# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Sandbox Execute JavaScript Module
Execute JavaScript code via Node.js with timeout.
"""
import asyncio
import logging
import os
import tempfile
import time
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='sandbox.execute_js',
    version='1.0.0',
    category='sandbox',
    tags=['sandbox', 'javascript', 'js', 'node', 'execute', 'code'],
    label='Execute JavaScript',
    label_key='modules.sandbox.execute_js.label',
    description='Execute JavaScript code via Node.js with timeout',
    description_key='modules.sandbox.execute_js.description',
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
            'code',
            type='text',
            label='JavaScript Code',
            label_key='modules.sandbox.execute_js.params.code.label',
            description='JavaScript code to execute via Node.js',
            description_key='modules.sandbox.execute_js.params.code.description',
            required=True,
            placeholder='console.log("Hello, World!");',
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.sandbox.execute_js.params.timeout.label',
            description='Execution timeout in seconds',
            description_key='modules.sandbox.execute_js.params.timeout.description',
            default=10,
            min=1,
            max=300,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'stdout': {
            'type': 'string',
            'description': 'Standard output from the script',
            'description_key': 'modules.sandbox.execute_js.output.stdout.description',
        },
        'stderr': {
            'type': 'string',
            'description': 'Standard error from the script',
            'description_key': 'modules.sandbox.execute_js.output.stderr.description',
        },
        'exit_code': {
            'type': 'number',
            'description': 'Process exit code (0 = success)',
            'description_key': 'modules.sandbox.execute_js.output.exit_code.description',
        },
        'execution_time_ms': {
            'type': 'number',
            'description': 'Execution time in milliseconds',
            'description_key': 'modules.sandbox.execute_js.output.execution_time_ms.description',
        },
    },
    examples=[
        {
            'title': 'Simple console.log',
            'title_key': 'modules.sandbox.execute_js.examples.simple.title',
            'params': {
                'code': 'console.log("Hello, World!");',
                'timeout': 10,
            },
        },
        {
            'title': 'JSON processing',
            'title_key': 'modules.sandbox.execute_js.examples.json.title',
            'params': {
                'code': 'const data = { name: "test", value: 42 };\nconsole.log(JSON.stringify(data, null, 2));',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def sandbox_execute_js(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute JavaScript code via Node.js with timeout."""
    params = context['params']
    code = params.get('code', '')
    timeout = int(params.get('timeout', 10))

    if not code.strip():
        raise ValidationError("Missing required parameter: code", field="code")

    # Check if Node.js is available
    node_path = await _find_node()
    if not node_path:
        raise ModuleError(
            "Node.js is not installed. "
            "Install Node.js from https://nodejs.org to use sandbox.execute_js"
        )

    # Write code to a temp file
    tmp_fd = None
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.js', prefix='flyto_sandbox_')
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(code)
        tmp_fd = None  # os.fdopen took ownership

        start_time = time.monotonic()

        proc = await asyncio.create_subprocess_exec(
            node_path, tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
                    'stderr': 'Execution timed out after {} seconds'.format(timeout),
                    'exit_code': -1,
                    'execution_time_ms': elapsed_ms,
                },
            }

        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')
        exit_code = proc.returncode if proc.returncode is not None else -1

        logger.info(
            "JavaScript sandbox execution completed (exit=%d, %.1fms)",
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
    except ModuleError:
        raise
    except Exception as e:
        raise ModuleError("Failed to execute JavaScript code: {}".format(str(e)))
    finally:
        # Clean up temp file
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


async def _find_node() -> str:
    """Find the Node.js executable path. Returns empty string if not found."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'which', 'node',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        path = stdout_bytes.decode('utf-8', errors='replace').strip()
        if path and proc.returncode == 0:
            return path
    except Exception:
        pass

    # Fallback: check common paths
    for candidate in ['/usr/local/bin/node', '/usr/bin/node', '/opt/homebrew/bin/node']:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return ''
