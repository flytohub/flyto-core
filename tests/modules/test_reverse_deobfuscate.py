"""
Unit tests for reverse.deobfuscate (Phase 4 — real semantic deobfuscation via
webcrack, run in a dedicated Node.js sidecar worker).

Unlike reverse.code (pure Python, always installed via the `dev` extra),
this module depends on a system-installed Node.js 22/24 plus a one-time
`npm install` in its sidecar worker directory — a real binary dependency,
not a pip extra. Only the tests that actually spawn the worker are skipped
when that dependency isn't present; validation/permission/mocked-error-path
tests run unconditionally.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
os.environ.setdefault("FLYTO_ENV", "test")

from core.modules import atomic  # noqa: F401 — triggers registration
from core.modules.atomic.reverse import deobfuscate as deobfuscate_module
from core.modules.errors import ModuleError
from core.modules.registry import ModuleRegistry
from core import module_policy

_WORKER_DIR = deobfuscate_module._WORKER_DIR
_NODE_AVAILABLE = shutil.which("node") is not None
_WORKER_DEPS_INSTALLED = (_WORKER_DIR / "node_modules").exists()

requires_worker = pytest.mark.skipif(
    not (_NODE_AVAILABLE and _WORKER_DEPS_INSTALLED),
    reason="requires Node.js 22/24 on PATH plus `npm install` in deobfuscate_worker/",
)

OBFUSCATED_JS = (
    'var _0x1a2b = ["Hello", "World"];'
    "function greet() { return _0x1a2b[0] + ', ' + _0x1a2b[1] + '!'; }"
    "greet();"
)


def get_module(mid):
    cls = ModuleRegistry.get(mid)
    assert cls is not None, f"{mid} not registered"
    return cls


async def run(params: dict) -> dict:
    cls = get_module("reverse.deobfuscate")
    mod = cls(params, {})  # BaseModule.__init__ calls validate_params()
    return await mod.execute()


class TestRegistration:
    def test_registered_requires_code_execute_permission(self):
        meta = ModuleRegistry.get_metadata("reverse.deobfuscate")
        assert meta is not None
        assert meta["category"] == "reverse"
        assert meta["required_permissions"] == ["code.execute"]


class TestPermissionGate:
    def test_denied_without_grant(self, monkeypatch):
        monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
        with pytest.raises(module_policy.ModulePolicyError):
            module_policy.enforce_module_policy("reverse.deobfuscate", ["code.execute"])

    def test_allowed_with_grant(self, monkeypatch):
        monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "code.execute")
        module_policy.enforce_module_policy("reverse.deobfuscate", ["code.execute"])


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_source_raises(self):
        with pytest.raises(ValueError):
            await run({})

    @pytest.mark.asyncio
    async def test_oversized_source_rejected(self):
        huge = "a" * (5 * 1024 * 1024 + 1)
        with pytest.raises(ValueError, match="byte limit"):
            await run({"source": huge})


class TestMissingDependencies:
    @pytest.mark.asyncio
    async def test_missing_node_raises_clear_error(self, monkeypatch):
        monkeypatch.setattr(deobfuscate_module.shutil, "which", lambda name: None)
        with pytest.raises(ModuleError, match="Node.js 22 or 24"):
            await run({"source": "1"})

    @pytest.mark.asyncio
    async def test_missing_worker_node_modules_raises_clear_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr(deobfuscate_module, "_WORKER_DIR", tmp_path)
        with pytest.raises(ModuleError, match="npm install"):
            await run({"source": "1"})


@requires_worker
class TestDeobfuscate:
    @pytest.mark.asyncio
    async def test_resolves_string_array_encoding(self):
        result = await run({"source": OBFUSCATED_JS})
        assert result["status"] == "success"
        assert "Hello" in result["deobfuscated"]
        assert "World" in result["deobfuscated"]
        assert result["bundleDetected"] is False

    @pytest.mark.asyncio
    async def test_timeout_kills_subprocess(self):
        with pytest.raises(ModuleError, match="timed out"):
            await run({"source": "function f(){return 1}", "timeout_ms": 1})
