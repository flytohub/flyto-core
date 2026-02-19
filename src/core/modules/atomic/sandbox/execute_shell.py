# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Sandbox Execute Shell Module
Execute a shell command with timeout and environment control.
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='sandbox.execute_shell',
    version='1.0.0',
    category='sandbox',
    tags=['sandbox', 'shell', 'command', 'execute', 'bash', 'terminal'],
    label='Execute Shell',
    label_key='modules.sandbox.execute_shell.label',
    description='Execute a shell command with timeout and environment control',
    description_key='modules.sandbox.execute_shell.description',
    icon='Terminal',
    color='#EF4444',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=30000,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['subprocess.execute'],

    params_schema=compose(
        field(
            'command',
            type='text',
            label='Command',
            label_key='modules.sandbox.execute_shell.params.command.label',
            description='Shell command to execute',
            description_key='modules.sandbox.execute_shell.params.command.description',
            required=True,
            placeholder='echo "Hello, World!"',
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.sandbox.execute_shell.params.timeout.label',
            description='Execution timeout in seconds',
            description_key='modules.sandbox.execute_shell.params.timeout.description',
            default=10,
            min=1,
            max=300,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'working_dir',
            type='string',
            label='Working Directory',
            label_key='modules.sandbox.execute_shell.params.working_dir.label',
            description='Working directory for the command',
            description_key='modules.sandbox.execute_shell.params.working_dir.description',
            placeholder='/tmp',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'env',
            type='object',
            label='Environment Variables',
            label_key='modules.sandbox.execute_shell.params.env.label',
            description='Additional environment variables to set (merged with current env)',
            description_key='modules.sandbox.execute_shell.params.env.description',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'stdout': {
            'type': 'string',
            'description': 'Standard output from the command',
            'description_key': 'modules.sandbox.execute_shell.output.stdout.description',
        },
        'stderr': {
            'type': 'string',
            'description': 'Standard error from the command',
            'description_key': 'modules.sandbox.execute_shell.output.stderr.description',
        },
        'exit_code': {
            'type': 'number',
            'description': 'Process exit code (0 = success)',
            'description_key': 'modules.sandbox.execute_shell.output.exit_code.description',
        },
        'execution_time_ms': {
            'type': 'number',
            'description': 'Execution time in milliseconds',
            'description_key': 'modules.sandbox.execute_shell.output.execution_time_ms.description',
        },
    },
    examples=[
        {
            'title': 'Simple echo',
            'title_key': 'modules.sandbox.execute_shell.examples.echo.title',
            'params': {
                'command': 'echo "Hello, World!"',
                'timeout': 10,
            },
        },
        {
            'title': 'List files with custom working directory',
            'title_key': 'modules.sandbox.execute_shell.examples.ls.title',
            'params': {
                'command': 'ls -la',
                'working_dir': '/tmp',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def sandbox_execute_shell(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a shell command with timeout and environment control."""
    params = context['params']
    command = params.get('command', '')
    timeout = int(params.get('timeout', 10))
    working_dir = params.get('working_dir', '').strip() or None
    extra_env = params.get('env') or {}

    if not command.strip():
        raise ValidationError("Missing required parameter: command", field="command")

    # Validate working directory if provided
    if working_dir and not os.path.isdir(working_dir):
        raise ValidationError(
            "Working directory does not exist: {}".format(working_dir),
            field="working_dir",
        )

    # Build environment: inherit current env + merge extra vars
    env = None
    if extra_env:
        env = dict(os.environ)
        for k, v in extra_env.items():
            env[str(k)] = str(v)

    start_time = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
            return {
                'ok': True,
                'data': {
                    'stdout': '',
                    'stderr': 'Command timed out after {} seconds'.format(timeout),
                    'exit_code': -1,
                    'execution_time_ms': elapsed_ms,
                },
            }

        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')
        exit_code = proc.returncode if proc.returncode is not None else -1

        logger.info(
            "Shell command completed (exit=%d, %.1fms)",
            exit_code, elapsed_ms,
        )

        return {
            'ok': True,
            'data': {
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': exit_code,
                'execution_time_ms': elapsed_ms,
            },
        }
    except Exception as e:
        raise ModuleError("Failed to execute shell command: {}".format(str(e)))
