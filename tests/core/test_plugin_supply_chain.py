"""Supply-chain hardening for plugin installation (P2-5).

`pip install` runs an arbitrary build backend, so where the package comes from
matters. These tests assert the index-pinning and fail-closed strict mode without
ever actually shelling out to pip.
"""

import types

import pytest

from core.plugin.loader import PluginLoader


class _FakeProc:
    returncode = 0
    stdout = ""
    stderr = ""


@pytest.fixture
def loader(monkeypatch):
    ld = PluginLoader()
    # never re-scan the environment during a unit test
    monkeypatch.setattr(ld, "discover_plugins", lambda force=False: {})
    return ld


def _capture_pip(monkeypatch):
    calls = {}

    def fake_run(cmd, *a, **k):
        calls["cmd"] = cmd
        return _FakeProc()

    monkeypatch.setattr("core.plugin.loader.subprocess.run", fake_run)
    return calls


def test_pins_to_configured_index(loader, monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_INDEX_URL", "https://pypi.internal/simple")
    monkeypatch.delenv("FLYTO_PLUGIN_REQUIRE_TRUSTED_INDEX", raising=False)
    calls = _capture_pip(monkeypatch)

    assert loader.install_plugin("flyto-plugin-slack", version="1.2.3") is True
    cmd = calls["cmd"]
    assert "--index-url" in cmd
    assert "https://pypi.internal/simple" in cmd
    assert "flyto-plugin-slack==1.2.3" in cmd


def test_strict_mode_refuses_without_index(loader, monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_REQUIRE_TRUSTED_INDEX", "1")
    monkeypatch.delenv("FLYTO_PLUGIN_INDEX_URL", raising=False)
    calls = _capture_pip(monkeypatch)

    assert loader.install_plugin("flyto-plugin-slack") is False
    assert "cmd" not in calls  # pip was never invoked


def test_default_install_still_works_without_index(loader, monkeypatch):
    monkeypatch.delenv("FLYTO_PLUGIN_INDEX_URL", raising=False)
    monkeypatch.delenv("FLYTO_PLUGIN_REQUIRE_TRUSTED_INDEX", raising=False)
    calls = _capture_pip(monkeypatch)

    assert loader.install_plugin("flyto-plugin-slack") is True
    assert "--index-url" not in calls["cmd"]


def test_invalid_version_rejected(loader, monkeypatch):
    calls = _capture_pip(monkeypatch)
    assert loader.install_plugin("flyto-plugin-slack", version="1.0; rm -rf /") is False
    assert "cmd" not in calls
