# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Stop Module
Stop a running Docker container

HOW FAR THIS MODULE FOLLOWS REALITY -- ACCEPTED, on its one return path

`stopped: True` is a literal written in this file. It is True on every path
that returns at all, because every other path raises, so it carries no
information: it would read exactly the same if nothing had stopped.

What is real is the exit status. `docker stop <ref>` exits non-zero for a
container that does not exist, and it does not return until the daemon has
finished stopping the container -- so exit 0 is the daemon saying it did the
work. That is "the other side acknowledged taking it", which is ACCEPTED, and
it is where this module stops.

Why not OBSERVED. Nothing here reads the container back. The obvious read-back
is not obviously right either: `docker stop` on a `--rm` container removes it,
so a follow-up `docker inspect` returns "No such object" -- which is
indistinguishable from a daemon error, an inspect of the wrong reference, or a
typo. Guessing "gone, therefore stopped" from an error string would be an
inference dressed as a measurement, which is worse than the honest ACCEPTED
below. The stdout echo is not a measurement either: it is the reference the
caller passed, echoed, and `container_id` falls back to that same parameter
when stdout is empty.
"""
import asyncio
import logging
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
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
            'description': (
                'Always true when this module returns at all -- every other path '
                'raises. Not a reading of the container; see outcome'
            ),
            'description_key': 'modules.docker.stop.output.stopped.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the stop was followed: accepted, meaning the daemon '
                'acknowledged doing the work by exiting 0. The container is not '
                'read back, so nothing here is observed'
            ),
            'description_key': 'modules.docker.stop.output.outcome.description',
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
                'outcome': envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'stop_command_succeeded',
                        'container': str(container),
                        'echoed_reference': stdout,
                        'measured_by': 'exit status 0 from `docker stop`',
                        'detail': (
                            'The daemon accepted the stop and returned only when it '
                            'had finished with the container. The container itself '
                            'was not read back, so its state now is not observed.'
                        ),
                    }],
                ),
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker stop error: %s", e)
        raise ModuleError("Docker stop failed: %s" % str(e))
