# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker PS Module
List Docker containers
"""
import asyncio
import json
import logging
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ModuleError

logger = logging.getLogger(__name__)


def _parse_container_line(line: str) -> Dict[str, Any]:
    """Parse a single JSON line from docker ps --format json."""
    try:
        raw = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return {}

    return {
        'id': raw.get('ID', ''),
        'name': raw.get('Names', ''),
        'image': raw.get('Image', ''),
        'status': raw.get('Status', ''),
        'ports': raw.get('Ports', ''),
        'state': raw.get('State', ''),
        'created': raw.get('CreatedAt', ''),
    }


@register_module(
    module_id='docker.ps',
    version='1.0.0',
    category='docker',
    tags=['docker', 'container', 'list', 'ps', 'devops'],
    label='List Docker Containers',
    label_key='modules.docker.ps.label',
    description='List Docker containers',
    description_key='modules.docker.ps.description',
    icon='Container',
    color='#0DB7ED',
    input_types=[],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['docker.read'],

    params_schema=compose(
        field(
            'all',
            type='boolean',
            label='Show All',
            label_key='modules.docker.ps.params.all.label',
            description='Show all containers (default shows just running)',
            description_key='modules.docker.ps.params.all.description',
            default=False,
            group=FieldGroup.BASIC,
        ),
        field(
            'filters',
            type='object',
            label='Filters',
            label_key='modules.docker.ps.params.filters.label',
            description='Filter containers (e.g. {"name": "my-app", "status": "running"})',
            description_key='modules.docker.ps.params.filters.description',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'containers': {
            'type': 'array',
            'description': 'List of containers with id, name, image, status, ports',
            'description_key': 'modules.docker.ps.output.containers.description',
        },
        'count': {
            'type': 'number',
            'description': 'Number of containers found',
            'description_key': 'modules.docker.ps.output.count.description',
        },
    },
    examples=[
        {
            'title': 'List running containers',
            'params': {},
        },
        {
            'title': 'List all containers',
            'params': {'all': True},
        },
        {
            'title': 'Filter by name',
            'params': {'filters': {'name': 'nginx'}},
        },
    ],
    timeout_ms=30000,
)
async def docker_ps(context: Dict[str, Any]) -> Dict[str, Any]:
    """List Docker containers."""
    params = context.get('params', {})

    show_all = params.get('all', False)
    filters = params.get('filters') or {}

    args = ['docker', 'ps', '--format', '{{json .}}', '--no-trunc']

    if show_all:
        args.append('--all')

    if isinstance(filters, dict):
        for key, value in filters.items():
            args.extend(['--filter', '%s=%s' % (str(key), str(value))])

    logger.info("Docker ps: %s", ' '.join(args))

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=25,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ModuleError("Docker ps timed out")

        stdout = stdout_bytes.decode('utf-8', errors='replace').strip()
        stderr = stderr_bytes.decode('utf-8', errors='replace').strip()

        if process.returncode != 0:
            error_msg = stderr if stderr else stdout
            raise ModuleError(
                "Docker ps failed (exit code %d): %s" % (process.returncode, error_msg)
            )

        containers: List[Dict[str, Any]] = []
        if stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parsed = _parse_container_line(line)
                if parsed:
                    containers.append(parsed)

        return {
            'ok': True,
            'data': {
                'containers': containers,
                'count': len(containers),
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker ps error: %s", e)
        raise ModuleError("Docker ps failed: %s" % str(e))
