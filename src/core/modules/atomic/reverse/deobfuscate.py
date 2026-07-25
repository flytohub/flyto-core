# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Reverse Deobfuscate Module

Real semantic JavaScript deobfuscation (Phase 4 of the reverse-engineering
toolkit): reverses control-flow-flattening, decodes string-array encoding,
bypasses self-defending/debug-protection guards, and unpacks webpack/
browserify bundles, via the `webcrack` npm package running in a dedicated
Node.js sidecar worker (`deobfuscate_worker/worker.mjs`, one subprocess per
invocation, no shared state, no JSON-RPC handshake/ping/shutdown protocol).

Unlike reverse.code (pure Python, tree-sitter/jsbeautifier, never executes
anything), webcrack's own pipeline unconditionally evaluates the caller's JS
inside an `isolated-vm` V8-isolate sandbox (10s per-eval timeout, disposed
after use) to resolve values static analysis alone can't reach. That is a
materially higher risk than reverse.code's pure parsing, so this module is
gated behind the new `code.execute` permission (deny-by-default), unlike
reverse.code and reverse.sourcemap. See DECISIONS.md for the full rationale,
including why this does not use the generic JSON-RPC plugin runtime
(src/core/runtime/manager.py) and why the `restringer` npm package was
deliberately left out of this first version.

Requires a system-installed Node.js 22 or 24 (webcrack's own requirement,
tied to `isolated-vm`'s V8 ABI compatibility) plus a one-time
`npm install --prefix <this module's deobfuscate_worker directory>` — this
module does not attempt to auto-install or bundle Node.js itself.
"""
import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict

from ...base import BaseModule
from ...errors import ModuleError
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup
from ...types import StabilityLevel

logger = logging.getLogger(__name__)

_WORKER_DIR = Path(__file__).parent / 'deobfuscate_worker'
_WORKER_SCRIPT = _WORKER_DIR / 'worker.mjs'

# Bounds the worst-case memory/CPU cost of a single invocation. webcrack's
# transforms are proportional to input size; this caps the attack surface
# rather than trying to predict every pathological expansion case.
_MAX_SOURCE_BYTES = 5 * 1024 * 1024
_MAX_STDOUT_BYTES = 20 * 1024 * 1024

_MISSING_NODE_MESSAGE = (
    "Node.js 22 or 24 is required for reverse.deobfuscate (none found on PATH). "
    f"Install it, then run: npm install --prefix {_WORKER_DIR}"
)
_MISSING_MODULES_MESSAGE = (
    "reverse.deobfuscate's Node.js worker dependencies are not installed. "
    f"Run: npm install --prefix {_WORKER_DIR}"
)

# Deliberately independent of runtime/process.py's SAFE_ENV_VARS allowlist —
# this module manages its own subprocess rather than depending on the
# generic (and, per DECISIONS.md, unfinished) plugin runtime. Kept minimal:
# only what `node` itself needs to start and resolve its own module cache.
_SAFE_ENV_VARS = frozenset({
    'PATH', 'HOME', 'LANG', 'LC_ALL',
    'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP',
})


def _scrubbed_env() -> Dict[str, str]:
    return {key: value for key, value in os.environ.items() if key in _SAFE_ENV_VARS}


@register_module(
    module_id='reverse.deobfuscate',
    version='1.0.0',
    category='reverse',
    stability=StabilityLevel.BETA,
    tags=['reverse', 'deobfuscation', 'javascript', 'webcrack', 'node'],
    label='Deobfuscate Code',
    label_key='modules.reverse.deobfuscate.label',
    description='Reverse control-flow-flattening, string-array encoding, and bundling via webcrack',
    description_key='modules.reverse.deobfuscate.description',
    icon='Wand2',
    color='#DC2626',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['reverse.*', 'flow.*'],
    can_connect_to=['reverse.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],

    params_schema=compose(
        field(
            'source',
            type='string',
            label='JavaScript Source',
            label_key='modules.reverse.deobfuscate.params.source.label',
            description='JavaScript source text to deobfuscate, e.g. from reverse.scripts get_source',
            placeholder='var _0x1a2b=["a","b"];...',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000, max_ms=120000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.reverse.deobfuscate.output.status.description'},
        'deobfuscated': {'type': 'string', 'description': 'Deobfuscated JavaScript source',
                'description_key': 'modules.reverse.deobfuscate.output.deobfuscated.description'},
        'bundleDetected': {'type': 'boolean', 'description': 'Whether a webpack/browserify bundle was detected and unpacked',
                'description_key': 'modules.reverse.deobfuscate.output.bundleDetected.description'},
    },
    examples=[
        {'name': 'Deobfuscate a string-array-encoded snippet', 'params': {'source': 'var _0x1a2b=["Hello"];console.log(_0x1a2b[0]);'}},
    ],
    author='Flyto2 Team',
    license='MIT',
    # Registry timeout must exceed the largest allowed caller timeout_ms
    # (120000) so BaseModule.run()'s outer wait_for never fires first and
    # skips this module's own kill-on-timeout cleanup — same reasoning as
    # reverse.wait_paused's _REGISTRY_TIMEOUT_MS.
    timeout_ms=130000,
    # Deny-by-default: webcrack unconditionally evaluates caller-supplied JS
    # in a sandboxed subprocess. See module docstring and DECISIONS.md.
    required_permissions=['code.execute'],
)
class ReverseDeobfuscateModule(BaseModule):
    """Real semantic JS deobfuscation via webcrack, run in a dedicated Node.js worker."""

    module_name = "Deobfuscate Code"
    module_description = "Reverse control-flow-flattening, string-array encoding, and bundling via webcrack"
    required_permission = "code.execute"

    def validate_params(self) -> None:
        self.source = self.params.get('source')
        if not self.source:
            raise ValueError("Missing required parameter: source")
        if len(self.source.encode('utf-8')) > _MAX_SOURCE_BYTES:
            raise ValueError(f"source exceeds the {_MAX_SOURCE_BYTES}-byte limit")

        timeout_ms = self.params.get('timeout_ms', 30000)
        self.timeout_ms = min(int(timeout_ms), 120000)

    async def execute(self) -> Dict[str, Any]:
        node_path = shutil.which('node')
        if not node_path:
            raise ModuleError(_MISSING_NODE_MESSAGE)
        if not (_WORKER_DIR / 'node_modules').exists():
            raise ModuleError(_MISSING_MODULES_MESSAGE)

        request = json.dumps({'source': self.source}).encode('utf-8')

        proc = await asyncio.create_subprocess_exec(
            node_path, str(_WORKER_SCRIPT),
            cwd=str(_WORKER_DIR),
            env=_scrubbed_env(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(request), timeout=self.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            # Fixes the exact gap found in src/core/runtime/process.py's
            # invoke() timeout path: that one abandons the future without
            # killing the subprocess, so it keeps running. Here we actually
            # terminate it before surfacing the error.
            proc.kill()
            await proc.wait()
            raise ModuleError(f"Deobfuscation timed out after {self.timeout_ms}ms")

        if proc.returncode != 0:
            err_text = stderr.decode('utf-8', errors='replace')[:2000]
            raise ModuleError(f"Deobfuscation worker exited with code {proc.returncode}: {err_text}")

        stdout_text = stdout[:_MAX_STDOUT_BYTES].decode('utf-8', errors='replace')
        try:
            response = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise ModuleError(f"Deobfuscation worker returned invalid output: {exc}") from exc

        if not response.get('ok'):
            raise ModuleError(response.get('error') or 'Deobfuscation failed')

        return {
            'status': 'success',
            'deobfuscated': response.get('code', ''),
            'bundleDetected': response.get('bundleDetected', False),
        }
