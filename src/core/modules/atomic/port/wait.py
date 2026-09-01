# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Port Wait Module
Wait for a network port to become available

HOW FAR THIS MODULE FOLLOWS REALITY

Three return paths, and which rung each earns turns on a distinction the socket
code was throwing away. `_check_port` used `connect_ex`, which hands back the
errno rather than raising, and then compared it to zero -- discarding the one
piece of information that separates "the host answered and nothing is listening"
(`ECONNREFUSED`) from "nobody said anything before the second was up"
(`EAGAIN`/`EINPROGRESS`/`ETIMEDOUT`, or a name that would not resolve). The
errno was already in hand and was being reduced to a boolean.

The line drawn is the one `port.check` draws over asyncio's API and for the same
reason written out there: a connect that ENDED answered the question, a connect
that ran out of time abandoned it. `ECONNREFUSED` and `EHOSTUNREACH` are both
the first kind; `EAGAIN`, `EINPROGRESS` and `ETIMEDOUT` are the second.

That distinction is worth more here than it is in `port.check`, because of
`expect_closed`. Waiting for a port to OPEN ends on a completed handshake, which
is unambiguous whatever the failures before it looked like. Waiting for a port
to CLOSE ends on a *non*-answer, and a firewall that starts dropping packets ends
that wait exactly like a process shutting down would. Both still return
`ok: True` -- the behaviour is unchanged -- but only one of them is observed:

    waited for open, it connected                      OBSERVED
    waited for closed, the host refused the connection OBSERVED
    waited for closed, nothing answered                INDETERMINATE
    the wait timed out                                 FAILED
    the wait timed out having probed nothing            INDETERMINATE

FAILED for the ordinary timeout, and `claim_by` is CALLER, because `port` +
`timeout` + `expect_closed` together are a contract the caller wrote: this port
reaches this state inside this window. It did not. That is a broken contract and
not a gap in our looking, which is the distinction `outcome.py` exists to carry.
The last line is the degenerate case where `timeout` is small enough that the
loop exits before a single probe -- nothing was measured, so nothing failed.

WHY THAT TIMEOUT IS FAILED WHEN `port.check`'S IS NOT, since the two modules
otherwise reason identically and this looks like a contradiction. The predicates
are different, and each rung matches its own. `port.check` asserts a STATE --
"every requested port accepts a TCP connection" -- which a dropped packet does
not falsify, because the port may well be accepting connections behind the
firewall that ate the probe. This module asserts a TIME-BOUNDED EVENT -- "the
port accepts a TCP connection within 60s" -- and whether a connection succeeded
is always observable from this side, because success is positive evidence. The
window elapsing without one falsifies that literally, whatever the individual
attempts looked like. Note that only the wait-for-open case can reach the
timeout on silence at all: a wait for CLOSED returns on the first non-answer, so
its weak case is the INDETERMINATE above, not this.

A BUG THIS FOUND, fixed here. The timeout path returned
`'available': not expect_closed`, which is inverted: a wait for a port to open
that timed out reported `available: True` while its own error string said the
port never became available, and a wait for a port to close that timed out
reported `available: False` for a port that never closed. Both said the wait had
succeeded in the one field a consumer is most likely to branch on. It now
reports the last state actually measured, and falls back only when there is no
measurement to report.

VERIFIED is not reached and no `postcondition=` is declared. What the caller
wants is a service that is ready; what this measures is a socket that accepts
connections. A port opens before a server finishes booting, and this module
cannot tell the difference.
"""

import asyncio
import errno
import logging
import socket
import time
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_host
from ...registry import register_module


logger = logging.getLogger(__name__)

#: Verdicts in which the connection attempt ran to a conclusion. See
#: `port.check`, which draws the same line from the same reasoning over a
#: different API: what makes a verdict definite is that the attempt ENDED, not
#: which errno ended it. `unresolved` is out because a name that will not
#: resolve means the port was never asked anything.
_DEFINITE_VERDICTS = frozenset({'connected', 'refused', 'unreachable'})

#: connect_ex results that mean the attempt ran out of time rather than being
#: answered. macOS reports EAGAIN, Linux EINPROGRESS; ETIMEDOUT arrives when the
#: kernel gives up before the socket timeout does.
_TIMED_OUT_ERRNOS = frozenset({
    errno.EAGAIN, errno.EWOULDBLOCK, errno.EINPROGRESS, errno.ETIMEDOUT,
})


def _expectation(expect_closed: bool, timeout_seconds: Any) -> str:
    """The caller's contract, written out so it travels beside the answer."""
    state = 'stops accepting TCP connections' if expect_closed else 'accepts a TCP connection'
    return f'the port {state} within {timeout_seconds}s'


def _reached_outcome(
    *,
    host: str,
    port: int,
    expect_closed: bool,
    verdict: str,
    wait_time_ms: int,
    attempts: int,
    timeout_seconds: Any,
) -> Dict[str, Any]:
    """The rung for a wait that ended in the state the caller asked for.

    Two answers, and only the ``expect_closed`` wait can land on the weaker one.
    A wait for OPEN ends on ``connected``: a finished handshake, which is a
    measurement whatever preceded it. A wait for CLOSED ends on the ABSENCE of
    one, and there the verdict is everything -- a connect that ended with an
    error measured the port closed, while one that ran out of time ended the
    loop identically and measured nothing at all.
    """
    reached_effect = {
        'kind': 'port_reached_expected_state',
        'host': host,
        'port': port,
        'expected': 'closed' if expect_closed else 'open',
        'verdict': verdict,
        'wait_time_ms': wait_time_ms,
        'attempts': attempts,
        'measured_by': (
            'socket.connect_ex: 0 for a completed handshake, a non-timeout errno '
            'for an attempt that ended without one'
        ),
    }

    if verdict in _DEFINITE_VERDICTS:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.CALLER,
            postcondition=_expectation(expect_closed, timeout_seconds),
            effects=[dict(
                reached_effect,
                detail=(
                    'The host answered, and the answer is the state the caller '
                    'waited for. Not a claim about the service behind the '
                    'socket: a port accepts connections before a server has '
                    'finished starting, and this module speaks no protocol.'
                ),
            )],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.CALLER,
        postcondition=_expectation(expect_closed, timeout_seconds),
        effects=[dict(
            reached_effect,
            measured_by=None,
            detail=(
                'The wait ended because nothing answered, and this module '
                'reports that as closed. Nothing answering is not the same fact '
                'as the port being closed -- a firewall that started dropping '
                'packets ends this wait exactly the way a clean shutdown does. '
                'ok is True and the state was not observed.'
            ),
        )],
    )


def _timeout_outcome(
    *,
    host: str,
    port: int,
    expect_closed: bool,
    last_verdict: Optional[str],
    wait_time_ms: int,
    attempts: int,
    timeout_seconds: Any,
) -> Dict[str, Any]:
    """The rung for a wait that ran out of time.

    FAILED, with the claim attributed to the CALLER. The window came from the
    caller's `timeout`, the target state from their `expect_closed`; the module
    evaluated that predicate on every pass of the loop and it never held. That
    is a contract that was tested and broke, which is a different thing from
    "we could not tell" and is the one a consumer has to act on.

    The exception is a wait so short the loop exited before probing once. There
    is no measurement there to have failed, so it is INDETERMINATE.
    """
    if attempts == 0 or last_verdict is None:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.CALLER,
            postcondition=_expectation(expect_closed, timeout_seconds),
            effects=[{
                'kind': 'port_never_probed',
                'host': host,
                'port': port,
                'wait_time_ms': wait_time_ms,
                'attempts': attempts,
                'measured_by': None,
                'detail': (
                    'The deadline had already passed when the loop was entered, '
                    'so no connection was ever attempted. Nothing failed here '
                    'because nothing was tested.'
                ),
            }],
        )

    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.CALLER,
        postcondition=_expectation(expect_closed, timeout_seconds),
        effects=[{
            'kind': 'port_expectation_timed_out',
            'host': host,
            'port': port,
            'expected': 'closed' if expect_closed else 'open',
            'last_verdict': last_verdict,
            'wait_time_ms': wait_time_ms,
            'attempts': attempts,
            'measured_by': (
                f'{attempts} connect_ex attempts, none of which found the '
                'expected state'
            ),
            'detail': (
                'The caller stated a window and a target state and the port did '
                'not reach it. last_verdict is what the final attempt actually '
                'saw -- "timeout" or "unreachable" there means the port was '
                'never measured in any state, only never measured in the '
                'expected one.'
            ),
        }],
    )


@register_module(
    module_id='port.wait',
    version='1.0.0',
    category='atomic',
    subcategory='port',
    tags=['port', 'wait', 'network', 'server', 'ready', 'atomic', 'ssrf_protected', 'path_restricted'],
    label='Wait for Port',
    label_key='modules.port.wait.label',
    description='Wait for a network port to become available',
    description_key='modules.port.wait.description',
    icon='Clock',
    color='#F59E0B',

    # Connection types
    input_types=['number', 'object'],
    output_types=['object', 'boolean'],
    can_connect_to=['browser.*', 'http.*', 'test.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=120000,  # 2 minutes max wait
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.port.wait.params.port.label',
            'description': 'Port number to wait for',
            'description_key': 'modules.port.wait.params.port.description',
            'required': True,
            'placeholder': '3000',
            'validation': {
                'minimum': 1,
                'maximum': 65535
            }
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.port.wait.params.host.label',
            'description': 'Host to connect to',
            'description_key': 'modules.port.wait.params.host.description',
            'required': False,
            'default': 'localhost',
            'placeholder': 'localhost',
},
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'label_key': 'modules.port.wait.params.timeout.label',
            'description': 'Maximum time to wait',
            'description_key': 'modules.port.wait.params.timeout.description',
            'required': False,
            'default': 60
        },
        'interval': {
            'type': 'number',
            'label': 'Check Interval (ms)',
            'label_key': 'modules.port.wait.params.interval.label',
            'description': 'Time between connection attempts in milliseconds',
            'description_key': 'modules.port.wait.params.interval.description',
            'required': False,
            'default': 500
        },
        'expect_closed': {
            'type': 'boolean',
            'label': 'Expect Closed',
            'label_key': 'modules.port.wait.params.expect_closed.label',
            'description': 'Wait for port to become unavailable instead',
            'description_key': 'modules.port.wait.params.expect_closed.description',
            'required': False,
            'default': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether port is in expected state'
        ,
                'description_key': 'modules.port.wait.output.ok.description'},
        'available': {
            'type': 'boolean',
            'description': (
                'Whether port is currently available. On a timeout this is the last '
                'state actually measured -- see last_verdict for whether anything '
                'answered at all'
            )
        ,
                'description_key': 'modules.port.wait.output.available.description'},
        'last_verdict': {
            'type': 'string',
            'description': (
                'What the final connection attempt saw: connected, refused, timeout, '
                'unreachable or error. Only connected and refused are measurements '
                'of the port; the rest are a reported state nobody confirmed'
            ),
            'description_key': 'modules.port.wait.output.last_verdict.description'},
        'host': {
            'type': 'string',
            'description': 'Host that was checked'
        ,
                'description_key': 'modules.port.wait.output.host.description'},
        'port': {
            'type': 'number',
            'description': 'Port that was checked'
        ,
                'description_key': 'modules.port.wait.output.port.description'},
        'wait_time_ms': {
            'type': 'number',
            'description': 'Time spent waiting in milliseconds'
        ,
                'description_key': 'modules.port.wait.output.wait_time_ms.description'},
        'attempts': {
            'type': 'number',
            'description': 'Number of connection attempts'
        ,
                'description_key': 'modules.port.wait.output.attempts.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this wait was followed: observed when the host answered in '
                'the expected state, indeterminate when the wait ended on silence, '
                'failed when the caller\'s window expired'
            ),
            'description_key': 'modules.port.wait.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Wait for dev server',
            'title_key': 'modules.port.wait.examples.dev.title',
            'params': {
                'port': 3000,
                'timeout': 30
            }
        },
        {
            'title': 'Wait for database',
            'title_key': 'modules.port.wait.examples.db.title',
            'params': {
                'port': 5432,
                'host': 'localhost',
                'timeout': 60
            }
        },
        {
            'title': 'Wait for port to close',
            'title_key': 'modules.port.wait.examples.close.title',
            'params': {
                'port': 8080,
                'expect_closed': True,
                'timeout': 10
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def port_wait(context: Dict[str, Any]) -> Dict[str, Any]:
    """Wait for a network port to become available"""
    params = context['params']
    port = int(params['port'])
    host = params.get('host', 'localhost')
    # SECURITY: `host` is caller-controlled and this module opens a raw
    # connection to it. Unguarded that reaches any internal service the runner
    # can route to, including the cloud metadata endpoint — the same
    # reachability the HTTP SSRF advisories are about, without a URL. Loopback
    # stays allowed so self-hosted deployments are unaffected.
    enforce_outbound_host(host, purpose='port wait')
    timeout_seconds = params.get('timeout', 60)
    interval_ms = params.get('interval', 500)
    expect_closed = params.get('expect_closed', False)

    interval_seconds = interval_ms / 1000
    start_time = time.time()
    attempts = 0
    # The last thing actually measured, kept so the timeout path can report a
    # state it saw instead of deriving one from what was hoped for.
    last_is_open: Optional[bool] = None
    last_verdict: Optional[str] = None

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            wait_time_ms = int(elapsed * 1000)

            if expect_closed:
                error_msg = f'Port {host}:{port} did not close within {timeout_seconds}s'
            else:
                error_msg = f'Port {host}:{port} did not become available within {timeout_seconds}s'

            logger.warning(error_msg)
            return {
                'ok': False,
                # Was `not expect_closed`, which was inverted -- see the module
                # docstring. A wait for a port to open that timed out reported
                # available: True. The loop only reaches here having never seen
                # the expected state, so the last measurement is the honest
                # answer; `expect_closed` is the fallback for the case where
                # there was no measurement at all, and the rung says so.
                'available': last_is_open if last_is_open is not None else expect_closed,
                'host': host,
                'port': port,
                'wait_time_ms': wait_time_ms,
                'attempts': attempts,
                'last_verdict': last_verdict,
                'error': error_msg,
                'error_code': 'TIMEOUT',
                'outcome': _timeout_outcome(
                    host=host,
                    port=port,
                    expect_closed=expect_closed,
                    last_verdict=last_verdict,
                    wait_time_ms=wait_time_ms,
                    attempts=attempts,
                    timeout_seconds=timeout_seconds,
                ),
            }

        attempts += 1
        is_open, verdict = await _check_port(host, port)
        last_is_open, last_verdict = is_open, verdict

        if expect_closed:
            if not is_open:
                wait_time_ms = int((time.time() - start_time) * 1000)
                logger.info(f"Port {host}:{port} is now closed (waited {wait_time_ms}ms)")
                return {
                    'ok': True,
                    'available': False,
                    'host': host,
                    'port': port,
                    'wait_time_ms': wait_time_ms,
                    'attempts': attempts,
                    'last_verdict': verdict,
                    'outcome': _reached_outcome(
                        host=host,
                        port=port,
                        expect_closed=True,
                        verdict=verdict,
                        wait_time_ms=wait_time_ms,
                        attempts=attempts,
                        timeout_seconds=timeout_seconds,
                    ),
                }
        else:
            if is_open:
                wait_time_ms = int((time.time() - start_time) * 1000)
                logger.info(f"Port {host}:{port} is now available (waited {wait_time_ms}ms)")
                return {
                    'ok': True,
                    'available': True,
                    'host': host,
                    'port': port,
                    'wait_time_ms': wait_time_ms,
                    'attempts': attempts,
                    'last_verdict': verdict,
                    'outcome': _reached_outcome(
                        host=host,
                        port=port,
                        expect_closed=False,
                        verdict=verdict,
                        wait_time_ms=wait_time_ms,
                        attempts=attempts,
                        timeout_seconds=timeout_seconds,
                    ),
                }

        await asyncio.sleep(interval_seconds)


async def _check_port(host: str, port: int) -> tuple:
    """``(is_open, verdict)`` -- whether it connected, and on what evidence.

    ``is_open`` is unchanged: ``connect_ex`` returning 0. What is added is the
    reading of the errno it already returned. ``ECONNREFUSED`` is the host
    answering and declining, which measures the port closed; a timed-out connect
    or an unresolvable name measures nothing, and a caller told "closed" on that
    basis is being told an assumption.
    """
    try:
        # Use asyncio's socket operations for non-blocking check
        loop = asyncio.get_event_loop()

        def sync_check():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            try:
                result = sock.connect_ex((host, port))
                if result == 0:
                    return True, 'connected'
                if result == errno.ECONNREFUSED:
                    return False, 'refused'
                if result in _TIMED_OUT_ERRNOS:
                    return False, 'timeout'
                return False, 'unreachable'
            except socket.timeout:
                return False, 'timeout'
            except socket.gaierror:
                # The name did not resolve, so no connect was attempted and
                # there is nothing measured about the port.
                return False, 'unresolved'
            except OSError:
                return False, 'error'
            finally:
                sock.close()

        return await loop.run_in_executor(None, sync_check)
    except Exception:
        return False, 'error'
