"""
Shell Execute Module
Execute shell commands with full control over environment and output
"""

import asyncio
import logging
import os
import shlex
from typing import Any, Dict, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='shell.exec',
    version='1.0.0',
    category='atomic',
    subcategory='shell',
    tags=['shell', 'command', 'exec', 'terminal', 'bash', 'atomic'],
    label='Execute Shell Command',
    label_key='modules.shell.exec.label',
    description='Execute a shell command and capture output',
    description_key='modules.shell.exec.description',
    icon='Terminal',
    color='#1E293B',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['file.*', 'data.*', 'test.*'],

    # Execution settings
    timeout=300,  # 5 minutes default for long-running commands
    retryable=False,  # Don't retry commands (could cause side effects)
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,  # Command output may contain sensitive data
    required_permissions=['shell.exec'],

    params_schema={
        'command': {
            'type': 'string',
            'label': 'Command',
            'label_key': 'modules.shell.exec.params.command.label',
            'description': 'Shell command to execute',
            'description_key': 'modules.shell.exec.params.command.description',
            'required': True,
            'placeholder': 'npm install',
            'examples': [
                'npm install',
                'python -m pytest tests/',
                'docker-compose up -d',
                'git status'
            ]
        },
        'cwd': {
            'type': 'string',
            'label': 'Working Directory',
            'label_key': 'modules.shell.exec.params.cwd.label',
            'description': 'Directory to execute command in',
            'description_key': 'modules.shell.exec.params.cwd.description',
            'required': False,
            'placeholder': '/path/to/project'
        },
        'env': {
            'type': 'object',
            'label': 'Environment Variables',
            'label_key': 'modules.shell.exec.params.env.label',
            'description': 'Additional environment variables',
            'description_key': 'modules.shell.exec.params.env.description',
            'required': False
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (seconds)',
            'label_key': 'modules.shell.exec.params.timeout.label',
            'description': 'Maximum execution time in seconds',
            'description_key': 'modules.shell.exec.params.timeout.description',
            'required': False,
            'default': 300
        },
        'shell': {
            'type': 'boolean',
            'label': 'Use Shell',
            'label_key': 'modules.shell.exec.params.shell.label',
            'description': 'Execute command through shell (enables pipes, redirects)',
            'description_key': 'modules.shell.exec.params.shell.description',
            'required': False,
            'default': True
        },
        'capture_stderr': {
            'type': 'boolean',
            'label': 'Capture Stderr',
            'label_key': 'modules.shell.exec.params.capture_stderr.label',
            'description': 'Capture stderr separately from stdout',
            'description_key': 'modules.shell.exec.params.capture_stderr.description',
            'required': False,
            'default': True
        },
        'encoding': {
            'type': 'string',
            'label': 'Output Encoding',
            'label_key': 'modules.shell.exec.params.encoding.label',
            'description': 'Character encoding for output',
            'description_key': 'modules.shell.exec.params.encoding.description',
            'required': False,
            'default': 'utf-8'
        },
        'raise_on_error': {
            'type': 'boolean',
            'label': 'Raise on Error',
            'label_key': 'modules.shell.exec.params.raise_on_error.label',
            'description': 'Raise exception if command returns non-zero exit code',
            'description_key': 'modules.shell.exec.params.raise_on_error.description',
            'required': False,
            'default': False
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether command executed successfully (exit code 0)'
        },
        'exit_code': {
            'type': 'number',
            'description': 'Command exit code'
        },
        'stdout': {
            'type': 'string',
            'description': 'Standard output'
        },
        'stderr': {
            'type': 'string',
            'description': 'Standard error output'
        },
        'command': {
            'type': 'string',
            'description': 'The executed command'
        },
        'cwd': {
            'type': 'string',
            'description': 'Working directory used'
        },
        'duration_ms': {
            'type': 'number',
            'description': 'Execution duration in milliseconds'
        }
    },
    examples=[
        {
            'title': 'Run npm install',
            'title_key': 'modules.shell.exec.examples.npm.title',
            'params': {
                'command': 'npm install',
                'cwd': './my-project'
            }
        },
        {
            'title': 'Run tests with pytest',
            'title_key': 'modules.shell.exec.examples.pytest.title',
            'params': {
                'command': 'python -m pytest tests/ -v',
                'timeout': 120
            }
        },
        {
            'title': 'Git status',
            'title_key': 'modules.shell.exec.examples.git.title',
            'params': {
                'command': 'git status --porcelain'
            }
        },
        {
            'title': 'Build project',
            'title_key': 'modules.shell.exec.examples.build.title',
            'params': {
                'command': 'npm run build',
                'cwd': './frontend',
                'env': {'NODE_ENV': 'production'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def shell_exec(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a shell command and capture output"""
    import time

    params = context['params']
    command = params['command']
    cwd = params.get('cwd')
    env_vars = params.get('env', {})
    timeout_seconds = params.get('timeout', 300)
    use_shell = params.get('shell', True)
    capture_stderr = params.get('capture_stderr', True)
    encoding = params.get('encoding', 'utf-8')
    raise_on_error = params.get('raise_on_error', False)

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

    # Prepare stderr handling
    stderr_pipe = asyncio.subprocess.PIPE if capture_stderr else asyncio.subprocess.STDOUT

    start_time = time.time()

    try:
        if use_shell:
            # Execute through shell
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=stderr_pipe,
                cwd=cwd,
                env=env
            )
        else:
            # Execute directly (safer, no shell injection)
            args = shlex.split(command)
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=stderr_pipe,
                cwd=cwd,
                env=env
            )

        # Wait for completion with timeout
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                'ok': False,
                'error': f'Command timed out after {timeout_seconds} seconds',
                'error_code': 'TIMEOUT',
                'command': command,
                'cwd': cwd,
                'duration_ms': int((time.time() - start_time) * 1000)
            }

        duration_ms = int((time.time() - start_time) * 1000)

        # Decode output
        stdout = stdout_bytes.decode(encoding, errors='replace') if stdout_bytes else ''
        stderr = stderr_bytes.decode(encoding, errors='replace') if stderr_bytes else ''

        exit_code = process.returncode
        ok = exit_code == 0

        logger.info(
            f"Shell exec: '{command[:50]}...' "
            f"exit_code={exit_code} duration={duration_ms}ms"
        )

        result = {
            'ok': ok,
            'exit_code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
            'command': command,
            'cwd': cwd,
            'duration_ms': duration_ms
        }

        if raise_on_error and not ok:
            error_msg = stderr if stderr else stdout
            raise RuntimeError(
                f"Command failed with exit code {exit_code}: {error_msg[:200]}"
            )

        return result

    except Exception as e:
        if isinstance(e, RuntimeError) and raise_on_error:
            raise

        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Shell exec failed: {e}")

        return {
            'ok': False,
            'error': str(e),
            'error_code': 'EXECUTION_ERROR',
            'command': command,
            'cwd': cwd,
            'duration_ms': duration_ms
        }
