# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Inspect Module
Inspect a Docker container's detailed configuration and state

HOW FAR THIS MODULE FOLLOWS REALITY

Two rungs, and the thing that separates them is whether the document the daemon
returned was about a container at all.

  the document carries a `State` object        OBSERVED
      `State.Status`, `State.Running`, `State.Pid`, `StartedAt` and the network
      addresses are the daemon's reading of a container it is running. Nothing
      in the payload is derivable from the `container` parameter, and a
      container that does not exist makes `docker inspect` exit non-zero.

  the document carries no `State`              ACCEPTED
      `docker inspect` resolves images, networks and volumes too, and it does
      so silently: `docker inspect nginx:latest` returns an image document,
      exits 0, and `_extract_inspect_data` then reports `status: ''`,
      `running: False`, `pid: 0` and `exit_code: 0` -- four values written in
      this file, none of them read from anything. They are byte-identical to
      what a stopped container would produce. A rung may not rest on them, so
      the claim falls to "the daemon answered", which is all that happened.
"""
import asyncio
import json
import logging
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _inspect_outcome(raw: Dict[str, Any]) -> Dict[str, Any]:
    """The rung this inspection earned, from what the daemon actually sent.

    The test is `isinstance(raw.get('State'), dict)` and not "the container
    looks running", because the question is whether a reading happened at all,
    not what it said. A container that is `exited` was observed just as much as
    one that is `running`; an image document was not observed at all.
    """
    state = raw.get('State')
    if isinstance(state, dict):
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'container_state_read',
                'status': state.get('Status', ''),
                'running': state.get('Running', False),
                'pid': state.get('Pid', 0),
                'measured_by': 'State object in the `docker inspect` document',
                'detail': (
                    "The daemon's reading of this container at the moment it "
                    'answered. It is not a claim that the container is still in '
                    'that state now, and nothing here was checked against a '
                    'postcondition.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'inspected_object_is_not_a_container',
            'measured_by': None,
            'detail': (
                'docker exited 0 and returned a document with no State object -- '
                'an image, network or volume resolves through `docker inspect` '
                'the same way a container does. Every field under `state` in this '
                "result is this module's default, not a reading."
            ),
        }],
    )


def _extract_inspect_data(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant fields from docker inspect JSON output."""
    state = raw.get('State', {})
    config = raw.get('Config', {})
    network_settings = raw.get('NetworkSettings', {})
    mounts = raw.get('Mounts', [])
    host_config = raw.get('HostConfig', {})

    # Extract network info
    networks = {}
    raw_networks = network_settings.get('Networks', {})
    for net_name, net_info in raw_networks.items():
        networks[net_name] = {
            'ip_address': net_info.get('IPAddress', ''),
            'gateway': net_info.get('Gateway', ''),
            'mac_address': net_info.get('MacAddress', ''),
        }

    # Extract mount info
    mount_list = []
    for mount in mounts:
        mount_list.append({
            'type': mount.get('Type', ''),
            'source': mount.get('Source', ''),
            'destination': mount.get('Destination', ''),
            'mode': mount.get('Mode', ''),
            'rw': mount.get('RW', False),
        })

    # Extract port bindings
    port_bindings = {}
    raw_ports = host_config.get('PortBindings') or {}
    for container_port, bindings in raw_ports.items():
        if bindings:
            host_ports = []
            for binding in bindings:
                hp = binding.get('HostPort', '')
                if hp:
                    host_ports.append(hp)
            port_bindings[container_port] = host_ports

    # Clean container name (remove leading slash)
    name = raw.get('Name', '')
    if name.startswith('/'):
        name = name[1:]

    return {
        'id': raw.get('Id', '')[:12],
        'name': name,
        'state': {
            'status': state.get('Status', ''),
            'running': state.get('Running', False),
            'paused': state.get('Paused', False),
            'restarting': state.get('Restarting', False),
            'pid': state.get('Pid', 0),
            'exit_code': state.get('ExitCode', 0),
            'started_at': state.get('StartedAt', ''),
            'finished_at': state.get('FinishedAt', ''),
        },
        'image': config.get('Image', ''),
        'network_settings': {
            'ip_address': network_settings.get('IPAddress', ''),
            'ports': port_bindings,
            'networks': networks,
        },
        'mounts': mount_list,
        'config': {
            'hostname': config.get('Hostname', ''),
            'env': config.get('Env', []),
            'cmd': config.get('Cmd', []),
            'entrypoint': config.get('Entrypoint', []),
            'working_dir': config.get('WorkingDir', ''),
            'labels': config.get('Labels', {}),
        },
    }


@register_module(
    module_id='docker.inspect_container',
    version='1.0.0',
    category='docker',
    tags=['docker', 'container', 'inspect', 'info', 'details', 'devops'],
    label='Inspect Docker Container',
    label_key='modules.docker.inspect_container.label',
    description='Get detailed information about a Docker container',
    description_key='modules.docker.inspect_container.description',
    icon='Container',
    color='#0DB7ED',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['docker.read'],

    params_schema=compose(
        field(
            'container',
            type='string',
            label='Container',
            label_key='modules.docker.inspect_container.params.container.label',
            description='Container ID or name to inspect',
            description_key='modules.docker.inspect_container.params.container.description',
            placeholder='my-container',
            required=True,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'id': {
            'type': 'string',
            'description': 'Short container ID',
            'description_key': 'modules.docker.inspect_container.output.id.description',
        },
        'name': {
            'type': 'string',
            'description': 'Container name',
            'description_key': 'modules.docker.inspect_container.output.name.description',
        },
        'state': {
            'type': 'object',
            'description': 'Container state (status, running, pid, exit_code, etc.)',
            'description_key': 'modules.docker.inspect_container.output.state.description',
        },
        'image': {
            'type': 'string',
            'description': 'Image used by the container',
            'description_key': 'modules.docker.inspect_container.output.image.description',
        },
        'network_settings': {
            'type': 'object',
            'description': 'Network configuration (IP, ports, networks)',
            'description_key': 'modules.docker.inspect_container.output.network_settings.description',
        },
        'mounts': {
            'type': 'array',
            'description': 'Volume and bind mounts',
            'description_key': 'modules.docker.inspect_container.output.mounts.description',
        },
        'config': {
            'type': 'object',
            'description': 'Container configuration (env, cmd, labels, etc.)',
            'description_key': 'modules.docker.inspect_container.output.config.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the reading was followed: observed when the daemon '
                'returned a container State object, accepted when it returned a '
                'document without one (an image, network or volume)'
            ),
            'description_key': 'modules.docker.inspect_container.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'Inspect a container by name',
            'params': {
                'container': 'my-nginx',
            },
        },
        {
            'title': 'Inspect a container by ID',
            'params': {
                'container': 'a1b2c3d4e5f6',
            },
        },
    ],
    timeout_ms=30000,
)
async def docker_inspect_container(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed information about a Docker container."""
    params = context.get('params', {})

    container = params.get('container')
    if not container:
        raise ValidationError("Missing required parameter: container", field="container")

    args = ['docker', 'inspect', str(container)]

    logger.info("Docker inspect: %s", ' '.join(args))

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
            raise ModuleError("Docker inspect timed out")

        stdout = stdout_bytes.decode('utf-8', errors='replace').strip()
        stderr = stderr_bytes.decode('utf-8', errors='replace').strip()

        if process.returncode != 0:
            error_msg = stderr if stderr else stdout
            raise ModuleError(
                "Docker inspect failed (exit code %d): %s" % (process.returncode, error_msg)
            )

        try:
            inspect_data = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as e:
            raise ModuleError("Failed to parse docker inspect output: %s" % str(e))

        if not inspect_data or not isinstance(inspect_data, list):
            raise ModuleError("Docker inspect returned empty or invalid data")

        raw = inspect_data[0]
        result = _extract_inspect_data(raw)
        result['outcome'] = _inspect_outcome(raw)

        return {
            'ok': True,
            'data': result,
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker inspect error: %s", e)
        raise ModuleError("Docker inspect failed: %s" % str(e))
