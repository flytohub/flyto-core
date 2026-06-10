"""Execution-chokepoint enforcement (pass-2 G1).

The MCP-boundary capability checks (#29/#34) were bypassable: flow.invoke /
template.invoke / foreach / composite sub-nodes / llm.agent tools run child
modules through a fresh engine or direct ModuleRegistry.get that never called the
filter. This enforces the policy in BaseModule.run() — the single point every
module execution flows through — so a denied module cannot run no matter how it
is reached.
"""

import pytest

from core.modules import atomic  # noqa: F401 — registers modules

import core.module_policy as module_policy
from core.module_policy import ModuleFilter, ModulePolicyError, enforce_module_policy
from core.modules.registry import ModuleRegistry
from core.modules.atomic.file.delete import FileDeleteModule
from core.mcp_handler import execute_module


@pytest.fixture
def default_policy(monkeypatch):
    """Install the default deny-by-default policy (no allowlist, no grants)."""
    monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())


class TestEnforce:
    def test_denied_module_raises(self, default_policy):
        with pytest.raises(ModulePolicyError):
            enforce_module_policy("sandbox.execute_shell", ["subprocess.execute"])

    def test_env_get_now_denied_by_default(self, default_policy):
        assert module_policy.module_filter.is_allowed("env.get") is False
        with pytest.raises(ModulePolicyError):
            enforce_module_policy("env.get", [])

    def test_allowed_module_passes(self, default_policy):
        enforce_module_policy("string.uppercase", [])  # no raise

    def test_dangerous_permission_requires_grant(self, default_policy):
        with pytest.raises(ModulePolicyError):
            enforce_module_policy("string.uppercase", ["subprocess.execute"])


@pytest.mark.asyncio
class TestRunBackstop:
    async def test_denied_module_blocked_at_run(self, default_policy):
        # Construct a denied module directly (bypassing the mcp_handler gate) and
        # call run() — the chokepoint must still block it before execute().
        mod = FileDeleteModule({"file_path": "/tmp/should-not-be-touched"}, {})
        with pytest.raises(ModulePolicyError):
            await mod.run()

    async def test_allowed_module_runs(self, default_policy):
        mod = ModuleRegistry.get("string.uppercase")({"text": "hi"}, {})
        result = await mod.run()
        assert result["data"]["result"] == "HI"


@pytest.mark.asyncio
async def test_flow_invoke_denied_by_default(default_policy):
    # The headline bypass (pass-2 G1): flow.invoke takes an inline child workflow
    # and used to run a denied child (shell.exec etc.) with no gate. It is now in
    # the default denylist, so the gadget itself is refused before it can run any
    # smuggled child. Must fail closed (ok=False, blocked by the module filter).
    inline = (
        "steps:\n"
        "  - id: s1\n"
        "    module: shell.exec\n"
        "    params:\n"
        "      command: echo CHOKEPOINT\n"
    )
    result = await execute_module("flow.invoke", {"workflow_source": inline})
    assert result["ok"] is False
    assert result.get("blocked_by") == "module_filter", result


@pytest.mark.asyncio
async def test_smuggled_child_blocked_even_if_gadget_allowed(monkeypatch):
    # Defense in depth: even if an operator deliberately ALLOWS flow.invoke, an
    # inline workflow_source that smuggles a denied module (shell.exec) is still
    # rejected by the pre-flight that recurses into the inline payload string.
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
    # Allow flow.invoke (and benign string.*) but NOT shell.*.
    monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "flow.invoke,string.*")
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())
    inline = (
        "steps:\n"
        "  - id: s1\n"
        "    module: shell.exec\n"
        "    params:\n"
        "      command: echo CHOKEPOINT\n"
    )
    result = await execute_module("flow.invoke", {"workflow_source": inline})
    assert result["ok"] is False
    assert result.get("blocked_by") == "module_filter", result
    assert "shell.exec" in result.get("blocked_modules", []), result
