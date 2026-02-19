"""
Docker Stop Module
Stop a running Docker container
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
    module_id='docker.stop',
    version='1.0.0',
    category='docker',
    tags=['docker', 'container', 'stop', 'shutdown', 'devops'],
    label='Stop Docker Container',
    label_key='modules.docker.stop.label',
    description='Stop a running Docker container',
    description_key='modules.docker.stop.description',
    icon='Container',
    color='#0DB7ED',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['docker.stop'],

    params_schema=compose(
        field(
            'container',
            type='string',
            label='Container',
            label_key='modules.docker.stop.params.container.label',
            description='Container ID or name to stop',
            description_key='modules.docker.stop.params.container.description',
            placeholder='my-container',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.docker.stop.params.timeout.label',
            description='Seconds to wait before killing the container',
            description_key='modules.docker.stop.params.timeout.description',
            default=10,
            min=0,
            max=300,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'container_id': {
            'type': 'string',
            'description': 'ID or name of the stopped container',
            'description_key': 'modules.docker.stop.output.container_id.description',
        },
        'stopped': {
            'type': 'boolean',
            'description': 'Whether the container was successfully stopped',
            'description_key': 'modules.docker.stop.output.stopped.description',
        },
    },
    examples=[
        {
            'title': 'Stop a container by name',
            'params': {
                'container': 'my-nginx',
            },
        },
        {
            'title': 'Stop with custom timeout',
            'params': {
                'container': 'my-app',
                'timeout': 30,
            },
        },
    ],
    timeout_ms=60000,
)
async def docker_stop(context: Dict[str, Any]) -> Dict[str, Any]:
    """Stop a running Docker container."""
    params = context.get('params', {})

    container = params.get('container')
    if not container:
        raise ValidationError("Missing required parameter: container", field="container")

    timeout = params.get('timeout', 10)

    args = ['docker', 'stop', '--time', str(int(timeout)), str(container)]

    logger.info("Docker stop: %s", ' '.join(args))

    # Allow extra time beyond the docker stop timeout for the command itself
    cmd_timeout = int(timeout) + 15

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=cmd_timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ModuleError(
                "Docker stop timed out after %d seconds" % cmd_timeout
            )

        stdout = stdout_bytes.decode('utf-8', errors='replace').strip()
        stderr = stderr_bytes.decode('utf-8', errors='replace').strip()

        if process.returncode != 0:
            error_msg = stderr if stderr else stdout
            raise ModuleError(
                "Docker stop failed (exit code %d): %s" % (process.returncode, error_msg)
            )

        container_id = stdout if stdout else str(container)

        return {
            'ok': True,
            'data': {
                'container_id': container_id,
                'stopped': True,
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker stop error: %s", e)
        raise ModuleError("Docker stop failed: %s" % str(e))
