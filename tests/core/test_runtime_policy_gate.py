# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The out-of-process plugin path passes the same gate as everything else.

Until this existed, ``StepExecutor`` fell through to ``RuntimeInvoker.invoke``
for any module id the registry did not know, and nothing on that path called
``enforce_module_policy``. It was not reachable — ``set_plugin_manager`` had no
caller, so ``_invoke_plugin`` raised ``PluginNotFoundError`` — but it was one
wiring change from working, and the same change from being a way around the
denylist that ``BaseModule.run`` enforces for every in-process module.
"""

import logging
from unittest.mock import MagicMock

import pytest

from core.runtime.invoke import RuntimeInvoker
from core.runtime.manager import PluginManifest

# The plugin id below is spelled `com-example-thermal`, not `com.example.thermal`:
# `validate_plugin_id` accepts alphanumerics, hyphens, underscores and slashes,
# and dots are not in that set. The reverse-DNS spelling made every
# `PluginManifest.from_dict` call in this file raise ValidationError, so the
# dict-manifest cases were erroring out instead of exercising the gate they pin.

# What the manifest store fails with, standing in for the shapes that really do
# show up in such an error: an on-disk path and a credential. Neither may appear
# in the denial the caller reads.
MANIFEST_FAILURE_DETAIL = (
    "/srv/flyto/plugins/thermal/manifest.json unreadable: token=s3cr3t-abc"
)

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
    """One manifest step.

    ``id_raises`` makes reading the step id throw. Manifest entries are
    plugin-supplied objects, so a field that raises on access is a shape the
    gate really can be handed — not a programming error — and the gate has to
    survive it the same way it survives a lookup that throws.
    """

    def __init__(self, step_id, required_permissions=None, id_raises=False):
        self._id = step_id
        self._id_raises = id_raises
        self.required_permissions = required_permissions or []

    @property
    def id(self):
        if self._id_raises:
            raise RuntimeError(MANIFEST_FAILURE_DETAIL)
        return self._id


class _Manifest:
    """A manifest whose lookup succeeded but whose fields may still fail."""

    def __init__(self, plugin_id, steps, steps_raise=False):
        self.id = plugin_id
        self._steps = steps
        self._steps_raise = steps_raise

    @property
    def steps(self):
        if self._steps_raise:
            raise RuntimeError(MANIFEST_FAILURE_DETAIL)
        return self._steps


class _Manager:
    def __init__(self, manifest=None, raises=False):
        self._manifest = manifest
        self._raises = raises
        self.manifest_queries = []

    def get_manifest(self, plugin_id):
        self.manifest_queries.append(plugin_id)
        if self._raises:
            raise RuntimeError(MANIFEST_FAILURE_DETAIL)
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
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "com-example-thermal")
    manager = _Manager(_Manifest("com-example-thermal", [_Step("scan")]))
    result = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "not permitted here" in result["error"]["message"]


@pytest.mark.asyncio
async def test_a_dangerous_permission_needs_a_grant_naming_the_plugin(monkeypatch):
    """A plugin declaring shell.execute must not reach the global grant."""
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    manager = _Manager(
        _Manifest("com-example-thermal", [_Step("scan", ["shell.execute"])])
    )
    result = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "ungranted permission" in result["error"]["message"]

    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "com-example-thermal:shell.execute")
    allowed = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert allowed["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_a_legacy_spelling_checks_the_resolved_plugin_manifest(monkeypatch):
    """Routing aliases must not erase the plugin's declared permissions.

    ``database.scan`` resolves to ``flyto-official/database``. Looking up the
    manifest under the caller's bare ``database`` spelling returns no manifest
    in the real manager, which used to let the routed subprocess run without
    checking its required_permissions.
    """
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    manager = _Manager(
        _Manifest("flyto-official/database", [_Step("scan", ["shell.execute"])])
    )
    invoker = _invoker(manager)
    invoker._router.set_available_plugins({"database"})

    result = await _invoke(invoker, "database", "scan")

    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert manager.manifest_queries == ["flyto-official/database"]


@pytest.mark.asyncio
async def test_only_the_named_step_permissions_are_read(monkeypatch):
    """A dangerous permission on a different step must not bleed onto this one."""
    manager = _Manager(
        _Manifest(
            "com-example-thermal",
            [_Step("scan"), _Step("wipe", ["shell.execute"])],
        )
    )
    result = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert result["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_a_malformed_permission_declaration_is_refused(monkeypatch):
    """A permission that is not a string is not a permission.

    It cannot equal a member of the dangerous set, so treating it as data made
    the gate answer "nothing dangerous declared" about a declaration it had not
    understood — and `["shell.execute"]` in place of `"shell.execute"` is a
    plausible manifest typo, not an exotic one. The unhashable case also used to
    raise `TypeError` out of `invoke` from the membership test.
    """
    odd = _Manager(_Manifest("com-example-thermal", [_Step("scan", [["shell.execute"]])]))
    result = await _invoke(_invoker(odd), "com-example-thermal", "scan")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "capability manifest" in result["error"]["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manifest",
    [
        # steps declared as a scalar. Iterable, so the old walk read "s", "c",
        # "a", "n" as four steps, matched none of them, and reported that the
        # plugin declared nothing.
        _Manifest("com-example-thermal", "scan"),
        # steps declared as a mapping keyed by step id — also iterable, also
        # into something that is not a step.
        _Manifest("com-example-thermal", {"scan": {"required_permissions": []}}),
        # A step entry that is not a step object.
        _Manifest("com-example-thermal", ["scan"]),
    ],
    ids=["steps-string", "steps-mapping", "step-entry-string"],
)
async def test_a_malformed_steps_declaration_is_refused(manifest, caplog):
    """A manifest whose steps are not steps cannot be read as declaring nothing."""
    with caplog.at_level(logging.WARNING, logger="core.runtime.invoke"):
        result = await _invoke(_invoker(_Manager(manifest)), "com-example-thermal", "scan")

    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "capability manifest" in result["error"]["message"]
    # Generic to the caller, diagnosable to the operator: the envelope says what
    # could not be checked and the log says what shape was wrong.
    assert "com-example-thermal" in result["error"]["message"]
    # The structural reason stays internal; the caller learns only that the
    # manifest could not be validated.
    assert "not a step object" not in result["error"]["message"]
    assert "not a list" not in result["error"]["message"]
    assert "Malformed capability manifest" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permissions",
    [
        # The typo that matters: a single permission written as a scalar. Every
        # character of it is iterable and none of them is "shell.execute", so
        # the gate used to allow the step that asked for shell execution.
        "shell.execute",
        {"shell.execute": True},
        ["shell.execute", None],
        [{"name": "shell.execute"}],
    ],
    ids=["scalar", "mapping", "none-entry", "object-entry"],
)
async def test_a_malformed_permission_declaration_is_refused_by_shape(
    permissions, monkeypatch, caplog
):
    """Permissions that are not a list of strings deny, granted or not."""
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "com-example-thermal:shell.execute")
    manager = _Manager(_Manifest("com-example-thermal", [_Step("scan", permissions)]))

    with caplog.at_level(logging.WARNING, logger="core.runtime.invoke"):
        result = await _invoke(_invoker(manager), "com-example-thermal", "scan")

    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "capability manifest" in result["error"]["message"]
    # The declaration itself is plugin-supplied and never echoed back.
    assert "shell.execute" not in result["error"]["message"]
    assert "Malformed capability manifest" in caplog.text


@pytest.mark.asyncio
async def test_a_real_dict_manifest_refuses_a_scalar_permission_declaration(monkeypatch):
    """The same shapes, against the manifest type that actually ships."""
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    manager = _Manager(
        _real_manifest(
            "com-example-thermal", [{"id": "scan", "required_permissions": "shell.execute"}]
        )
    )

    result = await _invoke(_invoker(manager), "com-example-thermal", "scan")

    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "capability manifest" in result["error"]["message"]


@pytest.mark.asyncio
async def test_a_well_formed_empty_declaration_is_still_allowed():
    """Fail-closed on malformed, not on quiet: silence is a legal manifest."""
    manager = _Manager(
        _real_manifest("com-example-thermal", [{"id": "get", "required_permissions": []}])
    )
    result = await _invoke(_invoker(manager), "com-example-thermal", "get")
    assert result["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_an_unreadable_manifest_does_not_open_the_gate(monkeypatch):
    """A manifest lookup that throws must not fail open.

    Nor a manifest whose *fields* throw after the lookup already succeeded.
    ``_policy_denial`` runs before ``invoke``'s try block, so an exception out of
    the step walk did not fail closed and did not fail open either — it left
    ``invoke`` entirely, so the step was neither allowed nor denied, just
    crashed, with our traceback attached to the answer.
    """
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "anything")
    result = await _invoke(_invoker(_Manager(raises=True)), "shell", "exec")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"

    # The steps list itself is unreadable.
    unreadable_steps = _Manager(_Manifest("com-example-thermal", [], steps_raise=True))
    result = await _invoke(_invoker(unreadable_steps), "shell", "exec")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"

    # The steps list reads, but a step id inside it does not.
    unreadable_step_id = _Manager(
        _Manifest("com-example-thermal", [_Step("scan", id_raises=True)])
    )
    result = await _invoke(_invoker(unreadable_step_id), "shell", "exec")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"

    # The step reads, but a permission it declares does not. Against a module id
    # the filter allows, so the permission is what decides the answer: the gate
    # used to hand the raw value to `missing_permissions`, which found it absent
    # from the dangerous set and allowed the step. An undeclarable permission is
    # not an absent one.
    unrenderable_permission = MagicMock()
    unrenderable_permission.__str__.side_effect = RuntimeError(MANIFEST_FAILURE_DETAIL)
    unrenderable = _Manager(
        _Manifest("com-example-thermal", [_Step("get", [unrenderable_permission])])
    )
    result = await _invoke(_invoker(unrenderable), "com-example-thermal", "get")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert MANIFEST_FAILURE_DETAIL not in result["error"]["message"]


@pytest.mark.asyncio
async def test_a_plugin_with_no_manifest_still_meets_the_module_filter():
    """Silence about permissions must not buy a denied module id."""
    result = await _invoke(_invoker(_Manager(manifest=None)), "shell", "exec")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"


# ---------------------------------------------------------------------------
# The gate against the manifest shape that actually ships
# ---------------------------------------------------------------------------
#
# Everything above uses attribute-style doubles. The real ``PluginManifest``
# stores ``steps`` as a list of plain dicts parsed from manifest JSON, and
# ``getattr(step, "id", "")`` on a dict returns "" for every step — so the gate
# matched no step, read no permissions, and waved every real plugin through no
# matter what it declared. These pin the shipping shape.


def _real_manifest(plugin_id, steps):
    """A genuine PluginManifest, steps as the dicts from_dict() produces."""
    return PluginManifest.from_dict(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "vendor": "test",
            "entryPoint": "main.py",
            "steps": steps,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("permission_key", ["required_permissions", "requiredPermissions"])
async def test_a_real_dict_manifest_enforces_dangerous_permissions(
    monkeypatch, permission_key
):
    """A dict step declaring shell.execute is refused without a plugin grant."""
    monkeypatch.setenv("FLYTO_GRANTED_PERMISSIONS", "shell.execute")
    manifest = _real_manifest(
        "com-example-thermal", [{"id": "scan", permission_key: ["shell.execute"]}]
    )
    manager = _Manager(manifest)

    result = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "ungranted permission" in result["error"]["message"]
    # The denial names the plugin, so the operator knows which grant to write.
    assert "com-example-thermal" in result["error"]["message"]

    monkeypatch.setenv("FLYTO_PLUGIN_GRANTS", "com-example-thermal:shell.execute")
    allowed = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert allowed["error"]["code"] != "MODULE_POLICY_DENIED"


@pytest.mark.asyncio
async def test_a_real_dict_manifest_reads_only_the_named_step(monkeypatch):
    """Dict steps must be matched by id, not collapsed into one another."""
    manager = _Manager(
        _real_manifest(
            "com-example-thermal",
            [
                {"id": "scan"},
                {"id": "wipe", "required_permissions": ["shell.execute"]},
            ],
        )
    )
    assert (
        await _invoke(_invoker(manager), "com-example-thermal", "scan")
    )["error"]["code"] != "MODULE_POLICY_DENIED"

    denied = await _invoke(_invoker(manager), "com-example-thermal", "wipe")
    assert denied["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "ungranted permission" in denied["error"]["message"]


@pytest.mark.asyncio
async def test_a_real_dict_manifest_enforces_the_plugin_denylist(monkeypatch):
    """Plugin identity must be read off a dict-stepped manifest too."""
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "com-example-thermal")
    manager = _Manager(_real_manifest("com-example-thermal", [{"id": "scan"}]))
    result = await _invoke(_invoker(manager), "com-example-thermal", "scan")
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "not permitted here" in result["error"]["message"]


@pytest.mark.asyncio
async def test_a_lookup_failure_denies_a_module_the_filter_would_allow():
    """Fail closed on an unreadable manifest, not just where the id is denied.

    ``http.get`` clears the module filter on its own, so this is the case where
    swallowing the lookup error is indistinguishable from "the plugin declared
    nothing dangerous" — and the gate used to make exactly that assumption.
    """
    result = await _invoke(_invoker(_Manager(raises=True)), "com-example-thermal", "get")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "manifest lookup" in result["error"]["message"]
    # The identity survives the failure; a denial that cannot name the plugin
    # cannot be acted on.
    assert "com-example-thermal" in result["error"]["message"]

    # Same for a manifest that was found but cannot be read: an unreadable
    # declaration is not an empty declaration, so this must deny too rather than
    # wave through a module nothing else objects to.
    unreadable = _Manager(_Manifest("com-example-thermal", [], steps_raise=True))
    result = await _invoke(_invoker(unreadable), "com-example-thermal", "get")
    assert result["ok"] is False
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "capability manifest" in result["error"]["message"]
    assert "com-example-thermal" in result["error"]["message"]


@pytest.mark.asyncio
async def test_a_lookup_failure_reason_says_nothing_about_the_cause(caplog):
    """Fail closed without turning the denial into a disclosure channel.

    The caller reading this envelope may be the plugin author or an MCP client,
    and the reason for a manifest lookup failure is our internal state — a store
    path, a connection string, a driver traceback. So the envelope carries the
    outline only, and the operator gets the whole cause from the log, keyed by
    the plugin id the denial already names.
    """
    # Both ways the manifest can be unevaluable: the lookup throws, and the
    # lookup succeeds but a field read throws. The second reaches the caller
    # through a different branch, so it needs its own proof that it says nothing.
    managers = (
        _Manager(raises=True),
        _Manager(_Manifest("com-example-thermal", [], steps_raise=True)),
        _Manager(_Manifest("com-example-thermal", [_Step("get", id_raises=True)])),
    )
    for manager in managers:
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="core.runtime.invoke"):
            result = await _invoke(_invoker(manager), "com-example-thermal", "get")

        message = result["error"]["message"]
        assert result["error"]["code"] == "MODULE_POLICY_DENIED"
        assert MANIFEST_FAILURE_DETAIL not in message
        # Spelled out, so a future reword that reintroduces any one of these
        # fails here rather than in production: path, secret, exception class.
        for leaked in ("/srv/flyto", "manifest.json", "s3cr3t", "RuntimeError"):
            assert leaked not in message

        # Fail closed, and still be diagnosable: the detail is in the log.
        assert MANIFEST_FAILURE_DETAIL in caplog.text
        assert "com-example-thermal" in caplog.text


@pytest.mark.asyncio
async def test_an_unmanifested_plugin_still_answers_to_the_plugin_denylist(monkeypatch):
    """Identity defaults to the requested plugin id, so the list still binds."""
    monkeypatch.setenv("FLYTO_PLUGIN_DENYLIST", "com-example-thermal")
    result = await _invoke(
        _invoker(_Manager(manifest=None)), "com-example-thermal", "scan"
    )
    assert result["error"]["code"] == "MODULE_POLICY_DENIED"
    assert "not permitted here" in result["error"]["message"]
