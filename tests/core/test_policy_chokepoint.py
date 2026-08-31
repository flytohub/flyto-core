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

import core.module_policy as module_policy
from core.mcp_handler import execute_module
from core.module_policy import ModuleFilter, ModulePolicyError, enforce_module_policy
from core.modules import atomic  # noqa: F401 — registers modules
from core.modules.atomic.file.delete import FileDeleteModule
from core.modules.registry import ModuleRegistry


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

    def test_execution_scoped_filter_does_not_mutate_global_policy(
        self,
        default_policy,
    ):
        class ScopedFilter:
            _flyto_runtime_opaque = True

            def is_allowed(self, module_id):
                return module_id == "template.invoke"

        enforce_module_policy(
            "template.invoke",
            [],
            module_filter_override=ScopedFilter(),
        )

        with pytest.raises(ModulePolicyError):
            enforce_module_policy("template.invoke", [])


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

    async def test_run_uses_only_an_opaque_execution_scoped_filter(
        self,
        default_policy,
    ):
        class ScopedFilter:
            _flyto_runtime_opaque = True

            def is_allowed(self, module_id):
                return module_id in {"template.invoke", "string.uppercase"}

        mod = ModuleRegistry.get("string.uppercase")(
            {"text": "scoped"},
            {"_module_policy_filter": ScopedFilter()},
        )
        result = await mod.run()

        assert result["data"]["result"] == "SCOPED"


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


# ---------------------------------------------------------------------------
# A capability refusal must not be retried.
#
# `execute_with_retry` caught every exception and re-invoked the step. A
# refusal is not a transient failure: policy does not change between attempts,
# so the retries could not turn it into a success, but each one re-ran whatever
# side effects preceded the refused module and gated it again. The refusal
# always propagated, so the gate stayed fail-closed — what leaked was the
# replay.
# ---------------------------------------------------------------------------

class _PolicyCallCounter:
    """Count enforce_module_policy calls for one module id."""

    def __init__(self, monkeypatch, module_id):
        self.module_id = module_id
        self.calls = 0
        original = module_policy.enforce_module_policy

        def counting(module_id_arg, *args, **kwargs):
            if module_id_arg == self.module_id:
                self.calls += 1
            return original(module_id_arg, *args, **kwargs)

        # BaseModule.run imports enforce_module_policy from the module object on
        # every call, so patching the attribute covers the chokepoint.
        monkeypatch.setattr(module_policy, "enforce_module_policy", counting)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retry_settings",
    [
        {"retry": {"count": 3, "delay_ms": 0}},
        {"on_error": "retry"},
        {"on_error": "continue", "retry": {"count": 2, "delay_ms": 0}},
    ],
    ids=["retry-config", "on_error-retry", "retry-plus-continue"],
)
async def test_refused_module_is_gated_exactly_once_despite_retry(
    monkeypatch,
    retry_settings,
):
    from core.engine.exceptions import is_policy_refusal
    from core.engine.workflow import WorkflowEngine

    monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
    monkeypatch.setenv("FLYTO_MODULE_DENYLIST", "string.uppercase")
    monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())
    counter = _PolicyCallCounter(monkeypatch, "string.uppercase")

    step = {
        "id": "refused",
        "module": "string.uppercase",
        "params": {"text": "hi"},
        **retry_settings,
    }
    engine = WorkflowEngine(workflow={"steps": [step]}, initial_context={})

    with pytest.raises(Exception) as exc_info:
        await engine.execute()

    # Fail-closed is the non-negotiable half: the refusal still propagates.
    assert is_policy_refusal(exc_info.value) is True
    # And the retry loop must not have replayed it.
    assert counter.calls == 1


@pytest.mark.asyncio
async def test_retry_still_retries_an_ordinary_failure(monkeypatch):
    """The refusal guard must not disable retries for normal errors."""
    from core.engine.step_executor.retry import execute_with_retry

    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = await execute_with_retry(
        step_id="flaky",
        execute_fn=flaky,
        retry_config={"count": 3, "delay_ms": 0},
    )

    assert result == "ok"
    assert attempts["n"] == 3


# ---------------------------------------------------------------------------
# Gates that survived the mutation sweep with nothing failing.
# ---------------------------------------------------------------------------

class TestModulePolicyFilterGates:
    def test_filter_that_raises_fails_closed(self, default_policy):
        """A filter whose is_allowed raises must deny, never fall open."""

        class BrokenFilter:
            _flyto_runtime_opaque = True

            def is_allowed(self, module_id):
                raise RuntimeError("policy backend unavailable")

        with pytest.raises(ModulePolicyError):
            enforce_module_policy(
                "string.uppercase",
                [],
                module_filter_override=BrokenFilter(),
            )

    @pytest.mark.asyncio
    async def test_non_opaque_filter_from_workflow_data_is_ignored(
        self,
        default_policy,
        monkeypatch,
    ):
        """Only a runtime-opaque capability may widen policy.

        `_module_policy_filter` is read off the execution context, which
        workflow-authored data can reach. A plain object that merely exposes
        `is_allowed` must not be honoured, or authoring a step would be enough
        to grant yourself any module.
        """
        monkeypatch.setenv("FLYTO_MODULE_DENYLIST", "string.uppercase")
        monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())

        class WorkflowSupplied:  # no _flyto_runtime_opaque marker
            def is_allowed(self, module_id):
                return True

        mod = ModuleRegistry.get("string.uppercase")(
            {"text": "hi"},
            {"_module_policy_filter": WorkflowSupplied()},
        )
        with pytest.raises(ModulePolicyError):
            await mod.run()

    @pytest.mark.asyncio
    async def test_marker_as_instance_key_is_not_a_capability(
        self,
        default_policy,
        monkeypatch,
    ):
        """The marker is read off the type, so JSON-shaped data cannot forge it."""
        monkeypatch.setenv("FLYTO_MODULE_DENYLIST", "string.uppercase")
        monkeypatch.setattr(module_policy, "module_filter", ModuleFilter())

        class MarkedDict(dict):
            def is_allowed(self, module_id):
                return True

        forged = MarkedDict(_flyto_runtime_opaque=True)

        mod = ModuleRegistry.get("string.uppercase")(
            {"text": "hi"},
            {"_module_policy_filter": forged},
        )
        with pytest.raises(ModulePolicyError):
            await mod.run()
