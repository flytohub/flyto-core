# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
DNS Lookup Module
Perform DNS record lookups for domains
"""

import asyncio
import logging
import socket
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup


logger = logging.getLogger(__name__)


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
    author='Flyto Team',
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
            'error_code': 'VALIDATION_ERROR'
        }

    # Try using dnspython (dns.resolver) for full record type support
    try:
        import dns.resolver

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
            'Install with: pip install dnspython'
        ),
        'error_code': 'MISSING_DEPENDENCY'
    }


async def _lookup_with_dnspython(domain: str, record_type: str, timeout: int) -> Dict[str, Any]:
    """DNS lookup using dnspython"""
    import dns.resolver
    import dns.exception

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
            }
        }

    except dns.resolver.NXDOMAIN:
        return {
            'ok': False,
            'error': f'Domain not found: {domain}',
            'error_code': 'NXDOMAIN',
            'data': {'domain': domain, 'record_type': record_type}
        }

    except dns.resolver.NoAnswer:
        return {
            'ok': True,
            'data': {
                'domain': domain,
                'record_type': record_type,
                'records': [],
                'ttl': None,
            }
        }

    except dns.resolver.NoNameservers:
        return {
            'ok': False,
            'error': f'No nameservers available for {domain}',
            'error_code': 'NO_NAMESERVERS',
            'data': {'domain': domain, 'record_type': record_type}
        }

    except asyncio.TimeoutError:
        return {
            'ok': False,
            'error': f'DNS query timed out after {timeout} seconds',
            'error_code': 'TIMEOUT',
            'data': {'domain': domain, 'record_type': record_type}
        }

    except Exception as e:
        logger.error(f"DNS lookup error for {domain}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'DNS_ERROR',
            'data': {'domain': domain, 'record_type': record_type}
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

        records = list(set(addr[4][0] for addr in results))

        logger.info(f"DNS lookup (socket): {domain} {record_type} -> {len(records)} records")

        return {
            'ok': True,
            'data': {
                'domain': domain,
                'record_type': record_type,
                'records': records,
                'ttl': None,
            }
        }

    except socket.gaierror as e:
        return {
            'ok': False,
            'error': f'DNS resolution failed: {e}',
            'error_code': 'RESOLUTION_FAILED',
            'data': {'domain': domain, 'record_type': record_type}
        }

    except asyncio.TimeoutError:
        return {
            'ok': False,
            'error': f'DNS query timed out after {timeout} seconds',
            'error_code': 'TIMEOUT',
            'data': {'domain': domain, 'record_type': record_type}
        }

    except Exception as e:
        logger.error(f"DNS lookup error for {domain}: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'DNS_ERROR',
            'data': {'domain': domain, 'record_type': record_type}
        }
