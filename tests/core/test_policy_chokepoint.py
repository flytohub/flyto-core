"""Execution-chokepoint enforcement (pass-2 G1).

The MCP-boundary capability checks (#29/#34) were bypassable: flow.invoke /
template.invoke / foreach / composite sub-nodes / llm.agent tools run child
modules through a fresh engine or direct ModuleRegistry.get that never called the
filter. This enforces the policy in BaseModule.run() — the single point every
module execution flows through — so a denied module cannot run no matter how it
is reached.
"""

import ast
import os
from pathlib import Path

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
    async def test_denied_module_blocked_at_run(self, default_policy, tmp_path):
        # Construct a denied module directly (bypassing the mcp_handler gate) and
        # call run() — the chokepoint must still block it before execute().
        #
        # The path has to sit inside the sandbox: file.delete now confines
        # file_path at construction, so an out-of-sandbox literal would raise
        # PathTraversalError before run() and this test would pass for the wrong
        # reason, proving nothing about the policy chokepoint.
        victim = tmp_path / "should-not-be-touched"
        victim.write_text("x", encoding="utf-8")
        os.environ["FLYTO_SANDBOX_DIR"] = str(tmp_path)
        try:
            mod = FileDeleteModule({"file_path": str(victim)}, {})
            with pytest.raises(ModulePolicyError):
                await mod.run()
        finally:
            del os.environ["FLYTO_SANDBOX_DIR"]

        assert victim.exists() is True

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


# ---------------------------------------------------------------------------
# GHSA-wmwj-g59x-c8px — verify.spec dynamic child dispatch
# ---------------------------------------------------------------------------
#
# verify.spec chooses its child modules from the CALLER's ruleset: every rule
# names a `source.module` / `target.module` with free-form params. That
# dispatcher used to call the child's execute() directly, so a caller who was
# restricted to verify.spec could name shell.exec in a ruleset and run a host
# command — past both the module filter and the dangerous-permission grant.


def _shell_ruleset(marker, branch: str = "source") -> dict:
    """A ruleset whose `branch` side runs shell.exec and writes `marker`."""
    rule = {
        "name": "execute denied module",
        "source": {"keys": []},
        "target": {"keys": []},
    }
    rule[branch] = {
        # `touch` passes shell.exec's own command allowlist, so the only thing
        # that can stop the marker from appearing is the policy gate — the
        # point of the test. A command shell.exec rejects on its own would make
        # these pass for the wrong reason.
        "module": "shell.exec",
        "params": {"command": f"touch {marker}"},
    }
    return {"name": "policy-bypass-regression", "rules": [rule]}


@pytest.mark.asyncio
class TestVerifySpecNestedDispatch:

    @pytest.mark.parametrize("branch", ["source", "target"])
    async def test_denied_child_blocked_by_default(self, default_policy, tmp_path, branch):
        # Default policy: shell.* is denied, verify.spec is not. The denied
        # child must fail closed, and it must surface as a policy error rather
        # than a failed verification rule.
        marker = tmp_path / f"marker-{branch}.txt"
        module = ModuleRegistry.get("verify.spec")(
            {"ruleset": _shell_ruleset(marker, branch)}, {}
        )
        with pytest.raises(ModulePolicyError):
            await module.run()
        assert marker.exists() is False

    async def test_denied_child_blocked_under_strict_allowlist(self, monkeypatch, tmp_path):
        # The reported scenario: the caller is allowed exactly one module.
        monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
        monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
        monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "verify.spec")
        monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())

        marker = tmp_path / "marker-allowlist.txt"
        module = ModuleRegistry.get("verify.spec")(
            {"ruleset": _shell_ruleset(marker)}, {}
        )
        with pytest.raises(ModulePolicyError):
            await module.run()
        assert marker.exists() is False

    async def test_allowed_child_still_needs_the_permission_grant(self, monkeypatch, tmp_path):
        # Even an operator who allows shell.exec by id has not granted the
        # dangerous permission it declares. run() checks both; execute() checked
        # neither.
        monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
        monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
        monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", "verify.spec,shell.exec")
        monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())

        marker = tmp_path / "marker-permission.txt"
        module = ModuleRegistry.get("verify.spec")(
            {"ruleset": _shell_ruleset(marker)}, {}
        )
        with pytest.raises(ModulePolicyError):
            await module.run()
        assert marker.exists() is False


@pytest.mark.asyncio
async def test_verify_spec_ruleset_rejected_at_the_mcp_boundary(default_policy, tmp_path):
    # Defense in depth: the transport pre-flight already walks nested `module:`
    # declarations, so the ruleset is refused before verify.spec runs at all.
    marker = tmp_path / "marker-boundary.txt"
    result = await execute_module("verify.spec", {"ruleset": _shell_ruleset(marker)})
    assert result["ok"] is False
    assert result.get("blocked_by") == "module_filter", result
    assert "shell.exec" in result.get("blocked_modules", []), result
    assert marker.exists() is False


def test_rest_execute_rejects_a_denied_nested_module(monkeypatch, tmp_path):
    # The REST route checked only the top-level module id, so verify.spec was
    # admitted and the ruleset's shell.exec rode in with it.
    from starlette.testclient import TestClient

    import core.api.routes.modules as modules_route
    from core.api import security as sec
    from core.api.server import create_app

    monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
    monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
    monkeypatch.delenv("FLYTO_GRANTED_PERMISSIONS", raising=False)
    fresh = ModuleFilter()
    monkeypatch.setattr(modules_route, "module_filter", fresh)
    monkeypatch.setattr(module_policy, "module_filter", fresh)

    marker = tmp_path / "marker-rest.txt"
    with TestClient(create_app()) as client:
        headers = {"Authorization": f"Bearer {sec._active_token}"}
        direct = client.post(
            "/v1/execute",
            json={"module_id": "shell.exec", "params": {"command": f"printf X > {marker}"}},
            headers=headers,
        ).json()
        assert direct["ok"] is False
        assert "blocked" in (direct.get("error") or "").lower()

        nested = client.post(
            "/v1/execute",
            json={"module_id": "verify.spec", "params": {"ruleset": _shell_ruleset(marker)}},
            headers=headers,
        ).json()

    assert nested["ok"] is False
    # Refused by the route's own pre-flight (before verify.spec runs at all),
    # not only by the engine chokepoint underneath it.
    assert "nested" in (nested.get("error") or "").lower(), nested
    assert "shell.exec" in (nested.get("error") or "")
    assert marker.exists() is False


# ---------------------------------------------------------------------------
# Registry-wide: no dynamic dispatch may call execute() directly
# ---------------------------------------------------------------------------

def _dynamic_dispatch_offenders(root: Path) -> list:
    """Functions that resolve a module by a NON-constant id and then await
    `<obj>.execute()` instead of the policy-gated `<obj>.run()`.

    A constant id (`ModuleRegistry.get('ai.extract')`) is a fixed collaborator
    the author chose; a variable id is whatever the caller asked for, and that
    is the shape that turns an allowed module into a launcher for a denied one
    (GHSA-675h-j4qg-m52x in the test/warroom runner, GHSA-wmwj-g59x-c8px in
    verify.spec).
    """
    offenders = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - source must parse
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            dynamic_lookup = False
            direct_execute = False
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    func = inner.func
                    name = (
                        func.attr if isinstance(func, ast.Attribute)
                        else func.id if isinstance(func, ast.Name)
                        else ""
                    )
                    if name in {"get_module", "get"} and inner.args:
                        target = inner.args[0]
                        looks_like_registry = name == "get_module" or (
                            isinstance(func, ast.Attribute)
                            and isinstance(func.value, ast.Name)
                            and func.value.id == "ModuleRegistry"
                        )
                        if looks_like_registry and not isinstance(target, ast.Constant):
                            dynamic_lookup = True
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "execute"
                        and isinstance(func.value, ast.Name)
                        and func.value.id != "self"
                    ):
                        direct_execute = True
            if dynamic_lookup and direct_execute:
                offenders.append(f"{path}:{node.lineno}:{node.name}")
    return offenders


def test_no_dynamic_dispatch_bypasses_the_chokepoint():
    src = Path(__file__).resolve().parents[2] / "src" / "core"
    assert src.is_dir(), src
    assert _dynamic_dispatch_offenders(src) == []
