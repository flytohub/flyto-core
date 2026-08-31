# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Run Module
Run a Docker container from an image

WHAT `status` USED TO BE, AND WHY IT NEEDED A READ-BACK

    status = 'running' if detach else 'exited'

That line is `file.write`'s `bytes_written` in another costume: it is a
restatement of a parameter the caller passed in. It reads `'running'` for a
detached container that crashed on its first instruction, for one whose
entrypoint does not exist, and for one the OOM killer took a millisecond after
`docker run` returned -- all identical to the healthy case, because no syscall
and no daemon response contributes to it.

`_observe_container_state` is now the one thing here that measures the world.
It asks the daemon for `State.Status` after the run, which no parameter of this
module can produce. What each answer earns:

  the daemon reported a state for the container      OBSERVED
      `status` is that state -- `running`, `exited`, `created`, `restarting`,
      `paused`, `dead`. Not an inference, and different from the old literal in
      exactly the cases where the old literal was wrong.

  no state could be read                             ACCEPTED
      `status` falls back to the old inference and `status_observed` is False.
      Three ordinary ways to land here, none of which is a failed run: the
      container was `--rm` and is already gone, a non-detached run was given no
      `--name` so there is no reference to inspect by, or the inspect itself
      failed. `docker run` exiting 0 with a container id on stdout is still the
      daemon reporting on its own work, which is ACCEPTED.

A caveat the rung does not hide: OBSERVED is a reading at one instant. A
container observed `running` may exit immediately afterwards, and nothing here
declares a postcondition, so `verified` is unreachable and is not claimed.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
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


async def _observe_container_state(reference: str) -> Tuple[Optional[str], Optional[str]]:
    """``(state, None)`` when the daemon named a state, ``(None, why)`` when not.

    Swallows every exception on purpose: this runs inside the caller's `try`,
    whose `except Exception` turns anything loose into "Docker run failed". A
    container that started and an observation that could not be made are two
    different things, and conflating them would report the first as the second.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            'docker', 'inspect', '--format', '{{.State.Status}}', reference,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=10,
        )
    except asyncio.TimeoutError:
        return None, 'docker inspect did not answer within 10 seconds'
    except Exception as error:
        return None, '%s: %s' % (type(error).__name__, error)

    if process.returncode != 0:
        detail = stderr_bytes.decode('utf-8', errors='replace').strip()
        return None, 'docker inspect exited %s: %s' % (process.returncode, detail[:200])

    state = stdout_bytes.decode('utf-8', errors='replace').strip()
    if not state:
        return None, 'docker inspect reported an empty state'
    return state, None


def _run_outcome(
    *,
    container_id: str,
    reference: str,
    observed_state: Optional[str],
    observation_error: Optional[str],
    inferred_status: str,
) -> Dict[str, Any]:
    """The rung this run earned, and the measurement that earned it."""
    accepted_effect = {
        'kind': 'run_command_succeeded',
        'container_id': container_id,
        'measured_by': 'exit status 0 from `docker run`, and its stdout',
        'detail': (
            'The daemon reports that it created and started the container. That '
            'is the daemon describing its own work, not a reading of what the '
            'container is doing now.'
        ),
    }

    if observed_state is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                accepted_effect,
                {
                    'kind': 'container_state_not_observed',
                    'measured_by': None,
                    'reason': observation_error or (
                        'no container reference to inspect: the run was not '
                        'detached and no name was given'
                    ),
                    'inferred_status': inferred_status,
                    'detail': (
                        'The `status` field on this result is inferred from the '
                        '`detach` parameter, not read from the daemon. It says '
                        "'running' for a container that has already crashed."
                    ),
                },
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[
            accepted_effect,
            {
                'kind': 'container_state_observed',
                'state': observed_state,
                'reference': reference,
                'measured_by': (
                    'docker inspect --format {{.State.Status}}, after the run'
                ),
                'detail': (
                    "The daemon's own state for this container, read back after "
                    'the run returned. True at the instant of the read and not '
                    'guaranteed afterwards.'
                ),
            },
        ],
    )


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
            'description': (
                'Container state read back from the daemon after the run '
                '(running, exited, created, ...). Falls back to a guess from the '
                'detach parameter when no read-back was possible -- see '
                'status_observed'
            ),
            'description_key': 'modules.docker.run.output.status.description',
        },
        'status_observed': {
            'type': 'boolean',
            'description': (
                'True when status came from docker inspect, false when it is '
                'inferred from the detach parameter and measures nothing'
            ),
            'description_key': 'modules.docker.run.output.status_observed.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the run was followed: observed when the container state '
                'was read back from the daemon, accepted when only docker run '
                'itself reported success'
            ),
            'description_key': 'modules.docker.run.output.outcome.description',
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
        inferred_status = 'running' if detach else 'exited'

        # What we can name the container by, in order of what is actually a
        # container reference. A detached run prints the id; a foreground run
        # prints the CONTAINER'S OWN OUTPUT, which is not a reference to
        # anything, so `--name` is the only handle left.
        if detach and container_id:
            reference = container_id
        else:
            reference = str(params.get('name') or '')

        observed_state, observation_error = (
            await _observe_container_state(reference) if reference else (None, None)
        )

        return {
            'ok': True,
            'data': {
                'container_id': container_id,
                'status': observed_state or inferred_status,
                'status_observed': observed_state is not None,
                'outcome': _run_outcome(
                    container_id=container_id,
                    reference=reference,
                    observed_state=observed_state,
                    observation_error=observation_error,
                    inferred_status=inferred_status,
                ),
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker run error: %s", e)
        raise ModuleError("Docker run failed: %s" % str(e))
