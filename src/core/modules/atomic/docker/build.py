# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Build Module
Build a Docker image from a Dockerfile

HOW FAR THIS MODULE FOLLOWS REALITY

The read-back that earns the rung was already here before the rung was: the
`docker image inspect <tag> --format {{.Size}}` call below asks the daemon
about its image store after the build, which is a different question from "did
the build command exit 0".

  the daemon reported a size for the tag       OBSERVED
      An integer byte count for `<tag>` in the daemon's store. It cannot be
      produced by a build that stored nothing, and no parameter of this module
      contributes to it.

  it did not                                   ACCEPTED
      Every fallback path -- inspect failed, timed out, or returned something
      that is not an integer -- leaves `size` as the empty string this file
      wrote. `docker build` exiting 0 is the daemon reporting on its own work,
      which is ACCEPTED and no more.

What OBSERVED here does NOT say: that this build produced the image. A fully
cached rebuild exits 0 having created no layer, and the tag it names may have
pointed at an identical image beforehand. The effect is called
`image_present_under_tag` rather than `image_built` for that reason.

`image_id` is parsed out of the build log by `_parse_image_id`, which knows two
output formats and returns `''` for anything else -- so an empty `image_id` is
routine on buildx and is not evidence about the image either way.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
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


async def _observe_image_size(tag: str) -> Tuple[Optional[int], str, Optional[str]]:
    """``(size_in_bytes, raw_text, error)`` from the daemon's image store.

    `size_in_bytes` is None whenever no byte count could be read; `raw_text` is
    whatever the daemon printed, kept because the `size` output field has always
    fallen back to it; `error` says why the number is missing.

    The only line in this module that measures anything other than the exit
    status of the build. It asks the daemon what is in its image store under
    `tag`, after the build has finished -- so a failure here is a failure to
    look, not a failure of the build, and it lowers the rung rather than the
    result.

    Swallows everything on purpose. This runs inside the caller's `try`, whose
    `except Exception` turns anything loose into a failed build, and a broken
    observation must never turn a successful build into an error.
    """
    try:
        inspect_proc = await asyncio.create_subprocess_exec(
            'docker', 'image', 'inspect', str(tag),
            '--format', '{{.Size}}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        inspect_stdout, inspect_stderr = await asyncio.wait_for(
            inspect_proc.communicate(),
            timeout=10,
        )
    except asyncio.TimeoutError:
        return None, '', 'docker image inspect did not answer within 10 seconds'
    except Exception as error:
        return None, '', '%s: %s' % (type(error).__name__, error)

    if inspect_proc.returncode != 0:
        detail = inspect_stderr.decode('utf-8', errors='replace').strip()
        return None, '', 'docker image inspect exited %s: %s' % (
            inspect_proc.returncode, detail[:200],
        )

    reported = inspect_stdout.decode('utf-8', errors='replace').strip()
    try:
        return int(reported), reported, None
    except ValueError:
        # A non-integer is not a size. It is still passed through to the `size`
        # output field, exactly as it always was -- but nothing may be observed
        # on the strength of a value we could not read as a number.
        return None, reported, (
            'docker image inspect returned %r, which is not a byte count' % (
                reported[:80],
            )
        )


def _format_size(size_bytes: int) -> str:
    """Human-readable size, in the units this module has always used."""
    if size_bytes >= 1073741824:
        return '%.2f GB' % (size_bytes / 1073741824)
    if size_bytes >= 1048576:
        return '%.1f MB' % (size_bytes / 1048576)
    return '%.1f KB' % (size_bytes / 1024)


def _build_outcome(
    *,
    tag: str,
    image_id: str,
    size_bytes: Optional[int],
    observation_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this build earned, and the measurement that earned it."""
    built_effect = {
        'kind': 'build_command_succeeded',
        'image_id': image_id,
        'measured_by': 'exit status 0 from `docker build`',
        'detail': (
            'The daemon reports that it built the image. That is the daemon '
            'describing its own work; `image_id` is scraped out of the same '
            "report and is '' whenever the build output is in a format "
            '`_parse_image_id` does not know.'
        ),
    }

    if size_bytes is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                built_effect,
                {
                    'kind': 'image_not_observed',
                    'measured_by': None,
                    'reason': observation_error,
                    'detail': (
                        "The daemon's image store was not read back, so nothing "
                        'here distinguishes a build that stored an image from one '
                        'that reported success and stored nothing.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[
            built_effect,
            {
                'kind': 'image_present_under_tag',
                'tag': tag,
                'size_bytes': size_bytes,
                'measured_by': (
                    'docker image inspect %s --format {{.Size}}, after the build' % tag
                ),
                'detail': (
                    'An image exists under this tag in the daemon store and it is '
                    'this many bytes. NOT a claim that this build created it: a '
                    'fully cached rebuild exits 0 having created no layer, and the '
                    'tag may have pointed at an image beforehand.'
                ),
            },
        ],
    )


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
        'size_bytes': {
            'type': 'number',
            'description': (
                'Byte count the daemon reported for the tag after the build, from '
                'docker image inspect. null when the image store could not be read'
            ),
            'description_key': 'modules.docker.build.output.size_bytes.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the build was followed: observed when the daemon '
                'reported a size for the tag afterwards, accepted when only the '
                'build command itself reported success'
            ),
            'description_key': 'modules.docker.build.output.outcome.description',
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

    # SECURITY: the build context directory is tarred up and shipped to the
    # Docker daemon in full, so an unconfined path exfiltrates every file
    # under it. Holding docker.build is already powerful, but that is not a
    # reason to leave the read boundary off.
    path = validate_path_with_env_config(str(path))

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

        # The read-back. Its answer decides the rung, so it is no longer an
        # optional nicety whose failure disappears into `except Exception: pass`
        # -- the reason it could not answer travels into the envelope instead.
        size_bytes, size_text, observation_error = await _observe_image_size(str(tag))

        if size_bytes is not None:
            size = _format_size(size_bytes)
        else:
            size = size_text

        return {
            'ok': True,
            'data': {
                'image_id': image_id,
                'tag': str(tag),
                'size': size,
                'size_bytes': size_bytes,
                'outcome': _build_outcome(
                    tag=str(tag),
                    image_id=image_id,
                    size_bytes=size_bytes,
                    observation_error=observation_error,
                ),
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker build error: %s", e)
        raise ModuleError("Docker build failed: %s" % str(e))
