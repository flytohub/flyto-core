"""
Docker Logs Module
Get container logs
"""
import asyncio
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='docker.logs',
    version='1.0.0',
    category='docker',
    tags=['docker', 'container', 'logs', 'output', 'debug', 'devops'],
    label='Get Container Logs',
    label_key='modules.docker.logs.label',
    description='Get logs from a Docker container',
    description_key='modules.docker.logs.description',
    icon='Container',
    color='#0DB7ED',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['docker.read'],

    params_schema=compose(
        field(
            'container',
            type='string',
            label='Container',
            label_key='modules.docker.logs.params.container.label',
            description='Container ID or name',
            description_key='modules.docker.logs.params.container.description',
            placeholder='my-container',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'tail',
            type='number',
            label='Tail Lines',
            label_key='modules.docker.logs.params.tail.label',
            description='Number of lines to show from the end of the logs',
            description_key='modules.docker.logs.params.tail.description',
            default=100,
            min=1,
            max=10000,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'follow',
            type='boolean',
            label='Follow',
            label_key='modules.docker.logs.params.follow.label',
            description='Follow log output (streams until timeout)',
            description_key='modules.docker.logs.params.follow.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'timestamps',
            type='boolean',
            label='Timestamps',
            label_key='modules.docker.logs.params.timestamps.label',
            description='Show timestamps in log output',
            description_key='modules.docker.logs.params.timestamps.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'logs': {
            'type': 'string',
            'description': 'Container log output',
            'description_key': 'modules.docker.logs.output.logs.description',
        },
        'lines': {
            'type': 'number',
            'description': 'Number of log lines returned',
            'description_key': 'modules.docker.logs.output.lines.description',
        },
    },
    examples=[
        {
            'title': 'Get last 50 lines',
            'params': {
                'container': 'my-nginx',
                'tail': 50,
            },
        },
        {
            'title': 'Get logs with timestamps',
            'params': {
                'container': 'my-app',
                'tail': 100,
                'timestamps': True,
            },
        },
    ],
    timeout_ms=30000,
)
async def docker_logs(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get logs from a Docker container."""
    params = context.get('params', {})

    container = params.get('container')
    if not container:
        raise ValidationError("Missing required parameter: container", field="container")

    tail = params.get('tail', 100)
    follow = params.get('follow', False)
    timestamps = params.get('timestamps', False)

    args = ['docker', 'logs']

    args.extend(['--tail', str(int(tail))])

    if follow:
        args.append('--follow')

    if timestamps:
        args.append('--timestamps')

    args.append(str(container))

    logger.info("Docker logs: %s", ' '.join(args))

    # For follow mode, use a shorter timeout so we don't hang forever
    timeout_seconds = 10 if follow else 25

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            if follow:
                # For follow mode, timeout is expected; collect what we have
                stdout_bytes = b''
                stderr_bytes = b''
            else:
                raise ModuleError("Docker logs timed out after %d seconds" % timeout_seconds)

        # Docker logs sends output to both stdout and stderr
        stdout = stdout_bytes.decode('utf-8', errors='replace').strip() if stdout_bytes else ''
        stderr = stderr_bytes.decode('utf-8', errors='replace').strip() if stderr_bytes else ''

        if process.returncode is not None and process.returncode != 0 and not follow:
            error_msg = stderr if stderr else stdout
            raise ModuleError(
                "Docker logs failed (exit code %d): %s" % (process.returncode, error_msg)
            )

        # Docker sometimes sends log output to stderr, combine both
        log_output = stdout
        if stderr and not log_output:
            log_output = stderr
        elif stderr and log_output:
            log_output = log_output + '\n' + stderr

        line_count = len(log_output.splitlines()) if log_output else 0

        return {
            'ok': True,
            'data': {
                'logs': log_output,
                'lines': line_count,
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker logs error: %s", e)
        raise ModuleError("Docker logs failed: %s" % str(e))
