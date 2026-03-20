# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Process Stop Module
Stop background processes by ID, name, or PID
"""

import asyncio
import logging
import os
import signal
from typing import Any, Dict, List, Optional, Tuple

from ...registry import register_module
from ...schema import compose, presets
from .start import get_process_registry


logger = logging.getLogger(__name__)


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
    """Kill a process by system PID that is not in the registry."""
    try:
        os.kill(pid, sig_num)
        if sig_num != signal.SIGKILL:
            await asyncio.sleep(timeout_seconds)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        return {
            'ok': True,
            'stopped': [{'pid': pid, 'signal': sig}],
            'failed': [],
            'count': 1,
        }
    except ProcessLookupError:
        return {
            'ok': False,
            'error': f'Process with PID {pid} not found',
            'error_code': 'NOT_FOUND',
        }
    except Exception as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'KILL_FAILED',
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
                'description_key': 'modules.process.stop.output.count.description'}
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
    author='Flyto Team',
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
            'error_code': 'NO_IDENTIFIER'
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
        'count': len(stopped)
    }
