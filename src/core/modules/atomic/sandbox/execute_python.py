# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Sandbox Execute Python Module
Execute Python code safely in a subprocess with timeout.

HOW FAR THIS MODULE FOLLOWS REALITY

Two returns, and both of them say `ok: True`. That is the whole reason this
module needs an envelope: a consumer reading `ok` cannot tell them apart.

  the process exited                          OBSERVED
      `proc.returncode` is the status the kernel recorded for a child that has
      been reaped, and stdout/stderr are the bytes it actually wrote. None of
      it is derivable from `code`.

      OBSERVED for a non-zero exit too, which is where this differs from
      `shell.exec`. `shell.exec` calls a non-zero exit INDETERMINATE because it
      sets `ok: False` from it -- an inference about what the caller wanted,
      which is wrong for a `grep` that exits 1 having worked perfectly. This
      module infers nothing: it reports the code and leaves `ok` True either
      way, so there is no inference to be unsure about. What was observed is
      that the process ran and ended with that status.

  the timeout killed it                       INDETERMINATE
      We stopped waiting and killed the child. It may have finished the work
      and died mid-print; it may have done nothing. `exit_code: -1` and the
      empty `stdout` in that return are written in this file, not measured --
      `wait_for` cancelled `communicate()` and its buffers went with it. This
      is the textbook indeterminate: we do not know whether it happened.

The `ModuleError` path raises rather than returns, so there is no dict to carry
an envelope. Nothing is claimed there and nothing can be.
"""
import asyncio
import logging
import os
import sys
import tempfile
import time
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError
from .safe_env import build_sandbox_env

logger = logging.getLogger(__name__)


def _exited_outcome(*, exit_code: int, stdout: str, stderr: str) -> Dict[str, Any]:
    """The envelope for a child that ran to completion and was reaped."""
    effects: List[Dict[str, Any]] = [{
        'kind': 'process_exited',
        'exit_code': exit_code,
        'measured_by': 'proc.returncode after communicate() returned',
        'detail': (
            'The status the kernel recorded for the child. It says the code ran '
            'and how it ended; it says nothing about whether it did the right '
            'thing, and no postcondition was evaluated.'
        ),
    }]
    if stdout:
        effects.append({
            'kind': 'stdout',
            'bytes': len(stdout.encode('utf-8', errors='replace')),
            'measured_by': 'bytes read from the child stdout pipe',
        })
    if stderr:
        effects.append({
            'kind': 'stderr',
            'bytes': len(stderr.encode('utf-8', errors='replace')),
            'measured_by': 'bytes read from the child stderr pipe',
        })
    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)


def _timed_out_outcome(*, timeout: int) -> Dict[str, Any]:
    """The envelope for a child we killed because we stopped waiting."""
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'process_started',
                'measured_by': 'the interpreter was spawned by create_subprocess_exec',
            },
            {
                'kind': 'process_killed',
                'after_seconds': timeout,
                'measured_by': 'proc.kill() after asyncio.wait_for timed out',
                'detail': (
                    'Whatever the code had already done, it has done. The '
                    "exit_code of -1 and the empty stdout in this result are this "
                    'module writing defaults, not readings: the pipes died with '
                    'the cancelled communicate().'
                ),
            },
        ],
    )


@register_module(
    module_id='sandbox.execute_python',
    version='1.0.0',
    category='sandbox',
    tags=['sandbox', 'python', 'execute', 'code', 'script'],
    label='Execute Python',
    label_key='modules.sandbox.execute_python.label',
    description='Execute Python code in a subprocess with timeout',
    description_key='modules.sandbox.execute_python.description',
    icon='Terminal',
    color='#EF4444',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=False,
    concurrent_safe=True,
    timeout_ms=30000,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['subprocess.execute'],

    params_schema=compose(
        field(
            'code',
            type='string',
            label='Python Code',
            label_key='modules.sandbox.execute_python.params.code.label',
            description='Python code to execute',
            description_key='modules.sandbox.execute_python.params.code.description',
            required=True,
            placeholder='print("Hello, World!")',
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.sandbox.execute_python.params.timeout.label',
            description='Execution timeout in seconds',
            description_key='modules.sandbox.execute_python.params.timeout.description',
            default=10,
            min=1,
            max=300,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'allowed_modules',
            type='array',
            label='Allowed Modules',
            label_key='modules.sandbox.execute_python.params.allowed_modules.label',
            description='Whitelist of importable modules (leave empty to allow all)',
            description_key='modules.sandbox.execute_python.params.allowed_modules.description',
            items={'type': 'string'},
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'stdout': {
            'type': 'string',
            'description': 'Standard output from the script',
            'description_key': 'modules.sandbox.execute_python.output.stdout.description',
        },
        'stderr': {
            'type': 'string',
            'description': 'Standard error from the script',
            'description_key': 'modules.sandbox.execute_python.output.stderr.description',
        },
        'exit_code': {
            'type': 'number',
            'description': 'Process exit code (0 = success)',
            'description_key': 'modules.sandbox.execute_python.output.exit_code.description',
        },
        'execution_time_ms': {
            'type': 'number',
            'description': 'Execution time in milliseconds',
            'description_key': 'modules.sandbox.execute_python.output.execution_time_ms.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the execution was followed: observed when the process '
                'exited and its status was read, indeterminate when the timeout '
                'killed it. Both returns say ok:true, so this is the field that '
                'tells them apart'
            ),
            'description_key': 'modules.sandbox.execute_python.output.outcome.description',
        },
    },
    examples=[
        {
            'title': 'Simple print',
            'title_key': 'modules.sandbox.execute_python.examples.simple.title',
            'params': {
                'code': 'print("Hello, World!")',
                'timeout': 10,
            },
        },
        {
            'title': 'Math calculation',
            'title_key': 'modules.sandbox.execute_python.examples.math.title',
            'params': {
                'code': 'import math\nprint(math.pi)',
                'allowed_modules': ['math'],
            },
        },
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def sandbox_execute_python(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Python code safely in a subprocess with timeout."""
    params = context['params']
    code = params.get('code', '')
    timeout = int(params.get('timeout', 10))
    allowed_modules = params.get('allowed_modules') or []

    if not code.strip():
        raise ValidationError("Missing required parameter: code", field="code")

    # If allowed_modules is set, prepend an import guard
    if allowed_modules:
        guard_code = _build_import_guard(allowed_modules)
        code = guard_code + code

    # Write code to a temp file
    tmp_fd = None
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.py', prefix='flyto_sandbox_')
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(code)
        tmp_fd = None  # os.fdopen took ownership

        start_time = time.monotonic()

        # Run with a scrubbed environment so attacker code cannot read host
        # secrets from os.environ. Set FLYTO_SANDBOX_INHERIT_ENV=1 to override.
        proc = await asyncio.create_subprocess_exec(
            sys.executable, tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=build_sandbox_env(params.get('env')),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
            return {
                'ok': True,
                'data': {
                    'stdout': '',
                    'stderr': 'Execution timed out after {} seconds'.format(timeout),
                    'exit_code': -1,
                    'execution_time_ms': elapsed_ms,
                    'outcome': _timed_out_outcome(timeout=timeout),
                },
            }

        elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)

        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')
        exit_code = proc.returncode if proc.returncode is not None else -1

        logger.info(
            "Python sandbox execution completed (exit=%d, %.1fms)",
            exit_code, elapsed_ms,
        )

        return {
            'ok': True,
            'data': {
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': exit_code,
                'execution_time_ms': elapsed_ms,
                'outcome': _exited_outcome(
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                ),
            },
        }
    except Exception as e:
        raise ModuleError("Failed to execute Python code: {}".format(str(e)))
    finally:
        # Clean up temp file
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _build_import_guard(allowed_modules: list) -> str:
    """Build a Python import guard that restricts imports to allowed modules."""
    allowed_set = repr(set(allowed_modules))
    newline = '\n'
    lines = [
        'import builtins as _builtins',
        '_original_import = _builtins.__import__',
        '_allowed = ' + allowed_set,
        'def _guarded_import(name, *args, **kwargs):',
        '    top = name.split(".")[0]',
        '    if top not in _allowed and top not in ("builtins", "__future__"):',
        '        raise ImportError("Module not allowed: " + name)',
        '    return _original_import(name, *args, **kwargs)',
        '_builtins.__import__ = _guarded_import',
        '',
    ]
    return newline.join(lines) + newline
