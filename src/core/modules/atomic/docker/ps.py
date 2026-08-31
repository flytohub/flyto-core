# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker PS Module
List Docker containers

HOW FAR THIS MODULE FOLLOWS REALITY

`docker ps` changes nothing, so what the rung reports is the quality of the
reading, and there are three different readings behind one `count`:

  at least one container line parsed          OBSERVED
      Each line is a JSON document the daemon wrote about a container it owns:
      id, image, status, ports. None of it is derivable from this module's
      parameters, and a container that does not exist cannot produce a line.

  the daemon answered with no output          ACCEPTED
      Exit 0 and empty stdout. The daemon took the question and answered it;
      no container state crossed the wire, so there is nothing here that was
      observed. This is the same shape as `database.query`'s empty result set.

  lines came back and none of them parsed     INDETERMINATE
      `_parse_container_line` returns `{}` for anything it cannot read and the
      caller drops it silently, so `count == 0` is reachable with a stdout full
      of container data. That reading is identical to the empty one above while
      meaning the opposite, and neither ACCEPTED nor OBSERVED may rest on it.

The distinction is decided per call from what was actually parsed, never from a
per-module constant: the same daemon gives all three answers.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ModuleError

logger = logging.getLogger(__name__)


def _ps_outcome(*, parsed: int, unreadable: int) -> Dict[str, Any]:
    """The rung this listing earned, and the count that earned it.

    `parsed` is the number of lines that became a container dict; `unreadable`
    is the number the parser dropped. Both are counted at the point of parsing
    rather than recomputed from the output list, so a future change to what is
    considered a valid line moves both numbers together.
    """
    if parsed > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'containers_listed',
                'count': parsed,
                'unreadable_lines': unreadable,
                'measured_by': (
                    'one parsed JSON document per line of `docker ps '
                    "--format '{{json .}}'` stdout"
                ),
                'detail': (
                    'Each line describes a container the daemon holds. This is a '
                    'reading of the daemon at one instant and nothing more: a '
                    'container may have exited between the read and this return.'
                ),
            }],
        )

    if unreadable > 0:
        return envelope(
            Outcome.INDETERMINATE,
            # INFERRED: no caller declared what the output should look like.
            # The expectation that a line of `docker ps` stdout is a JSON object
            # is this module's, and it is the one that did not hold.
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'output_not_readable',
                'unreadable_lines': unreadable,
                'measured_by': None,
                'detail': (
                    'The daemon wrote lines this module could not parse, and they '
                    'were dropped. `count` is 0 for the same reason an empty list '
                    'is 0, so it cannot be read as "no containers".'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'daemon_answered_empty',
            'measured_by': None,
            'detail': (
                'docker exited 0 and wrote nothing. The daemon took the question '
                'and answered; no container state crossed the wire, so nothing '
                'about any container was observed.'
            ),
        }],
    )


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
        'outcome': {
            'type': 'object',
            'description': (
                'How far the reading was followed: observed when container lines '
                'were parsed, accepted when the daemon answered with nothing, '
                'indeterminate when output came back unreadable'
            ),
            'description_key': 'modules.docker.ps.output.outcome.description',
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
        unreadable = 0
        if stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parsed = _parse_container_line(line)
                if parsed:
                    containers.append(parsed)
                else:
                    # Counted, not just skipped. A dropped line is the one thing
                    # that makes `count` mean something other than what it looks
                    # like, and the rung below is decided from it.
                    unreadable += 1

        return {
            'ok': True,
            'data': {
                'containers': containers,
                'count': len(containers),
                'outcome': _ps_outcome(
                    parsed=len(containers),
                    unreadable=unreadable,
                ),
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker ps error: %s", e)
        raise ModuleError("Docker ps failed: %s" % str(e))
