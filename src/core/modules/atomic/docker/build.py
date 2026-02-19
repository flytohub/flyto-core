# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Build Module
Build a Docker image from a Dockerfile
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _build_build_args(params: Dict[str, Any]) -> List[str]:
    """Build docker build CLI arguments from params."""
    args = ['docker', 'build']

    tag = params.get('tag')
    if tag:
        args.extend(['-t', str(tag)])

    dockerfile = params.get('dockerfile')
    if dockerfile:
        args.extend(['-f', str(dockerfile)])

    no_cache = params.get('no_cache', False)
    if no_cache:
        args.append('--no-cache')

    # Build args: {"KEY": "VALUE"}
    build_args = params.get('build_args') or {}
    if isinstance(build_args, dict):
        for key, value in build_args.items():
            args.extend(['--build-arg', '%s=%s' % (str(key), str(value))])

    path = params.get('path', '.')
    args.append(str(path))

    return args


def _parse_image_id(output: str) -> str:
    """Extract image ID from docker build output."""
    # Look for "Successfully built <id>" or "writing image sha256:<id>"
    for line in reversed(output.splitlines()):
        # Classic build output
        match = re.search(r'Successfully built ([a-f0-9]+)', line)
        if match:
            return match.group(1)
        # BuildKit output
        match = re.search(r'writing image sha256:([a-f0-9]+)', line)
        if match:
            return match.group(1)[:12]
    return ''


@register_module(
    module_id='docker.build',
    version='1.0.0',
    category='docker',
    tags=['docker', 'image', 'build', 'dockerfile', 'devops'],
    label='Build Docker Image',
    label_key='modules.docker.build.label',
    description='Build a Docker image from a Dockerfile',
    description_key='modules.docker.build.description',
    icon='Container',
    color='#0DB7ED',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['docker.build'],

    params_schema=compose(
        field(
            'path',
            type='string',
            label='Build Context',
            label_key='modules.docker.build.params.path.label',
            description='Path to the build context directory',
            description_key='modules.docker.build.params.path.description',
            placeholder='.',
            required=True,
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'tag',
            type='string',
            label='Tag',
            label_key='modules.docker.build.params.tag.label',
            description='Name and optionally tag the image (e.g. myapp:latest)',
            description_key='modules.docker.build.params.tag.description',
            placeholder='myapp:latest',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'dockerfile',
            type='string',
            label='Dockerfile',
            label_key='modules.docker.build.params.dockerfile.label',
            description='Path to the Dockerfile (relative to build context)',
            description_key='modules.docker.build.params.dockerfile.description',
            placeholder='Dockerfile',
            group=FieldGroup.OPTIONS,
            format='path',
        ),
        field(
            'build_args',
            type='object',
            label='Build Arguments',
            label_key='modules.docker.build.params.build_args.label',
            description='Build-time variables (e.g. {"NODE_ENV": "production"})',
            description_key='modules.docker.build.params.build_args.description',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'no_cache',
            type='boolean',
            label='No Cache',
            label_key='modules.docker.build.params.no_cache.label',
            description='Do not use cache when building the image',
            description_key='modules.docker.build.params.no_cache.description',
            default=False,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'image_id': {
            'type': 'string',
            'description': 'ID of the built image',
            'description_key': 'modules.docker.build.output.image_id.description',
        },
        'tag': {
            'type': 'string',
            'description': 'Tag applied to the image',
            'description_key': 'modules.docker.build.output.tag.description',
        },
        'size': {
            'type': 'string',
            'description': 'Size of the built image',
            'description_key': 'modules.docker.build.output.size.description',
        },
    },
    examples=[
        {
            'title': 'Build from current directory',
            'params': {
                'path': '.',
                'tag': 'myapp:latest',
            },
        },
        {
            'title': 'Build with custom Dockerfile and args',
            'params': {
                'path': './backend',
                'tag': 'myapi:v1.0',
                'dockerfile': 'Dockerfile.prod',
                'build_args': {'NODE_ENV': 'production'},
                'no_cache': True,
            },
        },
    ],
    timeout_ms=600000,
)
async def docker_build(context: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Docker image from a Dockerfile."""
    params = context.get('params', {})

    path = params.get('path')
    if not path:
        raise ValidationError("Missing required parameter: path", field="path")

    tag = params.get('tag')
    if not tag:
        raise ValidationError("Missing required parameter: tag", field="tag")

    args = _build_build_args(params)

    logger.info("Docker build: %s", ' '.join(args))

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=580,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise ModuleError("Docker build timed out")

        stdout = stdout_bytes.decode('utf-8', errors='replace').strip()
        stderr = stderr_bytes.decode('utf-8', errors='replace').strip()

        # Docker build sends progress to stdout or stderr depending on BuildKit
        combined_output = stdout + '\n' + stderr

        if process.returncode != 0:
            # Truncate error output for readability
            error_msg = stderr if stderr else stdout
            if len(error_msg) > 500:
                error_msg = error_msg[-500:]
            raise ModuleError(
                "Docker build failed (exit code %d): %s" % (process.returncode, error_msg)
            )

        image_id = _parse_image_id(combined_output)

        # Try to get image size via docker inspect
        size = ''
        try:
            inspect_proc = await asyncio.create_subprocess_exec(
                'docker', 'image', 'inspect', str(tag),
                '--format', '{{.Size}}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            inspect_stdout, _ = await asyncio.wait_for(
                inspect_proc.communicate(),
                timeout=10,
            )
            if inspect_proc.returncode == 0 and inspect_stdout:
                size_bytes = inspect_stdout.decode('utf-8', errors='replace').strip()
                try:
                    size_int = int(size_bytes)
                    if size_int >= 1073741824:
                        size = '%.2f GB' % (size_int / 1073741824)
                    elif size_int >= 1048576:
                        size = '%.1f MB' % (size_int / 1048576)
                    else:
                        size = '%.1f KB' % (size_int / 1024)
                except ValueError:
                    size = size_bytes
        except Exception:
            pass

        return {
            'ok': True,
            'data': {
                'image_id': image_id,
                'tag': str(tag),
                'size': size,
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker build error: %s", e)
        raise ModuleError("Docker build failed: %s" % str(e))
