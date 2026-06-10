"""
MCP capability-filter tests — the guardrail that closes the host-RCE / SSRF-to-DB
exposure where the module denylist was enforced ONLY on the REST route and
bypassed by both MCP transports (STDIO + HTTP).

Covers:
  - the dangerous-by-default denylist (sandbox/shell/process/database/k8s/ssh/
    docker.run/file.delete) while keeping the shipped scraping primitives
    (browser.evaluate, docker.ps, file.write) allowed
  - execute_module() fails closed for a denied module, runs an allowed one
  - run_recipe() rejects a recipe whose declared steps use a denied module,
    BEFORE the engine executes anything
  - FLYTO_MODULE_ALLOWLIST strict opt-in overrides the denylist
"""

import pytest

from core.modules import atomic  # noqa: F401 — triggers module registration

import core.module_policy as module_policy
from core.module_policy import ModuleFilter
from core.mcp_handler import execute_module, run_recipe, _collect_module_ids


@pytest.fixture
def policy(monkeypatch):
    """Install a ModuleFilter built from the given env, as the active singleton."""
    def _install(denylist=None, allowlist=None):
        monkeypatch.delenv("FLYTO_MODULE_DENYLIST", raising=False)
        monkeypatch.delenv("FLYTO_MODULE_ALLOWLIST", raising=False)
        if denylist is not None:
            monkeypatch.setenv("FLYTO_MODULE_DENYLIST", denylist)
        if allowlist is not None:
            monkeypatch.setenv("FLYTO_MODULE_ALLOWLIST", allowlist)
        mf = ModuleFilter()
        # _module_is_allowed() does `from core.module_policy import module_filter`
        monkeypatch.setattr(module_policy, "module_filter", mf)
        return mf
    return _install


# ---------------------------------------------------------------------------
# Default policy shape
# ---------------------------------------------------------------------------

DANGEROUS = [
    "shell.exec", "process.start", "sandbox.execute_shell", "sandbox.execute_python",
    "sandbox.execute_js", "database.query", "database.update", "k8s.apply",
    "ssh.exec", "docker.run", "docker.exec", "file.delete",
]
SHIPPED_SAFE = [
    "string.uppercase", "browser.evaluate", "browser.goto", "docker.ps",
    "file.write", "http.get", "network.whois",
]


def test_default_denylist_blocks_dangerous():
    mf = ModuleFilter()  # reads real default (no env)
    for mid in DANGEROUS:
        assert mf.is_allowed(mid) is False, f"{mid} should be denied by default"


def test_default_denylist_keeps_shipped_recipes_working():
    mf = ModuleFilter()
    for mid in SHIPPED_SAFE:
        assert mf.is_allowed(mid) is True, f"{mid} should stay allowed by default"


# ---------------------------------------------------------------------------
# execute_module — the direct MCP chokepoint (both transports flow through here)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_module_denies_sandbox_rce(policy):
    policy()  # default dangerous denylist
    result = await execute_module("sandbox.execute_shell", {"command": "id"})
    assert result["ok"] is False
    assert result.get("blocked_by") == "module_filter"


@pytest.mark.asyncio
async def test_execute_module_denies_database_ssrf(policy):
    policy()
    result = await execute_module(
        "database.query",
        {"connection_string": "postgres://internal-rds:5432/x", "query": "SELECT 1"},
    )
    assert result["ok"] is False
    assert result.get("blocked_by") == "module_filter"


@pytest.mark.asyncio
async def test_execute_module_allows_safe_module(policy):
    policy()
    result = await execute_module("string.uppercase", {"text": "hello"})
    assert result.get("ok") is True
    assert result["data"]["result"] == "HELLO"


@pytest.mark.asyncio
async def test_allowlist_is_strict_opt_in(policy):
    policy(allowlist="string.*")
    assert (await execute_module("string.uppercase", {"text": "hi"})).get("ok") is True
    blocked = await execute_module("http.get", {"url": "http://example.com"})
    assert blocked["ok"] is False
    assert blocked.get("blocked_by") == "module_filter"


# ---------------------------------------------------------------------------
# run_recipe — pre-flight static scan rejects denied steps before execution
# ---------------------------------------------------------------------------

def test_collect_module_ids_walks_nested():
    workflow = {
        "steps": [
            {"module": "browser.goto"},
            {"module": "flow.loop", "body": [{"module": "sandbox.execute_python"}]},
        ]
    }
    assert _collect_module_ids(workflow) == {
        "browser.goto", "flow.loop", "sandbox.execute_python",
    }


@pytest.mark.asyncio
async def test_run_recipe_blocks_denied_module(policy, monkeypatch):
    policy()  # default denylist denies sandbox.*
    import cli.recipe as recipe_mod

    poisoned = {"steps": [
        {"id": "s1", "module": "browser.goto", "params": {"url": "http://x"}},
        {"id": "s2", "module": "sandbox.execute_python", "params": {"code": "import os; os.system('id')"}},
    ]}
    monkeypatch.setattr(recipe_mod, "load_recipe", lambda name: poisoned)
    monkeypatch.setattr(recipe_mod, "substitute_args", lambda wf, args: wf)

    # If the gate fails, the engine would actually run the RCE step; instead we
    # expect a fail-closed rejection naming the denied module.
    result = await run_recipe("poisoned-recipe", {})
    assert result["ok"] is False
    assert result.get("blocked_by") == "module_filter"
    assert "sandbox.execute_python" in result.get("blocked_modules", [])
