# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The out-of-process plugin path passes the same gate as everything else.

Until this existed, ``StepExecutor`` fell through to ``RuntimeInvoker.invoke``
for any module id the registry did not know, and nothing on that path called
``enforce_module_policy``. It was not reachable — ``set_plugin_manager`` had no
caller, so ``_invoke_plugin`` raised ``PluginNotFoundError`` — but it was one
wiring change from working, and the same change from being a way around the
denylist that ``BaseModule.run`` enforces for every in-process module.
"""

import pytest

from core.runtime.invoke import RuntimeInvoker

POLICY_ENVS = (
    "FLYTO_GRANTED_PERMISSIONS",
    "FLYTO_PLUGIN_GRANTS",
    "FLYTO_PLUGIN_DENYLIST",
    "FLYTO_PLUGIN_ALLOWLIST",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in POLICY_ENVS:
        monkeypatch.delenv(name, raising=False)


class _Step:
    def __init__(self, step_id, required_permissions=None):
        self.id = step_id
        self.required_permissions = required_permissions or []


class _Manifest:
    def __init__(self, plugin_id, steps):
        self.id = plugin_id
        self.steps = steps


class _Manager:
    def __init__(self, manifest=None, raises=False):
        self._manifest = manifest
        self._raises = raises

    def get_manifest(self, plugin_id):
        if self._raises:
            raise RuntimeError("manifest store is unavailable")
        return self._manifest

    def list_plugins(self):
        return []


def _invoker(manager=None):
    invoker = RuntimeInvoker()
    if manager is not None:
        invoker._plugin_manager = manager
    return invoker


async def _invoke(invoker, module_id, step_id):
    return await invoker.invoke(
        module_id=module_id, step_id=step_id, input_data={}, config={}, context={}
    )


@pytest.mark.asyncio
async def test_a_denylisted_module_id_is_refused_before_routing():
    """The hole this closes: shell.exec reached through a plugin subprocess."""
    result = await _invoke(_invoker(), "shell", "exec")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "capability policy" in result["error"]["message"]


@pytest.mark.asyncio
async def test_an_ordinary_module_id_is_not_refused_by_the_gate():
    """It must stop denied work, not all work: this gets past policy and fails
    later for its own reasons."""
    result = await _invoke(_invoker(), "http", "get")
    assert result["ok"] is False
    assert result["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_a_denied_plugin_cannot_invoke_anything(monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "com.example.thermal")
    manager = _Manager(_Manifest("com.example.thermal", [_Step("scan")]))
    result = await _invoke(_invoker(manager), "com.example.thermal", "scan")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "not permitted here" in result["error"]["message"]


@pytest.mark.asyncio
async def test_a_dangerous_permission_needs_a_grant_naming_the_plugin(monkeypatch):
    """A plugin declaring shell.execute must not reach the global grant."""
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    manager = _Manager(
        _Manifest("com.example.thermal", [_Step("scan", ["shell.execute"])])
    )
    result = await _invoke(_invoker(manager), "com.example.thermal", "scan")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "ungranted permission" in result["error"]["message"]

    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "com.example.thermal:shell.execute")
    allowed = await _invoke(_invoker(manager), "com.example.thermal", "scan")
    assert allowed["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_only_the_named_step_permissions_are_read(monkeypatch):
    """A dangerous permission on a different step must not bleed onto this one."""
    manager = _Manager(
        _Manifest(
            "com.example.thermal",
            [_Step("scan"), _Step("wipe", ["shell.execute"])],
        )
    )
    result = await _invoke(_invoker(manager), "com.example.thermal", "scan")
    assert result["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_an_unreadable_manifest_does_not_open_the_gate(monkeypatch):
    """A manifest lookup that throws must not fail open."""
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "anything")
    result = await _invoke(_invoker(_Manager(raises=True)), "shell", "exec")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_a_plugin_with_no_manifest_still_meets_the_module_filter():
    """Silence about permissions must not buy a denied module id."""
    result = await _invoke(_invoker(_Manager(manifest=None)), "shell", "exec")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
