"""
Process Start Module
Start and manage background processes (dev servers, services, etc.)
"""

import asyncio
import logging
import os
import signal
import sys
import time
from typing import Any, Dict, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)

# Global process registry for tracking started processes
_process_registry: Dict[str, Dict[str, Any]] = {}


def get_process_registry() -> Dict[str, Dict[str, Any]]:
    """Get the global process registry"""
    return _process_registry


@register_module(
    module_id='process.start',
    version='1.0.0',
    category='atomic',
    subcategory='process',
    tags=['process', 'background', 'server', 'service', 'daemon', 'atomic'],
    label='Start Background Process',
    label_key='modules.process.start.label',
    description='Start a background process (server, service, etc.)',
    description_key='modules.process.start.description',
    icon='Play',
    color='#22C55E',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['port.*', 'process.*', 'test.*'],

    # Execution settings
    timeout=30,  # Time to wait for process to start
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['process.start'],

    params_schema={
        'command': {
            'type': 'string',
            'label': 'Command',
            'label_key': 'modules.process.start.params.command.label',
            'description': 'Command to execute',
            'description_key': 'modules.process.start.params.command.description',
            'required': True,
            'placeholder': 'npm run dev',
            'examples': [
                'npm run dev',
                'python -m http.server 8000',
                'docker-compose up',
                'node server.js'
            ]
        },
        'cwd': {
            'type': 'string',
            'label': 'Working Directory',
            'label_key': 'modules.process.start.params.cwd.label',
            'description': 'Directory to run command in',
            'description_key': 'modules.process.start.params.cwd.description',
            'required': False
        },
        'env': {
            'type': 'object',
            'label': 'Environment Variables',
            'label_key': 'modules.process.start.params.env.label',
            'description': 'Additional environment variables',
            'description_key': 'modules.process.start.params.env.description',
            'required': False
        },
        'name': {
            'type': 'string',
            'label': 'Process Name',
            'label_key': 'modules.process.start.params.name.label',
            'description': 'Friendly name for the process (for later reference)',
            'description_key': 'modules.process.start.params.name.description',
            'required': False,
            'placeholder': 'dev-server'
        },
        'wait_for_output': {
            'type': 'string',
            'label': 'Wait for Output',
            'label_key': 'modules.process.start.params.wait_for_output.label',
            'description': 'String to wait for in stdout before returning (e.g., "ready on")',
            'description_key': 'modules.process.start.params.wait_for_output.description',
            'required': False,
            'examples': [
                'ready on',
                'listening on port',
                'Server started',
                'compiled successfully'
            ]
        },
        'wait_timeout': {
            'type': 'number',
            'label': 'Wait Timeout (seconds)',
            'label_key': 'modules.process.start.params.wait_timeout.label',
            'description': 'Timeout for wait_for_output',
            'description_key': 'modules.process.start.params.wait_timeout.description',
            'required': False,
            'default': 60
        },
        'capture_output': {
            'type': 'boolean',
            'label': 'Capture Output',
            'label_key': 'modules.process.start.params.capture_output.label',
            'description': 'Capture stdout/stderr (stored in memory)',
            'description_key': 'modules.process.start.params.capture_output.description',
            'required': False,
            'default': True
        },
        'log_file': {
            'type': 'string',
            'label': 'Log File',
            'label_key': 'modules.process.start.params.log_file.label',
            'description': 'File to write process output to',
            'description_key': 'modules.process.start.params.log_file.description',
            'required': False
        },
        'auto_restart': {
            'type': 'boolean',
            'label': 'Auto Restart',
            'label_key': 'modules.process.start.params.auto_restart.label',
            'description': 'Automatically restart if process exits',
            'description_key': 'modules.process.start.params.auto_restart.description',
            'required': False,
            'default': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether process started successfully'
        },
        'pid': {
            'type': 'number',
            'description': 'Process ID'
        },
        'process_id': {
            'type': 'string',
            'description': 'Internal process identifier for process.stop'
        },
        'name': {
            'type': 'string',
            'description': 'Process name'
        },
        'command': {
            'type': 'string',
            'description': 'The executed command'
        },
        'cwd': {
            'type': 'string',
            'description': 'Working directory'
        },
        'started_at': {
            'type': 'string',
            'description': 'ISO timestamp when process started'
        },
        'initial_output': {
            'type': 'string',
            'description': 'Initial stdout output (if wait_for_output was used)'
        }
    },
    examples=[
        {
            'title': 'Start dev server',
            'title_key': 'modules.process.start.examples.dev.title',
            'params': {
                'command': 'npm run dev',
                'cwd': './frontend',
                'name': 'frontend-dev',
                'wait_for_output': 'ready on',
                'wait_timeout': 30
            }
        },
        {
            'title': 'Start Python HTTP server',
            'title_key': 'modules.process.start.examples.python.title',
            'params': {
                'command': 'python -m http.server 8000',
                'name': 'static-server'
            }
        },
        {
            'title': 'Start with environment',
            'title_key': 'modules.process.start.examples.env.title',
            'params': {
                'command': 'node server.js',
                'env': {'PORT': '3000', 'NODE_ENV': 'test'},
                'name': 'api-server',
                'wait_for_output': 'listening'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def process_start(context: Dict[str, Any]) -> Dict[str, Any]:
    """Start a background process"""
    import uuid
    from datetime import datetime

    params = context['params']
    command = params['command']
    cwd = params.get('cwd')
    env_vars = params.get('env', {})
    name = params.get('name', f'process-{uuid.uuid4().hex[:8]}')
    wait_for_output = params.get('wait_for_output')
    wait_timeout = params.get('wait_timeout', 60)
    capture_output = params.get('capture_output', True)
    log_file = params.get('log_file')

    # Resolve working directory
    if cwd:
        cwd = os.path.abspath(os.path.expanduser(cwd))
        if not os.path.isdir(cwd):
            return {
                'ok': False,
                'error': f'Working directory does not exist: {cwd}',
                'error_code': 'INVALID_CWD'
            }
    else:
        cwd = os.getcwd()

    # Prepare environment
    env = os.environ.copy()
    env.update(env_vars)

    # Generate unique process ID
    process_id = f'{name}-{uuid.uuid4().hex[:8]}'

    # Open log file if specified
    log_handle = None
    if log_file:
        log_handle = open(log_file, 'a', encoding='utf-8')

    try:
        # Start the process
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
            start_new_session=True  # Detach from parent process group
        )

        started_at = datetime.utcnow().isoformat() + 'Z'
        initial_output = ''

        # Wait for specific output if requested
        if wait_for_output and capture_output:
            output_buffer = []
            found = False
            start_time = time.time()

            while time.time() - start_time < wait_timeout:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=1.0
                    )
                    if not line:
                        # Process ended
                        break

                    decoded = line.decode('utf-8', errors='replace')
                    output_buffer.append(decoded)

                    if log_handle:
                        log_handle.write(decoded)
                        log_handle.flush()

                    if wait_for_output in decoded:
                        found = True
                        break

                except asyncio.TimeoutError:
                    # Check if process is still running
                    if process.returncode is not None:
                        break
                    continue

            initial_output = ''.join(output_buffer)

            if not found:
                # Process didn't produce expected output
                if process.returncode is not None:
                    return {
                        'ok': False,
                        'error': f'Process exited before outputting "{wait_for_output}"',
                        'error_code': 'PROCESS_EXITED_EARLY',
                        'exit_code': process.returncode,
                        'output': initial_output
                    }
                else:
                    return {
                        'ok': False,
                        'error': f'Timeout waiting for "{wait_for_output}"',
                        'error_code': 'WAIT_TIMEOUT',
                        'output': initial_output,
                        'pid': process.pid
                    }

        # Register the process
        _process_registry[process_id] = {
            'process': process,
            'pid': process.pid,
            'name': name,
            'command': command,
            'cwd': cwd,
            'started_at': started_at,
            'log_handle': log_handle,
            'capture_output': capture_output
        }

        # Start background output reader if capturing
        if capture_output and not wait_for_output:
            asyncio.create_task(_read_output(process_id, process, log_handle))

        logger.info(f"Started process: {name} (PID: {process.pid})")

        return {
            'ok': True,
            'pid': process.pid,
            'process_id': process_id,
            'name': name,
            'command': command,
            'cwd': cwd,
            'started_at': started_at,
            'initial_output': initial_output
        }

    except Exception as e:
        if log_handle:
            log_handle.close()
        logger.error(f"Failed to start process: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'START_FAILED'
        }


async def _read_output(process_id: str, process: asyncio.subprocess.Process, log_handle):
    """Background task to read process output"""
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            if log_handle:
                decoded = line.decode('utf-8', errors='replace')
                log_handle.write(decoded)
                log_handle.flush()

    except Exception as e:
        logger.debug(f"Output reader for {process_id} ended: {e}")

    finally:
        if log_handle:
            log_handle.close()

        # Remove from registry when process ends
        if process_id in _process_registry:
            del _process_registry[process_id]
