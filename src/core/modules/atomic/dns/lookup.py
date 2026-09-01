# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
DNS Lookup Module
Perform DNS record lookups for domains

HOW FAR THIS MODULE FOLLOWS REALITY

Nine return paths across two resolvers, and they do not share a rung. What
separates them is whether a nameserver's answer is actually in the payload:

    records came back                    OBSERVED
        `records` holds strings built from rdata objects the resolver
        materialised out of a response. A returned record is that record; no
        report by a peer about its own work is involved.

    the server answered with no records  ACCEPTED
        dnspython's NoAnswer means a response arrived whose answer section is
        empty for this type. The server answered; nothing about the zone is in
        the payload, because `records: []` reads identically whether the type
        is absent, the query was discarded, or this module never ran.

    NXDOMAIN                             FAILED
        A definite negative from the authority. Not a low rung -- the lookup
        did not produce a resolution and never will for this name, which is
        what a consumer deciding whether to retry needs to know.

    timeout / no nameservers / unknown   INDETERMINATE
        Nobody answered, so whether the record exists is not known. A retry is
        meaningful here and is not on the NXDOMAIN path; that is the whole
        reason these two are different answers rather than one `error`.

    empty domain / dnspython missing     FAILED
        Nothing left this process at all.

A caveat the socket fallback carries and the dnspython path does not:
`getaddrinfo` goes through the OS resolver, which may answer from a cache
without a packet leaving the machine. The record content is still real -- it
came from a nameserver at some point -- but its freshness is not measured, and
`ttl` is `None` on that path precisely because nothing observed one. The effect
names which resolver produced the answer so a reader can tell.
"""

import asyncio
import logging
import socket
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


def _records_outcome(
    *,
    domain: str,
    record_type: str,
    records: List[str],
    ttl: Optional[int],
    resolver: str,
) -> Dict[str, Any]:
    """The rung for a query that came back without an error.

    `len(records)` is the decision, for the reason `database.query` splits on
    the same number: a returned record is an observation of that record, and
    zero returned records is an observation of nothing. The empty case is not
    demoted for being disappointing -- it is demoted because the value carries
    no information about whether the query reached anything.
    """
    if records:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'dns_records_returned',
                'domain': domain,
                'record_type': record_type,
                'count': len(records),
                'ttl': ttl,
                'resolver': resolver,
                'measured_by': 'len() over records the resolver returned',
                'detail': (
                    'Records were returned and are in the payload. The socket '
                    'resolver may serve these from an OS cache, in which case '
                    'the content is real and its freshness is not measured; '
                    'ttl is null whenever nothing observed one.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'dns_no_records_returned',
            'domain': domain,
            'record_type': record_type,
            'count': 0,
            'resolver': resolver,
            'measured_by': None,
            'detail': (
                'A nameserver answered and its answer section held no records '
                'of this type. That the server answered is all this says: an '
                'empty records list reads the same whether the type is absent '
                'or nothing was ever asked.'
            ),
        }],
    )


def _query_failed_outcome(
    *,
    domain: str,
    record_type: str,
    error_code: str,
    resolver: str,
    detail: str,
    rung: Outcome,
) -> Dict[str, Any]:
    """The envelope for a path that returns ``ok: False``.

    Attached even though `wrap_legacy_result` turns `ok: False` into an ERROR
    result and discards `data` on the way out of the step, for the reason
    `http.request._error_result` gives: the fact is true whether or not a
    consumer exists yet, and adding it after one exists means the consumer is
    built against results that carry nothing.

    The split that matters is FAILED versus INDETERMINATE, and it is exactly
    the retry question. NXDOMAIN is an authoritative "this name does not
    exist"; a timeout is "nobody said". Collapsing them into one error state is
    what makes an automation retry the first and give up on the second.
    """
    return envelope(
        rung,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'dns_query_unresolved',
            'domain': domain,
            'record_type': record_type,
            'error_code': error_code,
            'resolver': resolver,
            'measured_by': None,
            'detail': detail,
        }],
    )


@register_module(
    module_id='dns.lookup',
    version='1.0.0',
    category='atomic',
    subcategory='dns',
    tags=['dns', 'lookup', 'network', 'devops'],
    label='DNS Lookup',
    label_key='modules.dns.lookup.label',
    description='DNS lookup for domain records',
    description_key='modules.dns.lookup.description',
    icon='Globe',
    color='#06B6D4',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['network.connect'],

    params_schema=compose(
        field('domain', type='string', label='Domain', label_key='modules.dns.lookup.params.domain.label',
              description='Domain name to look up', required=True,
              placeholder='example.com', group=FieldGroup.BASIC),
        field('record_type', type='select', label='Record Type', label_key='modules.dns.lookup.params.record_type.label',
              description='DNS record type to query', default='A',
              options=[
                  {'value': 'A', 'label': 'A (IPv4)'},
                  {'value': 'AAAA', 'label': 'AAAA (IPv6)'},
                  {'value': 'CNAME', 'label': 'CNAME'},
                  {'value': 'MX', 'label': 'MX (Mail)'},
                  {'value': 'NS', 'label': 'NS (Nameserver)'},
                  {'value': 'TXT', 'label': 'TXT'},
                  {'value': 'SOA', 'label': 'SOA'},
                  {'value': 'SRV', 'label': 'SRV'},
              ],
              group=FieldGroup.BASIC),
        field('timeout', type='number', label='Timeout', label_key='modules.dns.lookup.params.timeout.label',
              description='Query timeout in seconds', default=10, min=1, max=60,
              group=FieldGroup.ADVANCED),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether lookup succeeded'},
        'data': {
            'type': 'object',
            'properties': {
                'domain': {'type': 'string', 'description': 'Queried domain'},
                'record_type': {'type': 'string', 'description': 'Record type queried'},
                'records': {'type': 'array', 'description': 'Resolved records'},
                'ttl': {'type': 'number', 'description': 'Time to live (if available)'},
                'outcome': {
                    'type': 'object',
                    'description': (
                        'How far this lookup was followed: "observed" when '
                        'records came back, "accepted" when a server answered '
                        'with none, "failed" for an authoritative NXDOMAIN, '
                        '"indeterminate" when nobody answered'
                    ),
                },
            }
        }
    },
    examples=[
        {
            'title': 'A record lookup',
            'title_key': 'modules.dns.lookup.examples.a.title',
            'params': {
                'domain': 'example.com',
                'record_type': 'A'
            }
        },
        {
            'title': 'MX record lookup',
            'title_key': 'modules.dns.lookup.examples.mx.title',
            'params': {
                'domain': 'example.com',
                'record_type': 'MX'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def dns_lookup(context: Dict[str, Any]) -> Dict[str, Any]:
    """Perform DNS lookup"""
    params = context['params']
    domain = params['domain']
    record_type = params.get('record_type', 'A')
    timeout = params.get('timeout', 10)

    # Strip trailing dot and whitespace
    domain = domain.strip().rstrip('.')

    if not domain:
        return {
            'ok': False,
            'error': 'Domain name is required',
            'error_code': 'VALIDATION_ERROR',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='VALIDATION_ERROR',
                    resolver='none',
                    rung=Outcome.FAILED,
                    detail='No query was made: the domain parameter was empty.',
                ),
            },
        }

    # Try using dnspython (dns.resolver) for full record type support
    try:
        from dns import resolver as _resolver

        del _resolver
        return await _lookup_with_dnspython(domain, record_type, timeout)
    except ImportError:
        pass

    # Fallback: use socket for A/AAAA records only
    if record_type in ('A', 'AAAA'):
        return await _lookup_with_socket(domain, record_type, timeout)

    return {
        'ok': False,
        'error': (
            f'Record type {record_type} requires dnspython library. '
            "Install with: pip install 'flyto-core[dns]'"
        ),
        'error_code': 'MISSING_DEPENDENCY',
        'data': {
            'domain': domain,
            'record_type': record_type,
            'outcome': _query_failed_outcome(
                domain=domain,
                record_type=record_type,
                error_code='MISSING_DEPENDENCY',
                resolver='none',
                rung=Outcome.FAILED,
                detail=(
                    'No query was made: this record type needs dnspython and '
                    'the socket fallback resolves A and AAAA only.'
                ),
            ),
        },
    }


async def _lookup_with_dnspython(domain: str, record_type: str, timeout: int) -> Dict[str, Any]:
    """DNS lookup using dnspython"""
    import dns.exception
    import dns.resolver

    loop = asyncio.get_event_loop()

    try:
        def resolve():
            resolver = dns.resolver.Resolver()
            resolver.lifetime = timeout
            return resolver.resolve(domain, record_type)

        answers = await asyncio.wait_for(
            loop.run_in_executor(None, resolve),
            timeout=timeout + 2
        )

        records: List[str] = []
        ttl: Optional[int] = None

        if hasattr(answers, 'rrset') and answers.rrset is not None:
            ttl = answers.rrset.ttl

        for rdata in answers:
            if record_type == 'MX':
                records.append(f'{rdata.preference} {rdata.exchange}')
            elif record_type == 'SOA':
                records.append(
                    f'{rdata.mname} {rdata.rname} {rdata.serial} '
                    f'{rdata.refresh} {rdata.retry} {rdata.expire} {rdata.minimum}'
                )
            elif record_type == 'SRV':
                records.append(
                    f'{rdata.priority} {rdata.weight} {rdata.port} {rdata.target}'
                )
            else:
                records.append(str(rdata))

        logger.info(f"DNS lookup: {domain} {record_type} -> {len(records)} records")

        return {
            'ok': True,
            'data': {
                'domain': domain,
                'record_type': record_type,
                'records': records,
                'ttl': ttl,
                'outcome': _records_outcome(
                    domain=domain,
                    record_type=record_type,
                    records=records,
                    ttl=ttl,
                    resolver='dnspython',
                ),
            }
        }

    except dns.resolver.NXDOMAIN:
        return {
            'ok': False,
            'error': f'Domain not found: {domain}',
            'error_code': 'NXDOMAIN',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='NXDOMAIN',
                    resolver='dnspython',
                    rung=Outcome.FAILED,
                    detail=(
                        'An authority answered that this name does not exist. '
                        'A definite negative, not a lost packet: retrying it '
                        'will return the same answer.'
                    ),
                ),
            },
        }

    except dns.resolver.NoAnswer:
        return {
            'ok': True,
            'data': {
                'domain': domain,
                'record_type': record_type,
                'records': [],
                'ttl': None,
                'outcome': _records_outcome(
                    domain=domain,
                    record_type=record_type,
                    records=[],
                    ttl=None,
                    resolver='dnspython',
                ),
            }
        }

    except dns.resolver.NoNameservers:
        return {
            'ok': False,
            'error': f'No nameservers available for {domain}',
            'error_code': 'NO_NAMESERVERS',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='NO_NAMESERVERS',
                    resolver='dnspython',
                    rung=Outcome.INDETERMINATE,
                    detail=(
                        'Every nameserver tried failed to answer. Whether this '
                        'record exists is not known.'
                    ),
                ),
            },
        }

    except asyncio.TimeoutError:
        return {
            'ok': False,
            'error': f'DNS query timed out after {timeout} seconds',
            'error_code': 'TIMEOUT',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='TIMEOUT',
                    resolver='dnspython',
                    rung=Outcome.INDETERMINATE,
                    detail=(
                        'The query was sent and no answer arrived in time. '
                        'Whether this record exists is not known.'
                    ),
                ),
            },
        }

    except Exception as e:
        logger.error(f"DNS lookup error for {domain}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'DNS_ERROR',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='DNS_ERROR',
                    resolver='dnspython',
                    rung=Outcome.INDETERMINATE,
                    detail=(
                        f'The resolver raised {type(e).__name__}. Nothing about '
                        'this record was established either way.'
                    ),
                ),
            },
        }


async def _lookup_with_socket(domain: str, record_type: str, timeout: int) -> Dict[str, Any]:
    """Fallback DNS lookup using socket.getaddrinfo"""
    loop = asyncio.get_event_loop()

    family = socket.AF_INET if record_type == 'A' else socket.AF_INET6

    try:
        def resolve():
            return socket.getaddrinfo(domain, None, family, socket.SOCK_STREAM)

        results = await asyncio.wait_for(
            loop.run_in_executor(None, resolve),
            timeout=timeout
        )

        records = list({addr[4][0] for addr in results})

        logger.info(f"DNS lookup (socket): {domain} {record_type} -> {len(records)} records")

        return {
            'ok': True,
            'data': {
                'domain': domain,
                'record_type': record_type,
                'records': records,
                'ttl': None,
                'outcome': _records_outcome(
                    domain=domain,
                    record_type=record_type,
                    records=records,
                    ttl=None,
                    resolver='socket.getaddrinfo',
                ),
            }
        }

    except socket.gaierror as e:
        # EAI_NONAME is the resolver saying the name does not resolve, which is
        # the same definite negative as NXDOMAIN. Every other gaierror --
        # EAI_AGAIN above all, which is a temporary failure -- says only that
        # this attempt did not work. Splitting them here is the difference
        # between "stop" and "try again", and `e.errno` is the one place the
        # distinction survives.
        definite = getattr(e, 'errno', None) == socket.EAI_NONAME
        return {
            'ok': False,
            'error': f'DNS resolution failed: {e}',
            'error_code': 'RESOLUTION_FAILED',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='RESOLUTION_FAILED',
                    resolver='socket.getaddrinfo',
                    rung=Outcome.FAILED if definite else Outcome.INDETERMINATE,
                    detail=(
                        'The resolver reported that this name does not '
                        'resolve (EAI_NONAME). A definite negative.'
                        if definite else
                        f'The resolver failed with {e}. This attempt did not '
                        'resolve the name; whether the name resolves is not '
                        'known.'
                    ),
                ),
            },
        }

    except asyncio.TimeoutError:
        return {
            'ok': False,
            'error': f'DNS query timed out after {timeout} seconds',
            'error_code': 'TIMEOUT',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='TIMEOUT',
                    resolver='socket.getaddrinfo',
                    rung=Outcome.INDETERMINATE,
                    detail=(
                        'The resolver did not answer in time. Whether this '
                        'name resolves is not known.'
                    ),
                ),
            },
        }

    except Exception as e:
        logger.error(f"DNS lookup error for {domain}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'DNS_ERROR',
            'data': {
                'domain': domain,
                'record_type': record_type,
                'outcome': _query_failed_outcome(
                    domain=domain,
                    record_type=record_type,
                    error_code='DNS_ERROR',
                    resolver='socket.getaddrinfo',
                    rung=Outcome.INDETERMINATE,
                    detail=(
                        f'The resolver raised {type(e).__name__}. Nothing about '
                        'this name was established either way.'
                    ),
                ),
            },
        }
