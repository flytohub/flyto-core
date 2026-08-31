# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Docker Logs Module
Get container logs

HOW FAR THIS MODULE FOLLOWS REALITY

Three answers behind one return shape, and the third is the one that matters:

  log lines came back                         OBSERVED
      Bytes the container wrote, carried by the daemon's log driver. A
      container that logged nothing cannot produce them.

  the daemon answered with nothing            ACCEPTED
      Exit 0, empty output. `lines == 0` reads identically whether the
      container never logged, the log driver is `none`, or `--tail` cut
      everything off. Nothing about the container was observed.

  follow mode hit the timeout                 INDETERMINATE
      `--follow` streams until killed, so the timeout is the normal end of a
      follow. The module returns `ok: True` with empty logs on that path, which
      a consumer reading only `ok` cannot tell from "this container has no
      logs". It is neither: `asyncio.wait_for` cancels `communicate()`, and
      everything the stream had read is discarded with the cancelled coroutine.
      We do not know what the container logged, which is the definition of
      indeterminate. (See the note at that return: the discard is a real defect
      in follow mode, not something the rung can fix.)
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


def _logs_outcome(*, line_count: int, byte_count: int, follow_timed_out: bool) -> Dict[str, Any]:
    """The rung this read earned, decided per call from what came back."""
    if follow_timed_out:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[
                {
                    'kind': 'log_stream_started',
                    'measured_by': 'the `docker logs --follow` child process was spawned',
                },
                {
                    'kind': 'log_stream_killed',
                    'measured_by': None,
                    'detail': (
                        'The follow was killed at the timeout and whatever it had '
                        'read was lost with the cancelled communicate(). The empty '
                        '`logs` in this result is the absence of a reading, not a '
                        'reading of an absence.'
                    ),
                },
            ],
        )

    if line_count > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'log_lines_read',
                'lines': line_count,
                'bytes': byte_count,
                'measured_by': 'bytes docker wrote to stdout/stderr, split on newlines',
                'detail': (
                    'Output the container produced, as the daemon stored it. '
                    'Bounded by `tail`, so this is a window on the log and not '
                    'the whole of it.'
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
                'docker exited 0 and returned no log content. That reads the same '
                'whether the container logged nothing, its log driver keeps '
                'nothing, or `tail` excluded everything.'
            ),
        }],
    )


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
        'outcome': {
            'type': 'object',
            'description': (
                'How far the read was followed: observed when log lines came '
                'back, accepted when the daemon answered with nothing, '
                'indeterminate when a follow was killed at the timeout'
            ),
            'description_key': 'modules.docker.logs.output.outcome.description',
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

    follow_timed_out = False

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
                #
                # There is nothing to collect. `wait_for` cancelled
                # `communicate()`, and the buffer it had filled died with the
                # coroutine -- so a follow that streams for ten seconds returns
                # exactly as much as one that streams nothing. The two empty
                # strings below are not a reading, and `follow_timed_out`
                # carries that into the envelope so the result stops passing for
                # "this container has no logs".
                follow_timed_out = True
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
                'outcome': _logs_outcome(
                    line_count=line_count,
                    byte_count=len(log_output.encode('utf-8')),
                    follow_timed_out=follow_timed_out,
                ),
            },
        }

    except ModuleError:
        raise
    except Exception as e:
        logger.error("Docker logs error: %s", e)
        raise ModuleError("Docker logs failed: %s" % str(e))
