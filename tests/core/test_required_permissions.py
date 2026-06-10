"""Per-module required_permissions enforcement (P0-10) — a second lock beyond the
module-id allowlist. Dangerous permissions (shell/subprocess/payment) must be
explicitly granted via FLYTO_GRANTED_PERMISSIONS even if the module-id is allowed."""

import pytest

from core.modules import atomic  # noqa: F401 — registers modules

import core.module_policy as module_policy
from core.module_policy import ModuleFilter, missing_permissions
from core.mcp_handler import execute_module, run_recipe


def _allow_all(monkeypatch, granted=None):
    """Make the module filter allow everything, set the granted-permission env."""
    monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "*")
    if granted is None:
        monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
    else:
        monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", granted)
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


class TestMissingPermissions:
    def test_dangerous_requires_grant(self, monkeypatch):
        monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
        assert "subprocess.execute" in missing_permissions(["subprocess.execute"])
        assert "payment.process" in missing_permissions(["payment.process"])

    def test_safe_permissions_always_allowed(self, monkeypatch):
        monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
        assert missing_permissions(["browser.automation", "filesystem.read", "network.access"]) == []
        assert missing_permissions([]) == []

    def test_grant_clears_it(self, monkeypatch):
        monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "subprocess.execute,payment.process")
        assert missing_permissions(["subprocess.execute"]) == []
        assert missing_permissions(["payment.process"]) == []


@pytest.mark.asyncio
class TestExecuteModulePermissionGate:
    async def test_blocked_when_permission_not_granted(self, monkeypatch):
        # module-id allowed, but subprocess.execute not granted -> permission block
        _allow_all(monkeypatch, granted=None)
        res = await execute_module("sandbox.execute_shell", {"command": "id"})
        assert res["ok"] is False
        assert res["blocked_by"] == "required_permissions"
        assert "subprocess.execute" in res["missing_permissions"]

    async def test_passes_gate_when_granted(self, monkeypatch):
        _allow_all(monkeypatch, granted="subprocess.execute")
        res = await execute_module("sandbox.execute_shell", {"command": "echo hi", "timeout": 5})
        # may actually run now — assert it is NOT stopped by either policy gate
        assert res.get("blocked_by") not in ("required_permissions", "module_filter")

    async def test_safe_module_unaffected(self, monkeypatch):
        _allow_all(monkeypatch, granted=None)
        res = await execute_module("string.uppercase", {"text": "hi"})
        assert res.get("ok") is True


@pytest.mark.asyncio
async def test_run_recipe_blocks_on_missing_permission(monkeypatch):
    _allow_all(monkeypatch, granted=None)
    import cli.recipe as recipe_mod
    poisoned = {"steps": [{"id": "s1", "module": "sandbox.execute_shell",
                           "params": {"command": "id"}}]}
    monkeypatch.setattr(recipe_mod, "load_recipe", lambda name: poisoned)
    monkeypatch.setattr(recipe_mod, "substitute_args", lambda wf, args: wf)
    res = await run_recipe("poisoned", {})
    assert res["ok"] is False
    assert res["blocked_by"] == "required_permissions"
    assert "sandbox.execute_shell" in res["blocked_modules"]
