# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Shell Execute Module
Execute shell commands with full control over environment and output

WHAT THIS MODULE IS ABLE TO CLAIM (see core/engine/outcome.py)

Every return from `shell_exec` carries an outcome envelope, and the highest
rung any of them reaches is OBSERVED. That ceiling is not modesty, it is what
the code measures:

  * `process.returncode`, read after `communicate()` returns, is a real
    measurement of a real state change -- a child process was spawned, it ran,
    it terminated, and these are the bytes it wrote. `ceiling_for`'s own
    docstring names "a process exit code" as the example of an honest OBSERVED.

  * It is not, and can never be here, a VERIFIED. `exit 0` from a script that
    wrote no file proves the process ended and nothing whatsoever about the
    effect the caller wanted. VERIFIED requires a declared postcondition that
    was evaluated; `register_module` accepts a `postcondition=` kwarg now, but
    this module declares none and has no parameter through which a caller could
    state what the command was supposed to achieve, so nothing here evaluates a
    predicate. `ceiling_for(None)` is OBSERVED.

There are FIVE return shapes below, not one, and each gets its own envelope.
Four of them are error returns, and a consumer that found the envelope only on
the success path would KeyError on every failure -- exactly the shape of
result a ladder exists to describe. The reasoning for each rung is written at
the return it belongs to.
"""

import asyncio
import logging
import os
import shlex
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets

logger = logging.getLogger(__name__)

# Allowlist of safe command base names
_ALLOWED_COMMANDS = frozenset({
    'node', 'npm', 'npx', 'yarn', 'pnpm', 'bun',
    'git', 'python', 'python3', 'pip', 'pip3', 'pytest',
    'cat', 'ls', 'find', 'grep', 'head', 'tail', 'wc', 'echo', 'pwd', 'which',
    'tsc', 'eslint', 'prettier', 'jest', 'vitest',
    'cargo', 'go', 'make', 'env',
    'mkdir', 'cp', 'mv', 'touch', 'sort', 'uniq', 'diff', 'tree',
})


def _validate_command(command: str) -> None:
    """
    Validate a command against the allowlist.
    Extracts the base command name (first token) and checks it.

    Raises:
        ValueError: If the command is not in the allowlist.
    """
    args = shlex.split(command)
    if not args:
        raise ValueError("Empty command")

    # Strip env var prefixes (e.g., "NODE_ENV=production npm run build")
    cmd_token = args[0]
    idx = 0
    while idx < len(args) and '=' in args[idx]:
        idx += 1
    if idx < len(args):
        cmd_token = args[idx]

    base_cmd = os.path.basename(cmd_token)
    if base_cmd not in _ALLOWED_COMMANDS:
        raise ValueError(
            f"Command '{base_cmd}' is not in the allowed commands list. "
            f"Allowed: {', '.join(sorted(_ALLOWED_COMMANDS))}"
        )


@register_module(
    module_id='shell.exec',
    version='1.0.0',
    category='atomic',
    subcategory='shell',
    tags=['shell', 'command', 'exec', 'terminal', 'bash', 'atomic'],
    label='Execute Shell Command',
    label_key='modules.shell.exec.label',
    description='Execute a shell command and capture output',
    description_key='modules.shell.exec.description',
    icon='Terminal',
    color='#1E293B',

    # Connection types
    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['file.*', 'data.*', 'test.*'],
    can_receive_from=['start', 'flow.*'],

    # Execution settings
    timeout_ms=300000,
    retryable=False,
    concurrent_safe=False,  # Shell commands can have race conditions

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['shell.execute'],

    # Schema-driven params
    # SECURITY NOTE: use_shell defaults to False to prevent shell injection attacks.
    # Only enable shell=True when absolutely necessary (e.g., shell features like pipes).
    params_schema=compose(
        presets.COMMAND(required=True, placeholder='npm install'),
        presets.WORKING_DIR(),
        presets.ENV_VARS(),
        presets.TIMEOUT_S(key='timeout', default=300),
        presets.USE_SHELL(default=False),  # SECURITY: Default False to prevent injection
        presets.CAPTURE_STDERR(default=True),
        presets.ENCODING(default='utf-8'),
        presets.RAISE_ON_ERROR(default=False),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether command executed successfully (exit code 0)'
        ,
                'description_key': 'modules.shell.exec.output.ok.description'},
        'exit_code': {
            'type': 'number',
            'description': 'Command exit code'
        ,
                'description_key': 'modules.shell.exec.output.exit_code.description'},
        'stdout': {
            'type': 'string',
            'description': 'Standard output'
        ,
                'description_key': 'modules.shell.exec.output.stdout.description'},
        'stderr': {
            'type': 'string',
            'description': 'Standard error output'
        ,
                'description_key': 'modules.shell.exec.output.stderr.description'},
        'command': {
            'type': 'string',
            'description': 'The executed command'
        ,
                'description_key': 'modules.shell.exec.output.command.description'},
        'cwd': {
            'type': 'string',
            'description': 'Working directory used'
        ,
                'description_key': 'modules.shell.exec.output.cwd.description'},
        'duration_ms': {
            'type': 'number',
            'description': 'Execution duration in milliseconds'
        ,
                'description_key': 'modules.shell.exec.output.duration_ms.description'},
        # Declared so it is visible to consumers that map outputs from
        # metadata. Present on every return this module makes, including all
        # four error returns -- which is why it is declared once here rather
        # than described as a success-only field.
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: rung, claim_by, postcondition, '
                'effects, evidence_ref. Never higher than "observed" for this module.'
            ),
            'description_key': 'modules.shell.exec.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Run npm install',
            'title_key': 'modules.shell.exec.examples.npm.title',
            'params': {
                'command': 'npm install',
                'cwd': './my-project'
            }
        },
        {
            'title': 'Run tests with pytest',
            'title_key': 'modules.shell.exec.examples.pytest.title',
            'params': {
                'command': 'python -m pytest tests/ -v',
                'timeout': 120
            }
        },
        {
            'title': 'Git status',
            'title_key': 'modules.shell.exec.examples.git.title',
            'params': {
                'command': 'git status --porcelain'
            }
        },
        {
            'title': 'Build project',
            'title_key': 'modules.shell.exec.examples.build.title',
            'params': {
                'command': 'npm run build',
                'cwd': './frontend',
                'env': {'NODE_ENV': 'production'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def shell_exec(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a shell command and capture output"""
    import time

    params = context['params']
    command = params['command']
    cwd = params.get('cwd')
    env_vars = params.get('env', {})
    timeout_seconds = params.get('timeout', 300)
    capture_stderr = params.get('capture_stderr', True)
    encoding = params.get('encoding', 'utf-8')
    raise_on_error = params.get('raise_on_error', False)

    # SECURITY: Validate command against allowlist
    try:
        _validate_command(command)
    except ValueError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'COMMAND_NOT_ALLOWED',
            'command': command,
            # FAILED, and specifically not INDETERMINATE. The refusal happens
            # above `create_subprocess_exec`, so no child was spawned and there
            # is no uncertainty to report: "definitely no effect" and "we
            # cannot say" are different answers, and only one of them is true
            # here. `effects` is empty because nothing about the world changed.
            # claim_by is NONE -- nobody's expectation was adjudicated, the
            # request was refused before one could be.
            'outcome': envelope(Outcome.FAILED),
        }

    # Resolve working directory
    if cwd:
        cwd = os.path.abspath(os.path.expanduser(cwd))
        if not os.path.isdir(cwd):
            return {
                'ok': False,
                'error': f'Working directory does not exist: {cwd}',
                'error_code': 'INVALID_CWD',
                # Same reasoning as COMMAND_NOT_ALLOWED: os.path.isdir said no
                # before anything was spawned, so nothing ran and we know it.
                # (This return also omits `command` and `duration_ms`, which
                # every other return carries. That predates the envelope and is
                # left alone here rather than changed under cover of this work.)
                'outcome': envelope(Outcome.FAILED),
            }
    else:
        cwd = os.getcwd()

    # Prepare environment from a scrubbed allowlist (PATH/HOME/locale/...) plus
    # caller-supplied vars — NOT the full parent env. shell.exec returns the
    # child's stdout to the caller, so inheriting os.environ would let `env`,
    # `cat /proc/self/environ`, or `python -c 'print(os.environ)'` exfiltrate
    # every host secret. Set FLYTO_SANDBOX_INHERIT_ENV=1 to restore inheritance.
    from core.safe_env import build_sandbox_env
    env = build_sandbox_env(env_vars)

    # Prepare stderr handling
    stderr_pipe = asyncio.subprocess.PIPE if capture_stderr else asyncio.subprocess.STDOUT

    start_time = time.time()

    # The sentinel the EXECUTION_ERROR handler reads to tell "nothing was ever
    # spawned" from "a child exists and we lost track of it". Those are a
    # FAILED and an INDETERMINATE respectively, and without this they arrive at
    # the same return indistinguishable.
    process = None

    try:
        # SECURITY: Always use exec (no shell) to prevent injection
        args = shlex.split(command)
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr_pipe,
            cwd=cwd,
            env=env
        )

        # Wait for completion with timeout
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                'ok': False,
                'error': f'Command timed out after {timeout_seconds} seconds',
                'error_code': 'TIMEOUT',
                'command': command,
                'cwd': cwd,
                'duration_ms': int((time.time() - start_time) * 1000),
                # The textbook INDETERMINATE, and the one rung on this module
                # that must not be argued down to something tidier. The command
                # was still running when we stopped waiting, and we killed it.
                # Whether it had already done the thing, done half of it, or
                # never got started, nothing here measured -- `communicate()`
                # was cancelled, so even the partial output it had produced is
                # gone with the pipes.
                #
                # FAILED would be a claim that the effect did not happen, and
                # nothing evaluated that. DISPATCHED would be a claim that we
                # know less than we do. The two effects below are what we
                # actually witnessed and all we witnessed: create_subprocess_exec
                # returned a live process, and process.kill()/wait() above
                # ended and reaped it.
                'outcome': envelope(
                    Outcome.INDETERMINATE,
                    effects=['process_started', 'process_killed'],
                ),
            }

        duration_ms = int((time.time() - start_time) * 1000)

        # Decode output
        stdout = stdout_bytes.decode(encoding, errors='replace') if stdout_bytes else ''
        stderr = stderr_bytes.decode(encoding, errors='replace') if stderr_bytes else ''

        exit_code = process.returncode
        ok = exit_code == 0

        logger.info(
            f"Shell exec: '{command[:50]}...' "
            f"exit_code={exit_code} duration={duration_ms}ms"
        )

        # What was measured here, and what it does not prove.
        #
        # `process.returncode` was read from the OS after `communicate()`
        # returned: a child was spawned, it terminated, and `stdout`/`stderr`
        # are the bytes it actually wrote. That is an observation of the world
        # changing, which is precisely what OBSERVED means -- "we saw the world
        # change. Not that the right thing changed."
        #
        # The effects below are named for what was witnessed rather than for
        # what the caller wanted. A process exiting is not "the file was
        # written"; it is a process exiting. Nothing in this module can see the
        # difference between `touch out.txt` and `true`.
        effects = ['process_exited']
        if stdout:
            effects.append('stdout')
        if stderr:
            effects.append('stderr')

        # A NON-ZERO EXIT IS NOT REPORTED AS FAILED, deliberately.
        #
        # FAILED means a postcondition was evaluated and did not hold. The only
        # predicate evaluated on this path is the `ok = exit_code == 0` above,
        # and that predicate is an inference of OURS about what the caller wanted,
        # not a contract the caller stated -- there is no parameter through
        # which they could have stated one. outcome.py's rule for an inference
        # that comes up short is INDETERMINATE, not FAILED, and it is the right
        # rule twice over here:
        #
        #   * The inference is simply wrong for several allowlisted commands.
        #     `grep` exits 1 for "no match" and `diff` exits 1 for "the files
        #     differ" -- both after running exactly as intended. Calling those
        #     FAILED would report a broken contract where there is an answer.
        #
        #   * Even when the command really did fail, we do not know that
        #     nothing happened. An `npm install` that exits 1 can leave
        #     node_modules half-written; a `cp` killed mid-copy leaves a
        #     truncated file. "It worked" and "nothing happened" are both
        #     unsupportable, which is the definition of INDETERMINATE.
        #
        # claim_by=INFERRED records whose expectation that was, so a consumer
        # can see the judgement was the module's own and not the caller's. On
        # the exit-0 branch nobody claimed anything at all, so it stays NONE.
        result = {
            'ok': ok,
            'exit_code': exit_code,
            'stdout': stdout,
            'stderr': stderr,
            'command': command,
            'cwd': cwd,
            'duration_ms': duration_ms,
            'outcome': envelope(
                Outcome.OBSERVED if ok else Outcome.INDETERMINATE,
                claim_by=ClaimBy.NONE if ok else ClaimBy.INFERRED,
                effects=effects,
            ),
        }

        if raise_on_error and not ok:
            error_msg = stderr if stderr else stdout
            raise RuntimeError(
                f"Command failed with exit code {exit_code}: {error_msg[:200]}"
            )

        return result

    except Exception as e:
        if isinstance(e, RuntimeError) and raise_on_error:
            raise

        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Shell exec failed: {e}")

        # Two different answers arrive at this one return and they are not
        # interchangeable, so the sentinel set before the try block decides
        # between them.
        #
        # `process` is still None whenever the failure happened before
        # create_subprocess_exec returned: shlex.split on an unbalanced quote,
        # FileNotFoundError for a command that is on the allowlist but not on
        # this host, PermissionError on the cwd. Nothing ran, we know it ran,
        # and that certainty is what makes it FAILED rather than a shrug.
        #
        # Once `process` is bound a child exists, and this handler cannot say
        # what it did. An exception raised after the spawn -- a bogus
        # `encoding` reaching .decode is the reachable case -- severs the
        # observation channel while the command was already underway, which is
        # named in outcome.py as an INDETERMINATE in its own right.
        spawned = process is not None

        return {
            'ok': False,
            'error': str(e),
            'error_code': 'EXECUTION_ERROR',
            'command': command,
            'cwd': cwd,
            'duration_ms': duration_ms,
            'outcome': envelope(
                Outcome.INDETERMINATE if spawned else Outcome.FAILED,
                effects=['process_started'] if spawned else [],
            ),
        }
