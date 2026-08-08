# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Per-plugin policy scope.

The defect this file exists for: with one process-global grant set, a plugin
that *honestly* declared ``required_permissions: [shell.execute]`` was asking
the operator to grant shell.execute to every module in the process — flyto-core's
own and every other plugin's. Declaring a permission is supposed to be how a
plugin tells the truth about itself; it must not be how it acquires reach.

The other half is ownership. If a module could say which plugin it belongs to,
the interesting lie is not "I am plugin B" but "I am no plugin at all", because
the empty owner is exactly the one the process-global grant still covers.
"""

import pytest

from core.module_policy import (
    ModulePolicyError,
    enforce_module_policy,
    is_plugin_allowed,
    missing_permissions,
    plugin_grants,
)
from core.modules.base import BaseModule
from core.modules.registry.core import ModuleRegistry

PLUGIN_ENVS = (
    "FLYTO_GRANTED_PERMISSIONS",
    "FLYTO_PLUGIN_GRANTS",
    "FLYTO_PLUGIN_DENYLIST",
    "FLYTO_PLUGIN_ALLOWLIST",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in PLUGIN_ENVS:
        monkeypatch.delenv(name, raising=False)


class _Noop(BaseModule):
    async def execute(self):  # pragma: no cover - never executed here
        return {}


# -- the escalation this exists to prevent ---------------------------------


def test_a_global_grant_does_not_reach_a_plugin(monkeypatch):
    """An operator who granted shell.execute to flyto-core has not granted it
    to every plugin they install afterwards."""
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")

    enforce_module_policy("build.run", ["shell.execute"], plugin="")

    with pytest.raises(ModulePolicyError, match="ungranted permission"):
        enforce_module_policy("thermal.scan", ["shell.execute"], plugin="thermal")


def test_a_grant_names_the_plugin_it_reaches(monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "thermal:shell.execute")

    enforce_module_policy("thermal.scan", ["shell.execute"], plugin="thermal")

    with pytest.raises(ModulePolicyError):
        enforce_module_policy("vision.observe", ["shell.execute"], plugin="vision")


def test_the_refusal_says_how_to_grant_it(monkeypatch):
    """An operator reading the error must not have to guess the syntax."""
    with pytest.raises(ModulePolicyError, match=r"FLYTO_PLUGIN_GRANTS=thermal:shell\.execute"):
        enforce_module_policy("thermal.scan", ["shell.execute"], plugin="thermal")


def test_a_first_party_refusal_still_points_at_the_global_grant():
    with pytest.raises(ModulePolicyError, match="FLYTO_GRANTED_PERMISSIONS"):
        enforce_module_policy("build.run", ["shell.execute"], plugin="")


def test_a_harmless_permission_needs_no_grant():
    enforce_module_policy("vision.observe", ["network.read"], plugin="vision")


def test_grants_parse_several_plugins_and_several_permissions(monkeypatch):
    monkeypatch.setenv(
        "FLYTO_PLUGIN_GRANTS", "a:shell.execute, b:code.execute ,a:payment.process"
    )
    assert plugin_grants("a") == {"shell.execute", "payment.process"}
    assert plugin_grants("b") == {"code.execute"}
    assert plugin_grants("c") == set()


@pytest.mark.parametrize("junk", ["", "  ", "noseparator", ":", "a:", ":b", ",,,"])
def test_a_malformed_grant_grants_nothing(monkeypatch, junk):
    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", junk)
    assert plugin_grants("a") == set()
    assert missing_permissions(["shell.execute"], plugin="a") == ["shell.execute"]


# -- which plugins may run at all ------------------------------------------


def test_a_denied_plugin_cannot_run_anything(monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "thermal")
    with pytest.raises(ModulePolicyError, match="not permitted here"):
        enforce_module_policy("thermal.scan", [], plugin="thermal")
    enforce_module_policy("vision.observe", [], plugin="vision")


def test_an_allowlist_excludes_everything_it_does_not_name(monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_ALLOWLIST", "vision")
    enforce_module_policy("vision.observe", [], plugin="vision")
    with pytest.raises(ModulePolicyError):
        enforce_module_policy("thermal.scan", [], plugin="thermal")


def test_the_plugin_lists_do_not_touch_first_party_modules(monkeypatch):
    """flyto-core's own modules are governed by the module filter, not by this."""
    monkeypatch.setenv("FLYTO_PLUGIN_ALLOWLIST", "vision")
    enforce_module_policy("http.get", [], plugin="")
    assert is_plugin_allowed("") is True


def test_an_allowlist_beats_a_denylist(monkeypatch):
    monkeypatch.setenv("FLYTO_PLUGIN_ALLOWLIST", "vision")
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "vision")
    assert is_plugin_allowed("vision") is True


# -- the plugin dimension may only narrow ----------------------------------


def test_a_permitted_plugin_still_cannot_run_a_denied_module(monkeypatch):
    """A plugin cannot name itself into the shell the denylist refuses."""
    monkeypatch.setenv("FLYTO_PLUGIN_ALLOWLIST", "vision")
    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "vision:shell.execute")
    with pytest.raises(ModulePolicyError, match="capability policy"):
        enforce_module_policy("shell.exec", [], plugin="vision")


# -- ownership is assigned, not claimed ------------------------------------


def test_a_module_registered_during_a_plugin_load_cannot_disown_itself():
    """The interesting lie is 'I belong to no plugin', because that owner is the
    one the process-global grant still reaches."""
    ModuleRegistry._loading_plugin = "thermal"
    try:
        ModuleRegistry.register(
            "thermal.liar", _Noop, {"plugin": "", "required_permissions": ["shell.execute"]}
        )
    finally:
        ModuleRegistry._loading_plugin = ""

    try:
        assert ModuleRegistry.get_metadata("thermal.liar")["plugin"] == "thermal"
    finally:
        ModuleRegistry.unregister("thermal.liar")


def test_a_module_cannot_claim_another_plugins_name():
    ModuleRegistry._loading_plugin = "thermal"
    try:
        ModuleRegistry.register("thermal.imposter", _Noop, {"plugin": "vision"})
    finally:
        ModuleRegistry._loading_plugin = ""

    try:
        assert ModuleRegistry.get_metadata("thermal.imposter")["plugin"] == "thermal"
    finally:
        ModuleRegistry.unregister("thermal.imposter")


def test_a_first_party_module_is_stamped_with_no_plugin():
    ModuleRegistry.register("firstparty.demo", _Noop, {"version": "1.0.0"})
    try:
        assert ModuleRegistry.get_metadata("firstparty.demo")["plugin"] == ""
    finally:
        ModuleRegistry.unregister("firstparty.demo")


def test_a_plugin_module_with_no_metadata_is_still_attributable():
    """The hole this closes: register() only stored metadata when it was truthy,
    so a plugin registering a module with none left it with no owner — and an
    absent owner reads as flyto-core's own, which is exactly the identity a
    denied plugin would want."""
    ModuleRegistry._loading_plugin = "thermal"
    try:
        ModuleRegistry.register("thermal.bare", _Noop)
    finally:
        ModuleRegistry._loading_plugin = ""

    try:
        assert ModuleRegistry.get_metadata("thermal.bare")["plugin"] == "thermal"
        with pytest.raises(ModulePolicyError):
            import os
            os.environ["FLYTO_PLUGIN_DENYLIST"] = "thermal"
            try:
                enforce_module_policy(
                    "thermal.bare",
                    ModuleRegistry.get_metadata("thermal.bare").get("required_permissions"),
                    plugin=ModuleRegistry.get_metadata("thermal.bare")["plugin"],
                )
            finally:
                os.environ.pop("FLYTO_PLUGIN_DENYLIST", None)
    finally:
        ModuleRegistry.unregister("thermal.bare")


def test_a_first_party_module_with_no_metadata_keeps_its_old_shape():
    """Unchanged behaviour outside plugin loading: no metadata stays no metadata."""
    ModuleRegistry.register("firstparty.bare", _Noop)
    try:
        assert ModuleRegistry.get_metadata("firstparty.bare") is None
    finally:
        ModuleRegistry.unregister("firstparty.bare")


def test_a_raising_plugin_does_not_leak_its_name(monkeypatch):
    """discover_plugins clears the marker in `finally`; without that, the next
    plugin's modules — or flyto-core's — would inherit the failed one's name."""

    class _Boom:
        name = "boom"
        value = "boom_pkg:register_all"

        @staticmethod
        def load():
            def register_all():
                raise RuntimeError("plugin exploded mid-registration")

            return register_all

    monkeypatch.setattr(
        "core.modules.registry.core.ModuleRegistry._plugins", {}, raising=False
    )
    import core.modules.registry.core as registry_core

    monkeypatch.setattr(
        registry_core, "entry_points", lambda **kw: [_Boom()], raising=False
    )
    ModuleRegistry._loading_plugin = ""
    try:
        ModuleRegistry.discover_plugins(force=True)
    except Exception:  # noqa: BLE001 - discovery swallows plugin errors itself
        pass
    assert ModuleRegistry._loading_plugin == ""
