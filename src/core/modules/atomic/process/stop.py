"""
Process Stop Module
Stop background processes by ID, name, or PID
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any, Dict, List, Optional

from ...registry import register_module
from .start import get_process_registry


logger = logging.getLogger(__name__)


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

    # Execution settings
    timeout=30,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['process.stop'],

    params_schema={
        'process_id': {
            'type': 'string',
            'label': 'Process ID',
            'label_key': 'modules.process.stop.params.process_id.label',
            'description': 'Internal process ID from process.start',
            'description_key': 'modules.process.stop.params.process_id.description',
            'required': False
        },
        'name': {
            'type': 'string',
            'label': 'Process Name',
            'label_key': 'modules.process.stop.params.name.label',
            'description': 'Process name (stops all matching)',
            'description_key': 'modules.process.stop.params.name.description',
            'required': False
        },
        'pid': {
            'type': 'number',
            'label': 'PID',
            'label_key': 'modules.process.stop.params.pid.label',
            'description': 'System process ID',
            'description_key': 'modules.process.stop.params.pid.description',
            'required': False
        },
        'signal': {
            'type': 'string',
            'label': 'Signal',
            'label_key': 'modules.process.stop.params.signal.label',
            'description': 'Signal to send (SIGTERM, SIGKILL, SIGINT)',
            'description_key': 'modules.process.stop.params.signal.description',
            'required': False,
            'default': 'SIGTERM',
            'enum': ['SIGTERM', 'SIGKILL', 'SIGINT']
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'label_key': 'modules.process.stop.params.timeout.label',
            'description': 'Time to wait for graceful shutdown before force kill',
            'description_key': 'modules.process.stop.params.timeout.description',
            'required': False,
            'default': 10
        },
        'force': {
            'type': 'boolean',
            'label': 'Force Kill',
            'label_key': 'modules.process.stop.params.force.label',
            'description': 'Use SIGKILL immediately',
            'description_key': 'modules.process.stop.params.force.description',
            'required': False,
            'default': False
        },
        'stop_all': {
            'type': 'boolean',
            'label': 'Stop All',
            'label_key': 'modules.process.stop.params.stop_all.label',
            'description': 'Stop all tracked processes',
            'description_key': 'modules.process.stop.params.stop_all.description',
            'required': False,
            'default': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether all processes were stopped successfully'
        },
        'stopped': {
            'type': 'array',
            'description': 'List of stopped process info'
        },
        'failed': {
            'type': 'array',
            'description': 'List of processes that failed to stop'
        },
        'count': {
            'type': 'number',
            'description': 'Number of processes stopped'
        }
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
    stopped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    # Find processes to stop
    processes_to_stop: List[str] = []

    if stop_all:
        processes_to_stop = list(registry.keys())
    elif process_id:
        if process_id in registry:
            processes_to_stop = [process_id]
        else:
            return {
                'ok': False,
                'error': f'Process not found: {process_id}',
                'error_code': 'NOT_FOUND'
            }
    elif name:
        processes_to_stop = [
            pid for pid, info in registry.items()
            if info.get('name') == name
        ]
    elif pid:
        # Find by system PID
        processes_to_stop = [
            proc_id for proc_id, info in registry.items()
            if info.get('pid') == pid
        ]

        # Also try to kill directly if not in registry
        if not processes_to_stop:
            try:
                os.kill(pid, sig_num)
                if sig_num != signal.SIGKILL:
                    # Wait for graceful shutdown
                    await asyncio.sleep(timeout_seconds)
                    try:
                        os.kill(pid, 0)  # Check if still alive
                        os.kill(pid, signal.SIGKILL)  # Force kill
                    except ProcessLookupError:
                        pass  # Already dead

                stopped.append({
                    'pid': pid,
                    'signal': sig
                })
                return {
                    'ok': True,
                    'stopped': stopped,
                    'failed': failed,
                    'count': 1
                }
            except ProcessLookupError:
                return {
                    'ok': False,
                    'error': f'Process with PID {pid} not found',
                    'error_code': 'NOT_FOUND'
                }
            except Exception as e:
                return {
                    'ok': False,
                    'error': str(e),
                    'error_code': 'KILL_FAILED'
                }

    if not processes_to_stop and not stop_all:
        return {
            'ok': False,
            'error': 'No process identifier provided (process_id, name, pid, or stop_all)',
            'error_code': 'NO_IDENTIFIER'
        }

    # Stop each process
    for proc_id in processes_to_stop:
        info = registry.get(proc_id, {})
        process = info.get('process')

        if not process:
            failed.append({
                'process_id': proc_id,
                'error': 'Process object not found'
            })
            continue

        try:
            proc_pid = process.pid

            # Send signal
            if sig_num == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()

            # Wait for process to exit
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown timed out
                logger.warning(f"Process {proc_id} didn't exit, force killing")
                process.kill()
                await process.wait()

            # Close log handle if exists
            log_handle = info.get('log_handle')
            if log_handle:
                try:
                    log_handle.close()
                except Exception:
                    pass

            # Remove from registry
            if proc_id in registry:
                del registry[proc_id]

            stopped.append({
                'process_id': proc_id,
                'pid': proc_pid,
                'name': info.get('name'),
                'signal': sig,
                'exit_code': process.returncode
            })

            logger.info(f"Stopped process: {info.get('name')} (PID: {proc_pid})")

        except Exception as e:
            failed.append({
                'process_id': proc_id,
                'pid': info.get('pid'),
                'name': info.get('name'),
                'error': str(e)
            })
            logger.error(f"Failed to stop process {proc_id}: {e}")

    return {
        'ok': len(failed) == 0,
        'stopped': stopped,
        'failed': failed,
        'count': len(stopped)
    }
