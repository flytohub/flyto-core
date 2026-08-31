# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Port Check Module
Check if a network port is open or closed

HOW FAR THIS MODULE FOLLOWS REALITY

A completed TCP handshake is one of the least ambiguous measurements anything in
this product makes: a three-way handshake finished, so something is listening.
`open: True` is a real observation and always was.

`open: False` was not, and that is what this file had to fix before it could
claim anything. `_check_port_async` caught `(asyncio.TimeoutError,
ConnectionRefusedError, OSError)` in one clause and returned the same `False`
for all of them, so the payload said "closed" for two facts that are not the
same fact at all:

    the connect returned an error      the stack tried and the attempt ended
                                       with a reason -- a RST, no route, an
                                       unreachable host. The question "does this
                                       port accept a connection" was answered.
    the connect ran out of time        nobody said anything. We stopped waiting;
                                       a dropping firewall and an answer still
                                       in flight look identical from here, and
                                       calling either one "closed" is an
                                       inference dressed as a measurement.

Both still report `open: False` -- the behaviour is unchanged, because a caller
asking "can I connect" is answered the same way by both. What is new is
`verdict` on each result and the rung that rests on it:

    every port answered definitely                              OBSERVED
    any port gave no answer                                     INDETERMINATE
    the host was refused by the SSRF guard                      FAILED
    no ports were requested at all                              INDETERMINATE

WHY THE LINE IS DRAWN AT THE TIMEOUT and not at `ConnectionRefusedError`, which
is the tidier-looking place for it: asyncio does not preserve the distinction.
`open_connection('localhost', 1)` resolves to both `::1` and `127.0.0.1`, both
refuse, and `create_connection` flattens the two `ConnectionRefusedError`s into
one bare `OSError` whose entire content is a formatted string -- `errno` is
None. Checking for the exception type would therefore report the single most
common case in this product, a closed port on localhost, as unmeasured, while
the identical check against `127.0.0.1` measured it fine. That would be a rung
tracking an accident of name resolution rather than anything about the world.
The information a definite verdict rests on is that the connect ENDED rather
than timed out, and that survives the flattening.

`socket.gaierror` is excluded even though it is an OSError, and it is the case
that proves the rule: a name that will not resolve means no connect was ever
attempted, so there is no measurement of the port to have.

`expect_open` changes the claimant, not the ladder. It is a predicate the CALLER
wrote and this module evaluates, so when it does not hold the answer is FAILED
rather than a low rung -- `outcome.py` splits exactly on this, and a caller's
broken contract is the one case where somebody has to act. When it holds, the
rung is OBSERVED and not VERIFIED, and no `postcondition=` is declared on the
decorator: a listening socket is not a working service, and "port 5432 is open"
has never been the thing a caller actually wanted verified. `process.start`
makes the same call about `wait_for_output` for the same reason.
"""

import asyncio
import logging
import os
import socket
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import is_private_ip, resolve_guard_ip
from ...registry import register_module

logger = logging.getLogger(__name__)


# SECURITY: Localhost-only hosts that are always allowed
_LOCALHOST_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '0.0.0.0'})

#: Verdicts in which a connection attempt ran to a conclusion, and so measured
#: whether the port accepts connections. `connected` is a finished handshake;
#: `refused` is the host declining; `unreachable` is the stack ending the
#: attempt with a reason. `timeout`, `unresolved` and `error` are not here,
#: because in each of them nothing about the port was established.
_DEFINITE_VERDICTS = frozenset({'connected', 'refused', 'unreachable'})


def _expectation(expect_open: bool) -> str:
    """The caller's predicate, written out so it travels with the answer."""
    return (
        'every requested port accepts a TCP connection'
        if expect_open else
        'no requested port accepts a TCP connection'
    )


def _check_outcome(
    *,
    host: str,
    results: List[Dict[str, Any]],
    open_ports: List[int],
    closed_ports: List[int],
    expect_open: Any,
) -> Dict[str, Any]:
    """The rung these probes earned. See the module docstring for the argument.

    Order matters here and it is not the obvious one. "Did every port answer"
    is asked BEFORE "did the caller's expectation hold", because an expectation
    evaluated against a port that never answered has not really been evaluated:
    reporting FAILED on `expect_open=True` when the packet was dropped would put
    a broken-contract mark on a port that may well be open behind a firewall.
    The one exception is an expectation that is already contradicted by a
    definite measurement -- a port that connected while the caller expected all
    of them closed is a broken contract no amount of silence elsewhere softens.
    """
    unmeasured = [
        {'port': result['port'], 'verdict': result['verdict']}
        for result in results
        if result['verdict'] not in _DEFINITE_VERDICTS
    ]

    probe_effect = {
        'kind': 'tcp_ports_probed',
        'host': host,
        'open_ports': list(open_ports),
        'closed_ports': list(closed_ports),
        'verdicts': {str(result['port']): result['verdict'] for result in results},
        'measured_by': (
            'asyncio.open_connection per port: a completed handshake, or a '
            'connect attempt that ended with an error rather than a timeout'
        ),
        'detail': (
            'A finished handshake is an observation that something is listening. '
            'It is not an observation that the service behind it works, and this '
            'module never speaks a byte of any protocol.'
        ),
    }

    if not results:
        # Vacuous truth is the quietest false green there is: with no ports
        # requested, `ok` is True and `expect_open` "holds" over an empty set.
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.CALLER if expect_open is not None else ClaimBy.NONE,
            postcondition=_expectation(expect_open) if expect_open is not None else None,
            effects=[{
                'kind': 'no_ports_probed',
                'host': host,
                'measured_by': None,
                'detail': (
                    'No ports were requested, so no connection was attempted. Any '
                    'ok: True beside this is true of the empty set and rests on '
                    'nothing measured.'
                ),
            }],
        )

    # A definite verdict that goes the other way. For `expect_open=True` that is
    # any completed attempt that did not connect; for `expect_open=False` it is
    # a completed handshake. Only definite verdicts count, which is what stops a
    # timed-out probe from being reported as the caller's contract breaking.
    contradicted = expect_open is not None and any(
        r['verdict'] in _DEFINITE_VERDICTS and bool(r['open']) is not bool(expect_open)
        for r in results
    )

    if contradicted:
        return envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.CALLER,
            postcondition=_expectation(expect_open),
            effects=[
                probe_effect,
                {
                    'kind': 'port_expectation_broken',
                    'host': host,
                    'predicate': _expectation(expect_open),
                    'measured_by': (
                        'a definite verdict on at least one port that '
                        'contradicts the expectation'
                    ),
                    'detail': (
                        'The caller stated what the ports were supposed to be and '
                        'a port measured definitely otherwise. FAILED rather than '
                        'a low rung: the claim was the caller\'s, so somebody has '
                        'a broken assumption to act on.'
                    ),
                },
            ],
        )

    if unmeasured:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.CALLER if expect_open is not None else ClaimBy.NONE,
            postcondition=_expectation(expect_open) if expect_open is not None else None,
            effects=[
                probe_effect,
                {
                    'kind': 'ports_gave_no_answer',
                    'host': host,
                    'ports': unmeasured,
                    'measured_by': None,
                    'detail': (
                        'These ports are reported closed and were never measured '
                        'closed. Nothing came back -- a dropped packet, an '
                        'unreachable network, or a name that would not resolve -- '
                        'and none of those distinguishes a closed port from a '
                        'filtered one.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.CALLER if expect_open is not None else ClaimBy.NONE,
        postcondition=_expectation(expect_open) if expect_open is not None else None,
        effects=[probe_effect],
    )


@register_module(
    module_id='port.check',
    version='1.0.0',
    category='atomic',
    subcategory='port',
    tags=['port', 'check', 'network', 'status', 'atomic', 'ssrf_protected'],
    label='Check Port',
    label_key='modules.port.check.label',
    description='Check if network port(s) are open or closed',
    description_key='modules.port.check.description',
    icon='Wifi',
    color='#8B5CF6',

    # Connection types
    input_types=['number', 'array', 'object'],
    output_types=['object', 'boolean'],
    can_connect_to=['test.*', 'flow.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=10000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'port': {
            'type': 'any',
            'label': 'Port(s)',
            'label_key': 'modules.port.check.params.port.label',
            'description': 'Port number or array of ports to check',
            'description_key': 'modules.port.check.params.port.description',
            'required': True,
            'examples': [3000, [3000, 8080, 5432]]
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.port.check.params.host.label',
            'description': 'Host to connect to',
            'description_key': 'modules.port.check.params.host.description',
            'required': False,
            'default': 'localhost',
            'placeholder': 'localhost',
        },
        'connect_timeout': {
            'type': 'number',
            'label': 'Connect Timeout (seconds)',
            'label_key': 'modules.port.check.params.connect_timeout.label',
            'description': 'Timeout for each connection attempt',
            'description_key': 'modules.port.check.params.connect_timeout.description',
            'required': False,
            'default': 2,
            'placeholder': '30000',
        },
        'expect_open': {
            'type': 'boolean',
            'label': 'Expect Open',
            'label_key': 'modules.port.check.params.expect_open.label',
            'description': 'Set to true to assert ports are open, false for closed',
            'description_key': 'modules.port.check.params.expect_open.description',
            'required': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all checks passed (if expect_open is set)'
        ,
                'description_key': 'modules.port.check.output.ok.description'},
        'results': {
            'type': 'array',
            'description': (
                'Array of port check results. Each carries verdict: connected, '
                'refused, timeout, unreachable or error -- only the first two are '
                'measurements, the rest are a reported "closed" that nobody confirmed'
            )
        ,
                'description_key': 'modules.port.check.output.results.description'},
        'open_ports': {
            'type': 'array',
            'description': 'List of open ports'
        ,
                'description_key': 'modules.port.check.output.open_ports.description'},
        'closed_ports': {
            'type': 'array',
            'description': 'List of closed ports'
        ,
                'description_key': 'modules.port.check.output.closed_ports.description'},
        'summary': {
            'type': 'object',
            'description': 'Summary statistics'
        ,
                'description_key': 'modules.port.check.output.summary.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far these probes were followed: observed when every port gave a '
                'definite answer, indeterminate when any gave none, failed when a '
                'definite answer contradicted expect_open'
            ),
            'description_key': 'modules.port.check.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Check single port',
            'title_key': 'modules.port.check.examples.single.title',
            'params': {
                'port': 3000
            }
        },
        {
            'title': 'Check multiple ports',
            'title_key': 'modules.port.check.examples.multiple.title',
            'params': {
                'port': [3000, 8080, 5432],
                'host': 'localhost'
            }
        },
        {
            'title': 'Assert ports are open',
            'title_key': 'modules.port.check.examples.assert.title',
            'params': {
                'port': [80, 443],
                'host': 'example.com',
                'expect_open': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def port_check(context: Dict[str, Any]) -> Dict[str, Any]:
    """Check if network port(s) are open or closed"""
    params = context['params']
    ports_input = params['port']
    host = params.get('host', 'localhost')
    connect_timeout = params.get('connect_timeout', 2)
    expect_open = params.get('expect_open')

    # SECURITY: Validate host to prevent internal network scanning
    host_lower = host.lower()
    if host_lower not in _LOCALHOST_HOSTS:
        # Check if scanning non-localhost is allowed
        allow_remote = os.environ.get('FLYTO_ALLOW_PORT_SCAN', '').lower() == 'true'
        if not allow_remote:
            # Fail closed: an unresolvable host is treated as unsafe rather than
            # allowed through. This closes the IPv6-literal bypass where
            # gethostbyname() raised gaierror and the old bare `pass` let the
            # connect proceed against e.g. ::ffff:127.0.0.1
            # (GHSA-v7q9-pr72-5fmv). The resolver now lives in core.utils and is
            # shared with every other host-taking module rather than duplicated.
            guard_ip = resolve_guard_ip(host)
            if guard_ip is None or is_private_ip(guard_ip):
                target = host if guard_ip is None else f'{host} -> {guard_ip}'
                return {
                    'ok': False,
                    'error': f'SSRF blocked: Cannot scan private/unresolvable network host ({target}). '
                             'Set FLYTO_ALLOW_PORT_SCAN=true to allow.',
                    'error_code': 'SSRF_BLOCKED',
                    'results': [],
                    'open_ports': [],
                    'closed_ports': [],
                    'summary': {'total': 0, 'open': 0, 'closed': 0},
                    # FAILED, not INDETERMINATE: no packet left this process and
                    # nothing about the world is in question. The empty
                    # open/closed lists beside this are not measurements and the
                    # rung is what stops them being read as any.
                    'outcome': envelope(
                        Outcome.FAILED,
                        claim_by=ClaimBy.NONE,
                        effects=[{
                            'kind': 'port_scan_refused',
                            'host': host,
                            'measured_by': None,
                            'detail': (
                                'The outbound guard refused this host before any '
                                'connection was attempted. No port was probed.'
                            ),
                        }],
                    ),
                }

    # Normalize ports to list
    if isinstance(ports_input, int):
        ports = [ports_input]
    elif isinstance(ports_input, list):
        ports = [int(p) for p in ports_input]
    else:
        ports = [int(ports_input)]

    results: List[Dict[str, Any]] = []
    open_ports: List[int] = []
    closed_ports: List[int] = []

    # Check all ports concurrently
    async def check_single_port(port: int) -> Dict[str, Any]:
        is_open, verdict = await _check_port_async(host, port, connect_timeout)
        return {
            'port': port,
            'host': host,
            'open': is_open,
            'status': 'open' if is_open else 'closed',
            # What actually happened, beside what it was reduced to. 'closed'
            # above is a verdict on connectability; this is the evidence for it.
            'verdict': verdict,
        }

    check_tasks = [check_single_port(port) for port in ports]
    results = await asyncio.gather(*check_tasks)

    # Categorize results
    for result in results:
        if result['open']:
            open_ports.append(result['port'])
        else:
            closed_ports.append(result['port'])

    # Determine ok status
    ok = True
    if expect_open is not None:
        if expect_open:
            ok = len(closed_ports) == 0
        else:
            ok = len(open_ports) == 0

    summary = {
        'total': len(ports),
        'open': len(open_ports),
        'closed': len(closed_ports)
    }

    logger.info(
        f"Port check on {host}: {len(open_ports)} open, "
        f"{len(closed_ports)} closed"
    )

    return {
        'ok': ok,
        'results': results,
        'open_ports': open_ports,
        'closed_ports': closed_ports,
        'summary': summary,
        'outcome': _check_outcome(
            host=host,
            results=list(results),
            open_ports=open_ports,
            closed_ports=closed_ports,
            expect_open=expect_open,
        ),
    }


async def _check_port_async(host: str, port: int, timeout: float) -> tuple:
    """``(is_open, verdict)`` -- whether it connected, and what actually happened.

    The second element is the whole point. Every branch below used to collapse
    into a bare ``False``, which made a host that answered with a RST and a host
    that said nothing at all report the same thing. ``is_open`` keeps the old
    meaning exactly, so nothing downstream changes; ``verdict`` is what lets the
    outcome say whether the ``False`` was measured or assumed.

    Clause order is load-bearing, twice over. ``asyncio.TimeoutError`` IS
    ``TimeoutError`` from Python 3.11, which is a subclass of ``OSError``, so it
    has to be caught first or every abandoned attempt would be filed as a
    completed one -- the exact confusion this function exists to undo.
    ``socket.gaierror`` is likewise an OSError and has to be caught before it,
    because a name that would not resolve means the connect never happened.

    ``ConnectionRefusedError`` and the general ``OSError`` are kept apart for
    the record even though both are definite, because "the host declined" and
    "the stack could not get there" are different things to read in a log.
    """
    try:
        # Use asyncio's open_connection which is fully async
        future = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(future, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True, 'connected'
    except asyncio.TimeoutError:
        return False, 'timeout'
    except socket.gaierror:
        return False, 'unresolved'
    except ConnectionRefusedError:
        return False, 'refused'
    except OSError:
        # Includes asyncio's flattened multi-address failure, whose per-address
        # ConnectionRefusedErrors have already been reduced to a string. See the
        # module docstring: what makes this definite is that the attempt ended.
        return False, 'unreachable'
    except Exception:
        return False, 'error'
