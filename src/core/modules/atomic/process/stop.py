# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Process Stop Module
Stop background processes by ID, name, or PID

HOW FAR THIS MODULE FOLLOWS REALITY

Two very different mechanisms live behind one module id, and they do not earn
the same rung.

A REGISTERED process is stopped through its `asyncio` handle, and the line that
matters is `await process.wait()`: it returns when the child has been reaped
and its exit status read. That exit code is a fact about the world, produced by
the kernel, unobtainable if the process were still running -- so a registered
stop that completed is OBSERVED, and `exit_code` in the result is the evidence.

An UNREGISTERED pid is stopped with `os.kill`, which only queues a signal.
Delivery is not death:

    SIGKILL                             ACCEPTED
        `os.kill` returning means the kernel accepted the signal. Nothing looks
        afterwards, and SIGKILL is not instantaneous.
    SIGTERM/SIGINT, pid gone afterwards OBSERVED
        The liveness probe raised ProcessLookupError: the OS says no process
        holds that pid. That is a reading, not an inference.
    SIGTERM/SIGINT, pid still there     ACCEPTED
        The probe answered, we escalated to SIGKILL, and nothing looked again.
        The probe answering is also weaker than it appears -- a zombie answers.

Batch returns get one rung for the whole batch, and a mixed batch does not have
one: some children were reaped and some could not be touched. That is
INDETERMINATE, with both counts in the effect, rather than a rung picked from
whichever half is more flattering.

The empty batch -- `stop_all` over an empty registry, or a `name` that matched
nothing -- did nothing at all, and says DISPATCHED. Its `ok: True, count: 0` is
otherwise indistinguishable from having stopped everything asked for.
"""

import asyncio
import logging
import os
import signal
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets
from .start import get_process_registry


logger = logging.getLogger(__name__)


def _nothing_was_signalled() -> Dict[str, Any]:
    """The envelope for every return that never reached `os.kill` or `.terminate`.

    `effects` is empty, and empty is a claim: no signal was queued, no process
    was touched, nothing outlives this step. A refusal that listed effects
    would be describing what it declined to do.
    """
    return envelope(Outcome.FAILED, claim_by=ClaimBy.NONE, effects=[])


def _batch_outcome(
    stopped: List[Dict[str, Any]],
    failed: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """One rung for a loop over registered processes.

    A stopped entry is on the list because `await process.wait()` returned, so
    the child was reaped and its exit status read -- which is why the reaped
    count, and not `len(processes_to_stop)`, is what OBSERVED rests on.

    Four cases and only one of them is OBSERVED, because a batch is only as
    confirmed as its least confirmed member:

        reaped, none failed     OBSERVED       every child's exit was read
        reaped and failed       INDETERMINATE  no single rung describes it
        none reaped, failed     FAILED         nothing was stopped
        neither                 DISPATCHED     nothing was even attempted
    """
    reaped = [entry for entry in stopped if entry.get('exit_code') is not None]
    unreaped = len(stopped) - len(reaped)

    reaped_effect = {
        'kind': 'processes_reaped',
        'count': len(reaped),
        'exit_codes': [entry.get('exit_code') for entry in reaped],
        'measured_by': 'process.returncode after await process.wait() returned',
        'detail': (
            'Each of these children was waited on and its exit status read. A '
            'process that had not exited could not produce one.'
        ),
    }

    if not stopped and not failed:
        return envelope(
            Outcome.DISPATCHED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_process_matched',
                'measured_by': None,
                'detail': (
                    'Nothing matched, so no signal was sent and nothing was '
                    'observed. This return is ok:True with count 0, which on its '
                    'own is indistinguishable from having stopped everything '
                    'that was asked for.'
                ),
            }],
        )

    if stopped and not failed:
        # `unreaped` is normally 0: every entry on `stopped` came through
        # `await process.wait()`. It is checked rather than assumed because an
        # exit_code of None would mean the wait did not settle, and OBSERVED
        # must not rest on an entry that carries no exit status.
        if not reaped:
            return envelope(
                Outcome.ACCEPTED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'terminate_sent_without_exit_status',
                    'count': unreaped,
                    'measured_by': None,
                    'detail': (
                        'The processes were signalled but none reported an exit '
                        'code, so no exit was read back.'
                    ),
                }],
            )
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[reaped_effect],
        )

    if failed and not stopped:
        return envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'stop_failed',
                'count': len(failed),
                'measured_by': None,
                'detail': (
                    'Every process in this batch raised while being stopped, or '
                    'had no process object to stop. None was reaped.'
                ),
            }],
        )

    return envelope(
        # Mixed. Not FAILED -- children really were reaped; not OBSERVED --
        # others were not touched. A single rung cannot describe this batch, and
        # saying so is the answer rather than a gap in it.
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[
            reaped_effect,
            {
                'kind': 'stop_failed',
                'count': len(failed),
                'measured_by': None,
                'detail': (
                    'These were not stopped. They may still be running; nothing '
                    'here looked.'
                ),
            },
        ],
    )


def _find_processes_to_stop(
    registry: Dict[str, Any],
    process_id: Optional[str],
    name: Optional[str],
    pid: Optional[int],
    stop_all: bool,
) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    """Return (processes_to_stop, early_return_result).

    early_return_result is a dict to return immediately (e.g. NOT_FOUND)
    or None if processing should continue.
    """
    if stop_all:
        return list(registry.keys()), None

    if process_id:
        if process_id in registry:
            return [process_id], None
        return [], {
            'ok': False,
            'error': f'Process not found: {process_id}',
            'error_code': 'NOT_FOUND',
            'outcome': _nothing_was_signalled(),
        }

    if name:
        return [
            pid_key for pid_key, info in registry.items()
            if info.get('name') == name
        ], None

    if pid:
        found = [
            proc_id for proc_id, info in registry.items()
            if info.get('pid') == pid
        ]
        return found, None

    return [], None


async def _kill_pid_directly(
    pid: int,
    sig_num: int,
    sig: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    """Kill a process by system PID that is not in the registry.

    The rung here is decided by the probe that was already in this function.
    `os.kill(pid, 0)` raising ProcessLookupError is the OS reporting that no
    process holds this pid -- a reading of the process table, and the only
    evidence of death anywhere on this path. When the probe answers instead,
    the escalation to SIGKILL goes unchecked and the claim stops at "the
    signal was accepted".
    """
    death_observed = False
    signal_sent = False
    try:
        os.kill(pid, sig_num)
        # Set between the two statements on purpose. Everything after this point
        # can still raise -- `os.kill(pid, 0)` gives PermissionError for a pid
        # that has been reused by another user -- and a failure there is a
        # failure with a signal already delivered, which is not the same story
        # as a failure with none.
        signal_sent = True
        if sig_num != signal.SIGKILL:
            await asyncio.sleep(timeout_seconds)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                # Either probe raising means the pid is gone. This is the one
                # place on this path where the world was measured.
                death_observed = True

        if death_observed:
            outcome = envelope(
                Outcome.OBSERVED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'process_gone',
                    'pid': pid,
                    'signal': sig,
                    'measured_by': (
                        'os.kill(pid, 0) raised ProcessLookupError after the '
                        'signal'
                    ),
                    'detail': (
                        'No process holds this pid any more. Pids are reused, so '
                        'this is evidence about the number, and it is the '
                        'strongest evidence available without having been the '
                        "process's parent."
                    ),
                }],
            )
        else:
            outcome = envelope(
                Outcome.ACCEPTED,
                claim_by=ClaimBy.NONE,
                effects=[{
                    'kind': 'signal_accepted',
                    'pid': pid,
                    'signal': sig,
                    'measured_by': 'os.kill(pid, signal) returned without raising',
                    'detail': (
                        'The kernel queued the signal. Nothing looked afterwards: '
                        'for SIGKILL nothing is checked at all, and after a '
                        'SIGTERM that the process survived, the follow-up SIGKILL '
                        'is sent and never confirmed. A zombie also survives the '
                        'probe, so even "still there" is not proof it is alive.'
                    ),
                }],
            )

        return {
            'ok': True,
            'stopped': [{'pid': pid, 'signal': sig}],
            'failed': [],
            'count': 1,
            'outcome': outcome,
        }
    except ProcessLookupError:
        return {
            'ok': False,
            'error': f'Process with PID {pid} not found',
            'error_code': 'NOT_FOUND',
            # No signal was ever queued: the very first os.kill raised. That the
            # pid does not exist is a real reading, but it is a reading about
            # the request being impossible, not about an effect of ours.
            'outcome': _nothing_was_signalled(),
        }
    except Exception as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'KILL_FAILED',
            'outcome': (
                _nothing_was_signalled()
                if not signal_sent
                else envelope(
                    # A signal was delivered and then this went wrong. The
                    # process may be stopping, may have stopped, may be
                    # untouched by that signal. INDETERMINATE is the whole of
                    # what is known, and FAILED would assert more than that.
                    Outcome.INDETERMINATE,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'signal_accepted',
                        'pid': pid,
                        'signal': sig,
                        'measured_by': 'os.kill(pid, signal) returned without raising',
                        'detail': (
                            'The signal was delivered; the code that follows it up '
                            'raised, so nothing was checked afterwards.'
                        ),
                    }],
                )
            ),
        }


async def _stop_registered_process(
    proc_id: str,
    info: Dict[str, Any],
    sig_num: int,
    sig: str,
    timeout_seconds: float,
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    """Stop a single registered process. Returns a stopped-info or failed-info dict."""
    process = info.get('process')

    if not process:
        return {'failed': {'process_id': proc_id, 'error': 'Process object not found'}}

    try:
        proc_pid = process.pid

        if sig_num == signal.SIGKILL:
            process.kill()
        else:
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(f"Process {proc_id} didn't exit, force killing")
            process.kill()
            await process.wait()

        log_handle = info.get('log_handle')
        if log_handle:
            try:
                log_handle.close()
            except Exception:
                pass

        if proc_id in registry:
            del registry[proc_id]

        logger.info(f"Stopped process: {info.get('name')} (PID: {proc_pid})")
        return {
            'stopped': {
                'process_id': proc_id,
                'pid': proc_pid,
                'name': info.get('name'),
                'signal': sig,
                'exit_code': process.returncode,
            }
        }
    except Exception as e:
        logger.error(f"Failed to stop process {proc_id}: {e}")
        return {
            'failed': {
                'process_id': proc_id,
                'pid': info.get('pid'),
                'name': info.get('name'),
                'error': str(e),
            }
        }


@register_module(
    module_id='process.stop',
    version='1.0.0',
    category='atomic',
    subcategory='process',
    tags=['process', 'stop', 'kill', 'terminate', 'service', 'atomic'],
    label='Stop Process',
    label_key='modules.process.stop.label',
    description='Stop a running background process',
    description_key='modules.process.stop.description',
    icon='Square',
    color='#EF4444',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['test.*', 'flow.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.PROCESS_ID(),
        presets.PROCESS_NAME(label='Process Name'),
        presets.PID(),
        presets.SIGNAL_TYPE(default='SIGTERM'),
        presets.TIMEOUT_S(key='timeout', default=10),
        presets.FORCE_KILL(default=False),
        presets.STOP_ALL(default=False),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all processes were stopped successfully'
        ,
                'description_key': 'modules.process.stop.output.ok.description'},
        'stopped': {
            'type': 'array',
            'description': 'List of stopped process info'
        ,
                'description_key': 'modules.process.stop.output.stopped.description'},
        'failed': {
            'type': 'array',
            'description': 'List of processes that failed to stop'
        ,
                'description_key': 'modules.process.stop.output.failed.description'},
        'count': {
            'type': 'number',
            'description': 'Number of processes stopped'
        ,
                'description_key': 'modules.process.stop.output.count.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the stop was followed: observed when an exit status was '
                'read back, accepted when only a signal was delivered, '
                'dispatched when nothing matched, indeterminate for a mixed '
                'batch, failed when nothing was stopped'
            ),
            'description_key': 'modules.process.stop.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Stop by process ID',
            'title_key': 'modules.process.stop.examples.id.title',
            'params': {
                'process_id': '${start_result.process_id}'
            }
        },
        {
            'title': 'Stop by name',
            'title_key': 'modules.process.stop.examples.name.title',
            'params': {
                'name': 'dev-server'
            }
        },
        {
            'title': 'Force kill by PID',
            'title_key': 'modules.process.stop.examples.pid.title',
            'params': {
                'pid': 12345,
                'force': True
            }
        },
        {
            'title': 'Stop all processes',
            'title_key': 'modules.process.stop.examples.all.title',
            'params': {
                'stop_all': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def process_stop(context: Dict[str, Any]) -> Dict[str, Any]:
    """Stop a running background process"""
    params = context['params']
    process_id = params.get('process_id')
    name = params.get('name')
    pid = params.get('pid')
    sig = params.get('signal', 'SIGTERM')
    timeout_seconds = params.get('timeout', 10)
    force = params.get('force', False)
    stop_all = params.get('stop_all', False)

    # Map signal names to signal numbers
    signal_map = {
        'SIGTERM': signal.SIGTERM,
        'SIGKILL': signal.SIGKILL,
        'SIGINT': signal.SIGINT
    }
    sig_num = signal_map.get(sig, signal.SIGTERM)

    if force:
        sig_num = signal.SIGKILL

    registry = get_process_registry()

    # Find processes to stop
    processes_to_stop, early_return = _find_processes_to_stop(
        registry, process_id, name, pid, stop_all,
    )
    if early_return is not None:
        return early_return

    # Direct PID kill for unregistered processes
    if pid and not processes_to_stop:
        return await _kill_pid_directly(pid, sig_num, sig, timeout_seconds)

    if not processes_to_stop and not stop_all:
        return {
            'ok': False,
            'error': 'No process identifier provided (process_id, name, pid, or stop_all)',
            'error_code': 'NO_IDENTIFIER',
            'outcome': _nothing_was_signalled(),
        }

    # Stop each process
    stopped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for proc_id in processes_to_stop:
        info = registry.get(proc_id, {})
        result = await _stop_registered_process(
            proc_id, info, sig_num, sig, timeout_seconds, registry,
        )
        if 'stopped' in result:
            stopped.append(result['stopped'])
        else:
            failed.append(result['failed'])

    return {
        'ok': len(failed) == 0,
        'stopped': stopped,
        'failed': failed,
        'count': len(stopped),
        'outcome': _batch_outcome(stopped, failed),
    }
