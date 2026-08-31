# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Process Start Module
Start and manage background processes (dev servers, services, etc.)

HOW FAR THIS MODULE FOLLOWS REALITY

Five return paths, and what separates them is `wait_for_output` -- the one
parameter through which a caller states what starting successfully means. When
it is set, this module evaluates the caller's predicate ("the child writes this
string to stdout") and the answer is attributable to the caller. When it is
absent, nothing is evaluated at all and the honest claim is much weaker than
the `ok: True` beside it suggests.

  wait_for_output given, string seen          OBSERVED, claimed by the caller
      A line was read off the child's stdout and the caller's substring was in
      it. That is a reading of what the process did, not of what we asked for.
      Not VERIFIED: `register_module` declares no postcondition here, so
      `ceiling_for` caps this module at OBSERVED -- and rightly, because the
      predicate is whatever string the caller happened to pass, not a property
      of starting a process. The predicate travels in `postcondition` anyway so
      a reader can see what was evaluated.

  wait_for_output given, process exited first FAILED, claimed by the caller
      The child is gone and the string never appeared. The caller declared the
      expectation, so a broken one is FAILED and not INDETERMINATE -- this is
      the exact split `outcome.py` describes.

  wait_for_output given, timer expired        INDETERMINATE, claimed by the caller
      The process is still running and we stopped watching. It may print the
      string a second later. We do not know, which is what indeterminate is.

  no wait_for_output                          ACCEPTED
      The kernel returned a pid: the spawn was taken. Nothing has been read
      back. `sh -c 'nosuchcommand'` reaches this return with `ok: True` and a
      pid, having already exited 127. A liveness probe would not fix that --
      `os.kill(pid, 0)` succeeds for a zombie -- so nothing here is observed
      and nothing is claimed to be.

  the working directory does not exist        FAILED, nothing spawned
      No effects at all: `create_subprocess_shell` is never reached.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


def _waited_for(wait_for_output: Optional[str], wait_timeout: Any) -> str:
    """The caller's predicate, written out so a reader can see what was tested."""
    return (
        'the process writes %r to stdout within %s seconds'
        % (wait_for_output, wait_timeout)
    )

# Global process registry for tracking started processes
_process_registry: Dict[str, Dict[str, Any]] = {}


def get_process_registry() -> Dict[str, Dict[str, Any]]:
    """Get the global process registry"""
    return _process_registry


@register_module(
    module_id='process.start',
    version='1.0.0',
    category='atomic',
    subcategory='process',
    tags=['process', 'background', 'server', 'service', 'daemon', 'atomic'],
    label='Start Background Process',
    label_key='modules.process.start.label',
    description='Start a background process (server, service, etc.)',
    description_key='modules.process.start.description',
    icon='Play',
    color='#22C55E',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['port.*', 'process.*', 'test.*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=False,  # Process management requires sequential execution

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['shell.execute'],

    # Schema-driven params
    params_schema=compose(
        presets.COMMAND(required=True, placeholder='npm run dev'),
        presets.WORKING_DIR(),
        presets.ENV_VARS(),
        presets.PROCESS_NAME(placeholder='dev-server'),
        presets.WAIT_FOR_OUTPUT(placeholder='ready on'),
        presets.TIMEOUT_S(key='wait_timeout', default=60, label='Wait Timeout (seconds)'),
        presets.CAPTURE_OUTPUT(default=True),
        presets.LOG_FILE(),
        presets.AUTO_RESTART(default=False),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether process started successfully'
        ,
                'description_key': 'modules.process.start.output.ok.description'},
        'pid': {
            'type': 'number',
            'description': 'Process ID'
        ,
                'description_key': 'modules.process.start.output.pid.description'},
        'process_id': {
            'type': 'string',
            'description': 'Internal process identifier for process.stop'
        ,
                'description_key': 'modules.process.start.output.process_id.description'},
        'name': {
            'type': 'string',
            'description': 'Process name'
        ,
                'description_key': 'modules.process.start.output.name.description'},
        'command': {
            'type': 'string',
            'description': 'The executed command'
        ,
                'description_key': 'modules.process.start.output.command.description'},
        'cwd': {
            'type': 'string',
            'description': 'Working directory'
        ,
                'description_key': 'modules.process.start.output.cwd.description'},
        'started_at': {
            'type': 'string',
            'description': 'ISO timestamp when process started'
        ,
                'description_key': 'modules.process.start.output.started_at.description'},
        'initial_output': {
            'type': 'string',
            'description': 'Initial stdout output (if wait_for_output was used)'
        ,
                'description_key': 'modules.process.start.output.initial_output.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the start was followed: observed when wait_for_output '
                'was seen on the child stdout, accepted when only a pid came '
                'back, failed when the process exited before the expected '
                'output, indeterminate when the wait expired with it still '
                'running'
            ),
            'description_key': 'modules.process.start.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Start dev server',
            'title_key': 'modules.process.start.examples.dev.title',
            'params': {
                'command': 'npm run dev',
                'cwd': './frontend',
                'name': 'frontend-dev',
                'wait_for_output': 'ready on',
                'wait_timeout': 30
            }
        },
        {
            'title': 'Start Python HTTP server',
            'title_key': 'modules.process.start.examples.python.title',
            'params': {
                'command': 'python -m http.server 8000',
                'name': 'static-server'
            }
        },
        {
            'title': 'Start with environment',
            'title_key': 'modules.process.start.examples.env.title',
            'params': {
                'command': 'node server.js',
                'env': {'PORT': '3000', 'NODE_ENV': 'test'},
                'name': 'api-server',
                'wait_for_output': 'listening'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def process_start(context: Dict[str, Any]) -> Dict[str, Any]:
    """Start a background process"""
    import uuid
    from datetime import datetime

    params = context['params']
    command = params['command']
    cwd = params.get('cwd')
    env_vars = params.get('env', {})
    name = params.get('name', f'process-{uuid.uuid4().hex[:8]}')
    wait_for_output = params.get('wait_for_output')
    wait_timeout = params.get('wait_timeout', 60)
    capture_output = params.get('capture_output', True)
    log_file = params.get('log_file')

    # Resolve working directory
    if cwd:
        cwd = os.path.abspath(os.path.expanduser(cwd))
        if not os.path.isdir(cwd):
            return {
                'ok': False,
                'error': f'Working directory does not exist: {cwd}',
                'error_code': 'INVALID_CWD',
                # Empty effects, and not merely few: this returns before
                # `create_subprocess_shell`, so nothing was spawned and nothing
                # outlives the step.
                'outcome': envelope(
                    Outcome.FAILED,
                    claim_by=ClaimBy.NONE,
                    effects=[],
                ),
            }
    else:
        cwd = os.getcwd()

    # Prepare environment from a scrubbed allowlist (PATH/HOME/locale/...) plus
    # caller-supplied vars — NOT the full parent env. process.start spawns an
    # arbitrary detached shell whose stdout is captured, so inheriting os.environ
    # would hand every host secret to attacker-controlled code. Set
    # FLYTO_SANDBOX_INHERIT_ENV=1 to restore full inheritance.
    from core.safe_env import build_sandbox_env
    env = build_sandbox_env(env_vars)

    # Generate unique process ID
    process_id = f'{name}-{uuid.uuid4().hex[:8]}'

    # Open log file if specified
    log_handle = None
    if log_file:
        # Hardening, not a privilege boundary: this module already holds
        # shell.execute, so `command` can write anywhere log_file could reach.
        # The substring '..' check it replaces was ineffective anyway (absolute
        # paths sailed through), and routing every write sink through the one
        # sandbox helper is what keeps the coverage test in
        # tests/core/test_write_sink_coverage.py green.
        log_file = validate_path_with_env_config(log_file)
        log_handle = open(log_file, 'a', encoding='utf-8')

    # The sentinel that keeps the failure return honest. An exception before the
    # spawn means nothing is running; one after it means a detached child is
    # loose and this module has just lost its handle on it. Those are FAILED and
    # INDETERMINATE respectively, and without this they would be one return.
    process = None

    try:
        # Start the process
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env,
            start_new_session=True  # Detach from parent process group
        )

        started_at = datetime.utcnow().isoformat() + 'Z'
        initial_output = ''

        # Wait for specific output if requested
        if wait_for_output and capture_output:
            output_buffer = []
            found = False
            start_time = time.time()

            while time.time() - start_time < wait_timeout:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=1.0
                    )
                    if not line:
                        # Process ended
                        break

                    decoded = line.decode('utf-8', errors='replace')
                    output_buffer.append(decoded)

                    if log_handle:
                        log_handle.write(decoded)
                        log_handle.flush()

                    if wait_for_output in decoded:
                        found = True
                        break

                except asyncio.TimeoutError:
                    # Check if process is still running
                    if process.returncode is not None:
                        break
                    continue

            initial_output = ''.join(output_buffer)

            if not found:
                # Process didn't produce expected output
                if process.returncode is not None:
                    return {
                        'ok': False,
                        'error': f'Process exited before outputting "{wait_for_output}"',
                        'error_code': 'PROCESS_EXITED_EARLY',
                        'exit_code': process.returncode,
                        'output': initial_output,
                        # FAILED, because the caller declared the expectation and
                        # it is now settled: the process is gone and cannot print
                        # the string. Nothing here is an inference of ours.
                        'outcome': envelope(
                            Outcome.FAILED,
                            claim_by=ClaimBy.CALLER,
                            postcondition=_waited_for(wait_for_output, wait_timeout),
                            effects=[{
                                'kind': 'process_exited',
                                'pid': process.pid,
                                'exit_code': process.returncode,
                                'output_bytes': len(initial_output),
                                'measured_by': (
                                    'process.returncode, after the stdout reader '
                                    'saw end of file'
                                ),
                            }],
                        ),
                    }
                else:
                    return {
                        'ok': False,
                        'error': f'Timeout waiting for "{wait_for_output}"',
                        'error_code': 'WAIT_TIMEOUT',
                        'output': initial_output,
                        'pid': process.pid,
                        # INDETERMINATE and not FAILED: the process is still
                        # running, so the caller's predicate is not settled --
                        # only our patience ran out. A slow-booting dev server
                        # that prints its banner one second later would be marked
                        # broken by a FAILED here.
                        'outcome': envelope(
                            Outcome.INDETERMINATE,
                            claim_by=ClaimBy.CALLER,
                            postcondition=_waited_for(wait_for_output, wait_timeout),
                            effects=[
                                {
                                    'kind': 'process_started',
                                    'pid': process.pid,
                                    'measured_by': (
                                        'pid the OS assigned to the child of '
                                        'create_subprocess_shell'
                                    ),
                                },
                                {
                                    'kind': 'process_not_reaped',
                                    'output_bytes': len(initial_output),
                                    'measured_by': (
                                        'process.returncode was still None when '
                                        'the wait window closed'
                                    ),
                                    'detail': (
                                        'Not proof the child is alive: the '
                                        'returncode is set by the event loop\'s '
                                        'child watcher and can lag a real exit. '
                                        'The child is also never registered on '
                                        'this path, so the pid above is the only '
                                        'handle anything has on it.'
                                    ),
                                },
                            ],
                        ),
                    }

        # Register the process
        _process_registry[process_id] = {
            'process': process,
            'pid': process.pid,
            'name': name,
            'command': command,
            'cwd': cwd,
            'started_at': started_at,
            'log_handle': log_handle,
            'capture_output': capture_output
        }

        # Start background output reader if capturing
        if capture_output and not wait_for_output:
            asyncio.create_task(_read_output(process_id, process, log_handle))

        logger.info(f"Started process: {name} (PID: {process.pid})")

        spawned_effect = {
            'kind': 'process_spawned',
            'pid': process.pid,
            'measured_by': (
                'pid the OS assigned to the child of create_subprocess_shell'
            ),
            'detail': (
                'The kernel took the spawn and gave back a pid. It does not say '
                'the command exists or that it is still running: a shell that '
                'exits 127 on a missing binary reaches this line with a pid too.'
            ),
        }

        if wait_for_output and capture_output:
            # The only path in this module where a predicate was evaluated. It
            # was the caller's, and it held.
            outcome = envelope(
                Outcome.OBSERVED,
                claim_by=ClaimBy.CALLER,
                postcondition=_waited_for(wait_for_output, wait_timeout),
                effects=[
                    spawned_effect,
                    {
                        'kind': 'expected_output_seen',
                        'expected': wait_for_output,
                        'output_bytes': len(initial_output),
                        'measured_by': (
                            'substring test against a line read from the child '
                            "process's stdout"
                        ),
                    },
                ],
            )
        else:
            outcome = envelope(
                Outcome.ACCEPTED,
                claim_by=ClaimBy.NONE,
                effects=[spawned_effect],
            )

        return {
            'ok': True,
            'pid': process.pid,
            'process_id': process_id,
            'name': name,
            'command': command,
            'cwd': cwd,
            'started_at': started_at,
            'initial_output': initial_output,
            'outcome': outcome,
        }

    except Exception as e:
        if log_handle:
            log_handle.close()
        logger.error(f"Failed to start process: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'START_FAILED',
            # Two answers from one return, split on whether anything was
            # spawned. FAILED says nothing is running; INDETERMINATE says a
            # detached child exists and this module has just dropped it -- and
            # it is never registered, so nothing can stop it by process_id.
            'outcome': (
                envelope(Outcome.FAILED, claim_by=ClaimBy.NONE, effects=[])
                if process is None
                else envelope(
                    Outcome.INDETERMINATE,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'process_started',
                        'pid': process.pid,
                        'measured_by': (
                            'pid the OS assigned to the child of '
                            'create_subprocess_shell'
                        ),
                        'detail': (
                            'The spawn succeeded and this module then failed. The '
                            'child was never registered, so it is running and '
                            'unreachable.'
                        ),
                    }],
                )
            ),
        }


async def _read_output(process_id: str, process: asyncio.subprocess.Process, log_handle):
    """Background task to read process output"""
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            if log_handle:
                decoded = line.decode('utf-8', errors='replace')
                log_handle.write(decoded)
                log_handle.flush()

    except Exception as e:
        logger.debug(f"Output reader for {process_id} ended: {e}")

    finally:
        if log_handle:
            log_handle.close()

        # Remove from registry when process ends
        if process_id in _process_registry:
            del _process_registry[process_id]
