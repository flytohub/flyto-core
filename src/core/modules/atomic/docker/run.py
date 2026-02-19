# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Run Module
Run a Docker container from an image
"""
import asyncio
import json
import logging
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _build_run_args(params: Dict[str, Any]) -> List[str]:
    """Build docker run CLI arguments from params."""
    args = ['docker', 'run']

    name = params.get('name')
    if name:
        args.extend(['--name', str(name)])

    detach = params.get('detach', True)
    if detach:
        args.append('--detach')

    remove = params.get('remove', False)
    if remove:
        args.append('--rm')

    network = params.get('network')
    if network:
        args.extend(['--network', str(network)])

    # Port mappings: {"8080": "80", "443": "443"}
    ports = params.get('ports') or {}
    if isinstance(ports, dict):
        for host_port, container_port in ports.items():
            args.extend(['-p', '%s:%s' % (str(host_port), str(container_port))])

    # Volume mappings: {"/host/path": "/container/path"}
    volumes = params.get('volumes') or {}
    if isinstance(volumes, dict):
        for host_path, container_path in volumes.items():
            args.extend(['-v', '%s:%s' % (str(host_path), str(container_path))])

    # Environment variables: {"KEY": "VALUE"}
    env = params.get('env') or {}
    if isinstance(env, dict):
        for key, value in env.items():
            args.extend(['-e', '%s=%s' % (str(key), str(value))])

    image = params['image']
    args.append(str(image))

    command = params.get('command')
    if command:
        if isinstance(command, str):
            args.extend(command.split())
        elif isinstance(command, list):
            args.extend([str(c) for c in command])

    return args


@register_module(
    module_id='docker.run',
    version='1.0.0',
    category='docker',
    tags=['docker', 'container', 'run', 'deploy', 'devops'],
    label='Run Docker Container',
    label_key='modules.docker.run.label',
    description='Run a Docker container from an image',
    description_key='modules.docker.run.description',
    icon='Container',
    color='#0DB7ED',
    input_types=['string', 'object'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['docker.run'],

    params_schema=compose(
        field(
            'image',
            type='string',
            label='Image',
            label_key='modules.docker.run.params.image.label',
            description='Docker image to run (e.g. nginx:latest)',
            description_key='modules.docker.run.params.image.description',
            placeholder='nginx:latest',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'command',
            type='string',
            label='Command',
            label_key='modules.docker.run.params.command.label',
            description='Command to run inside the container',
            description_key='modules.docker.run.params.command.description',
            placeholder='echo hello',
            group=FieldGroup.BASIC,
        ),
        field(
            'name',
            type='string',
            label='Container Name',
            label_key='modules.docker.run.params.name.label',
            description='Assign a name to the container',
            description_key='modules.docker.run.params.name.description',
            placeholder='my-container',
            group=FieldGroup.BASIC,
        ),
        field(
            'ports',
            type='object',
            label='Port Mappings',
            label_key='modules.docker.run.params.ports.label',
            description='Port mappings as host:container (e.g. {"8080": "80"})',
            description_key='modules.docker.run.params.ports.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'volumes',
            type='object',
            label='Volume Mappings',
            label_key='modules.docker.run.params.volumes.label',
            description='Volume mappings as host_path:container_path',
            description_key='modules.docker.run.params.volumes.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'env',
            type='object',
            label='Environment Variables',
            label_key='modules.docker.run.params.env.label',
            description='Environment variables to set in the container',
            description_key='modules.docker.run.params.env.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'detach',
            type='boolean',
            label='Detach',
            label_key='modules.docker.run.params.detach.label',
            description='Run container in background',
            description_key='modules.docker.run.params.detach.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'remove',
            type='boolean',
            label='Auto Remove',
            label_key='modules.docker.run.params.remove.label',
            description='Automatically remove the container when it exits',
            description_key='modules.docker.run.params.remove.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'network',
            type='string',
            label='Network',
            label_key='modules.docker.run.params.network.label',
            description='Connect the container to a network',
            description_key='modules.docker.run.params.network.description',
            placeholder='bridge',
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'container_id': {
            'type': 'string',
            'description': 'ID of the created container',
            'description_key': 'modules.docker.run.output.container_id.description',
        },
        'status': {
            'type': 'string',
            'description': 'Container status after run',
            'description_key': 'modules.docker.run.output.status.description',
        },
    },
    examples=[
        {
            'title': 'Run Nginx web server',
            'params': {
                'image': 'nginx:latest',
                'name': 'my-nginx',
                'ports': {'8080': '80'},
                'detach': True,
            },
        },
        {
            'title': 'Run a one-off command',
            'params': {
                'image': 'alpine:latest',
                'command': 'echo hello world',
                'remove': True,
                'detach': False,
            },
        },
    ],
    timeout_ms=120000,
)
async def docker_run(context: Dict[str, Any]) -> Dict[str, Any]:
    """Run a Docker container from an image."""
    params = context.get('params', {})

    image = params.get('image')
    if not image:
        raise ValidationError("Missing required parameter: image", field="image")

    args = _build_run_args(params)
    detach = params.get('detach', True)

    logger.info("Docker run: %s", ' '.join(args))

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=110,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ModuleError("Docker run timed out after 110 seconds")

        stdout = stdout_bytes.decode('utf-8', errors='replace').strip()
        stderr = stderr_bytes.decode('utf-8', errors='replace').strip()

        if process.returncode != 0:
            error_msg = stderr if stderr else stdout
            raise ModuleError(
                "Docker run failed (exit code %d): %s" % (process.returncode, error_msg)
            )

        container_id = stdout[:12] if detach and stdout else stdout
        status = 'running' if detach else 'exited'

        return {
            'ok': True,
            'data': {
                'container_id': container_id,
                'status': status,
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker run error: %s", e)
        raise ModuleError("Docker run failed: %s" % str(e))
