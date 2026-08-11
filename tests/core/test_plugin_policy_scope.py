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

import threading
import time

import pytest

import core.modules.registry.core as registry_core
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


# A metadata row that refuses to be copied.
#
# Every boundary below is defended by `copy.deepcopy`, and a deep copy is not
# something the caller cannot refuse: `deepcopy` dispatches on the *exact* type
# and otherwise asks the value how to copy itself. A `dict` subclass answering
# `__deepcopy__` with `self` therefore passes straight through every one of
# those boundaries, and the registry ends up storing — or handing back — the
# caller's live object, which is precisely the aliasing the copies exist to
# close. Nothing about the row looks wrong: it is a dict, it compares equal to
# one, `isinstance` says yes — so each boundary asserts `type(row) is dict`, the exact built-in.
#
# Built with `type()` rather than declared, so the hostile behaviour is data a
# test installs on a row rather than a shape this module advertises.
_ALIASING_DICT = type(
    "_AliasingDict",
    (dict,),
    {
        "__doc__": "A dict subclass whose deep copy is itself.",
        "__deepcopy__": lambda self, memo: self,
        "__copy__": lambda self: self,
    },
)


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
    # Told through a row that declines to be copied, which is the version of
    # the lie that survives a `deepcopy`-only defence: the registry would store
    # this very object, so the stamp `register` writes could be written back out
    # by the caller the instant it returns.
    told = _ALIASING_DICT({"plugin": "", "required_permissions": ["shell.execute"]})
    ModuleRegistry._loading_plugin = "thermal"
    try:
        ModuleRegistry.register("thermal.liar", _Noop, told)
    finally:
        ModuleRegistry._loading_plugin = ""

    try:
        stored = ModuleRegistry._metadata["thermal.liar"]
        assert stored is not told, "the registry stored the caller's own row"
        assert type(stored) is dict, f"a subclass survived registration: {type(stored)}"
        told["plugin"] = ""
        assert stored["plugin"] == "thermal"
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


def test_a_retained_reference_cannot_rewrite_ownership_after_registration():
    """The same lie as the two tests above, told a moment later.

    `register` stamped and stored the caller's own dict, so the unconditional
    assignment only held until the caller — which still had the reference —
    wrote to it again. Handing over metadata and then setting `plugin` to `""`
    reassigns the module to flyto-core, the identity the process-global
    permission grant reaches, without ever passing through `register`.
    """
    retained = {"version": "1.0.0"}
    ModuleRegistry._loading_plugin = "thermal"
    try:
        ModuleRegistry.register("thermal.retained", _Noop, retained)
    finally:
        ModuleRegistry._loading_plugin = ""

    try:
        retained["plugin"] = ""
        retained["required_permissions"] = ["fs.write"]
        stored = ModuleRegistry.get_metadata("thermal.retained")
        assert stored["plugin"] == "thermal"
        assert "required_permissions" not in stored
        # Ownership queries agree with the stored row, not the caller's copy.
        assert "thermal.retained" in ModuleRegistry._owned_by("thermal")
        assert "thermal.retained" not in ModuleRegistry._owned_by("")
    finally:
        ModuleRegistry.unregister("thermal.retained")


def test_a_retained_reference_cannot_grow_the_stored_permissions():
    """The same aliasing as the test above, one level down.

    `register` copied the caller's dict, which detached the top mapping and
    nothing else: the stored `required_permissions` list was still the caller's
    object. A plugin could hand over an honest declaration, keep its reference,
    and afterwards append `shell.execute` to the list the registry stores —
    acquiring reach without ever passing back through `register`, which is the
    one place ownership and defaults are assigned. Enforcement reads the stored
    row, so the appended permission is one nobody ever granted or reviewed.
    """
    # The row is an `_ALIASING_DICT`, so the copy alone is not what saves this:
    # `deepcopy` would hand the registry the caller's object back unchanged, and
    # the append below would land on the stored `required_permissions`. What
    # closes it is plainifying the top mapping through `dict` first, which puts
    # the copy under the interpreter's rules rather than the row's.
    retained = _ALIASING_DICT(
        {"version": "1.0.0", "required_permissions": ["network.read"]}
    )
    ModuleRegistry._loading_plugin = "thermal"
    try:
        ModuleRegistry.register("thermal.creep", _Noop, retained)
    finally:
        ModuleRegistry._loading_plugin = ""

    try:
        retained["required_permissions"].append("shell.execute")
        stored = ModuleRegistry._metadata["thermal.creep"]
        assert stored is not retained
        assert type(stored) is dict
        assert stored["required_permissions"] == ["network.read"]
        assert stored["plugin"] == "thermal"
    finally:
        ModuleRegistry.unregister("thermal.creep")


def test_a_retained_reference_cannot_rewrite_a_stored_param_schema():
    """`params_schema` is the deepest thing a row carries, and the one a caller
    is most likely to keep a handle on — it is usually built once at import time
    and shared. Rewriting a default, or flipping `required`, changes what every
    later reader of the catalog is told about a module."""
    schema = {"path": {"type": "string", "required": True, "default": "/tmp/safe"}}
    retained = {"version": "1.0.0", "params_schema": schema, "tags": ["fs"]}
    ModuleRegistry.register("firstparty.deep", _Noop, retained)

    try:
        schema["path"]["default"] = "/etc/passwd"
        schema["path"]["required"] = False
        schema["injected"] = {"type": "string"}
        retained["tags"].append("smuggled")

        stored = ModuleRegistry._metadata["firstparty.deep"]
        assert stored["params_schema"]["path"]["default"] == "/tmp/safe"
        assert stored["params_schema"]["path"]["required"] is True
        assert "injected" not in stored["params_schema"]
        assert stored["tags"] == ["fs"]
    finally:
        ModuleRegistry.unregister("firstparty.deep")


def test_a_returned_row_cannot_be_edited_back_into_the_registry():
    """The read boundary, which is the same hole facing the other way.

    `get_metadata` localises into a one-level copy, so everything nested in the
    answer was the live row's own object. A caller that appended to the
    `required_permissions` list it was handed changed what the registry stores
    and what policy enforcement later reads — from outside the lock, with no
    registration involved, and durably, because the row is process-global.
    """
    ModuleRegistry.register(
        "firstparty.readback",
        _Noop,
        {
            "version": "1.0.0",
            "required_permissions": ["network.read"],
            "tags": ["safe"],
            "params_schema": {"path": {"type": "string", "default": "/tmp/safe"}},
        },
    )
    try:
        handed = ModuleRegistry.get_metadata("firstparty.readback")
        handed["required_permissions"].append("shell.execute")
        handed["tags"].append("smuggled")
        handed["params_schema"]["path"]["default"] = "/etc/passwd"
        handed["plugin"] = "thermal"

        stored = ModuleRegistry._metadata["firstparty.readback"]
        assert stored["required_permissions"] == ["network.read"]
        assert stored["tags"] == ["safe"]
        assert stored["params_schema"]["path"]["default"] == "/tmp/safe"
        assert stored["plugin"] == ""
        # And the next reader is told the same thing the first one was.
        assert ModuleRegistry.get_metadata("firstparty.readback") == stored

        # The same boundary, against a stored row that declines to be copied.
        # `_localize_metadata` deep-copies before localising, and `deepcopy`
        # defers to the value for anything that is not exactly a `dict` — so a
        # subclass answering `__deepcopy__` with itself would be handed to the
        # caller *as the live row*, and the whole read boundary would be undone
        # by one method. Installed directly, because `register` now refuses to
        # store one: this is the row shape that reached `_metadata` by any other
        # route.
        hostile = _ALIASING_DICT(stored)
        ModuleRegistry._metadata["firstparty.readback"] = hostile
        handed_again = ModuleRegistry.get_metadata("firstparty.readback")
        assert handed_again is not hostile, (
            "the public read handed back the live row itself"
        )
        assert type(handed_again) is dict
        handed_again["required_permissions"].append("shell.execute")
        handed_again["tags"].append("smuggled")
        handed_again["plugin"] = "thermal"
        assert hostile["required_permissions"] == ["network.read"]
        assert hostile["tags"] == ["safe"]
        assert hostile["plugin"] == ""
    finally:
        ModuleRegistry.unregister("firstparty.readback")


def test_two_readers_do_not_share_the_row_they_were_handed():
    """Two callers holding one nested object is the same defect between peers:
    whichever writes first silently rewrites what the other is looking at."""
    ModuleRegistry.register(
        "firstparty.twice", _Noop, {"version": "1.0.0", "tags": ["safe"]}
    )
    try:
        first = ModuleRegistry.get_all_metadata(filter_by_stability=False)[
            "firstparty.twice"
        ]
        second = ModuleRegistry.get_all_metadata(filter_by_stability=False)[
            "firstparty.twice"
        ]
        assert first["tags"] is not second["tags"]
        first["tags"].append("smuggled")
        assert second["tags"] == ["safe"]
    finally:
        ModuleRegistry.unregister("firstparty.twice")


def test_register_does_not_mutate_the_callers_metadata():
    """The other half of the aliasing: the caller's dict grew a `plugin` key and
    four defaults it never set, as a side effect of registering."""
    caller_owned = {"version": "1.0.0"}
    ModuleRegistry.register("firstparty.unmutated", _Noop, caller_owned)
    try:
        assert caller_owned == {"version": "1.0.0"}
        assert ModuleRegistry.get_metadata("firstparty.unmutated")["plugin"] == ""
    finally:
        ModuleRegistry.unregister("firstparty.unmutated")


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
    # _load_plugin catches the plugin's exception, rolls the pass back and
    # logs, so discovery returns normally even though the entry point raises
    # mid-registration; the assertion is what proves `finally` cleared it.
    ModuleRegistry.discover_plugins(force=True)
    assert ModuleRegistry._loading_plugin == ""


# -- discovery is a transaction over the registry ---------------------------
#
# Everything below drives discovery against described entry points rather than
# installed ones. The registry is process-global, so each test runs against an
# isolated copy of that state and puts the real one back.


class _Original(BaseModule):
    async def execute(self):  # pragma: no cover - never executed here
        return {}


class _Replacement(BaseModule):
    async def execute(self):  # pragma: no cover - never executed here
        return {}


# Every piece of registry state a discovery pass reads or writes. Saved and
# restored wholesale so a failing assertion cannot leak a half-built registry
# into the rest of the suite.
_REGISTRY_STATE = (
    "_modules",
    "_metadata",
    "_plugins",
    "_plugin_contributions",
    "_core_baseline",
    "_initialized",
    "_discovering",
    "_discovery_thread",
    "_loading_plugin",
    "_pass_registered",
    "_pass_touched",
    "_pass_displaced",
    "_started_empty",
    "_cleared",
)


class _Groups(list):
    """The entry points, in either shape ``_iter_entry_points`` asks for.

    It calls ``entry_points(group=...)`` on 3.10+ and ``entry_points().get(...)``
    below that. A plain list satisfies only the first, which would make these
    tests silently 3.10+-only against a package that supports 3.9.
    """

    def get(self, group, default=None):
        return list(self)


class _EntryPoint:
    """A described entry point.

    Discovery asks an entry point only for ``name``, ``value`` and ``load()``,
    so a plugin can be described here instead of built and installed as a
    distribution to describe it.
    """

    def __init__(self, name, register=None, value="fake_pkg:register_all"):
        self.name = name
        self.value = value
        self._register = register

    def load(self):
        return self._register if self._register is not None else (lambda: None)


def _registers(*module_ids, module_class=_Original, once=True):
    """A ``register_all`` that registers ``module_ids``.

    ``once=True`` is the common real shape: a package registers as an import
    side effect, the import is cached, and so every call after the first is a
    no-op that says nothing about what the plugin provides.
    """
    state = {"called": False}

    def register_all():
        if once and state["called"]:
            return
        state["called"] = True
        for module_id in module_ids:
            ModuleRegistry.register(module_id, module_class, {"version": "1.0.0"})

    return register_all


@pytest.fixture
def registry():
    saved = {attr: getattr(ModuleRegistry, attr) for attr in _REGISTRY_STATE}
    ModuleRegistry._modules = {}
    ModuleRegistry._metadata = {}
    ModuleRegistry._plugins = {}
    ModuleRegistry._plugin_contributions = {}
    ModuleRegistry._core_baseline = {}
    ModuleRegistry._initialized = False
    ModuleRegistry._discovering = False
    ModuleRegistry._discovery_thread = None
    ModuleRegistry._loading_plugin = ""
    ModuleRegistry._pass_registered = None
    ModuleRegistry._pass_touched = None
    ModuleRegistry._pass_displaced = {}
    ModuleRegistry._started_empty = False
    ModuleRegistry._cleared = False
    try:
        yield ModuleRegistry
    finally:
        for attr, value in saved.items():
            setattr(ModuleRegistry, attr, value)


@pytest.fixture
def installed(monkeypatch):
    """Replace the installed entry points with the ones a test describes."""

    def _install(*eps):
        monkeypatch.setattr(
            registry_core, "entry_points", lambda **kw: _Groups(eps), raising=False
        )
        return eps

    return _install


# -- a read is enough to make the registry honest --------------------------


def test_a_first_read_answers_about_what_is_installed(registry, installed):
    """Before this, the catalog reported an empty install until somebody
    happened to ask for a module by id and warmed it."""
    installed(_EntryPoint("thermal", _registers("thermal.scan")))

    assert "thermal.scan" in registry.list_all()


def test_a_read_from_inside_a_plugin_does_not_start_a_second_pass(registry, installed):
    """A plugin that reads the catalog while registering would otherwise load
    every plugin again underneath the pass already running."""
    seen = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        seen.append(sorted(registry.list_all()))

    installed(_EntryPoint("thermal", register_all))
    registry.discover_plugins(force=True)

    # Answered from the partial state, and only one pass ran.
    assert seen == [["thermal.scan"]]
    assert registry.get_plugins()["thermal"].module_count == 1


# -- the first discovery is serialised -------------------------------------
#
# Discovery is a process-global mutation with plugin code in the middle of it,
# so "who else is looking" is a real question. Two callers must be told apart:
#
#   The discovering thread itself, re-entering through a plugin. It is answered
#   from the partial state — the only answer available, since the work it would
#   be waiting for is its own.
#
#   Any other thread. It waits. The partial registry is not a smaller install,
#   it is one nobody has finished describing, and handing it over produced
#   snapshots that disagreed about the same machine depending on which thread
#   asked first.
#
# Each test below drives the deadlock-prone call from a daemon thread with a
# bounded join, so a regression fails the run instead of hanging it.


def _run_bounded(target, timeout=15.0):
    """Run ``target`` in a daemon thread; return whether it finished in time."""
    finished = threading.Event()

    def runner():
        try:
            target()
        finally:
            finished.set()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return finished.wait(timeout)


def test_a_reentrant_discovery_does_not_deadlock(registry, installed):
    """A plugin that calls back into discovery — directly or through a catalog
    read — must be answered, not made to wait for the pass it is inside.

    Serialising discovery is exactly the change that could make this hang, so
    it is pinned rather than assumed."""
    reached = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reached.append(sorted(registry.list_all()))
        reached.append(sorted(registry.discover_plugins()))
        reached.append(sorted(registry.get_catalog()["tier_counts"]))

    installed(_EntryPoint("thermal", register_all))

    assert _run_bounded(lambda: registry.discover_plugins(force=True)), (
        "Discovery deadlocked on its own thread: a plugin re-entering it waited "
        "for a pass only that thread could finish."
    )
    assert reached[0] == ["thermal.scan"]
    assert reached[1] == []  # no PluginInfo published yet — the pass is running
    assert registry.get_plugins()["thermal"].module_count == 1


def test_a_reentrant_discovery_does_not_start_a_second_pass(registry, installed):
    """The reentrancy escape must not be an escape into a nested pass.

    ``_discovery_lock`` is reentrant, so the owning thread would re-acquire it
    happily; what stops the second pass is the recorded owner, checked first."""
    loads = []

    def register_all():
        loads.append(1)
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        registry.discover_plugins(force=True)

    installed(_EntryPoint("thermal", register_all))

    assert _run_bounded(lambda: registry.discover_plugins(force=True))
    assert loads == [1]
    assert sorted(registry.list_all()) == ["thermal.scan"]


def test_a_concurrent_read_waits_for_the_whole_registry(registry, installed):
    """The defect: a read from another thread was answered from the middle of a
    discovery pass, so it saw whichever modules had registered so far."""
    reader_may_start = threading.Event()
    seen = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reader_may_start.set()
        # Long enough for the reader to arrive and block. If it is slow the
        # assertion still holds — this test cannot pass by accident, only be
        # weakened into a tautology, which the ordering assert below catches.
        time.sleep(0.3)
        registry.register("thermal.probe", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", register_all))

    def read():
        reader_may_start.wait(10)
        seen.append(sorted(registry.list_all()))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    registry.discover_plugins(force=True)
    reader.join(15)

    assert not reader.is_alive(), "The waiting reader never woke up."
    assert seen == [["thermal.probe", "thermal.scan"]], (
        "A concurrent reader was answered from a half-built registry."
    )


def test_a_concurrent_snapshot_describes_the_whole_install(registry, installed):
    """Why the partial answer mattered: the snapshot is what a resumed
    execution is matched against, and two threads must not record different
    module counts for one install."""
    reader_may_start = threading.Event()
    snapshots = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reader_may_start.set()
        time.sleep(0.3)
        registry.register("thermal.probe", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", register_all))

    def read():
        reader_may_start.wait(10)
        snapshots.append(registry.get_snapshot())

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    registry.discover_plugins(force=True)
    reader.join(15)

    assert not reader.is_alive()
    here = registry.get_snapshot()
    assert snapshots[0].module_count == here.module_count == 2
    assert snapshots[0].modules_hash == here.modules_hash


def test_only_one_thread_discovers_at_a_time(registry, installed):
    """Concurrent first reads must collapse into one pass, not race into
    several that overwrite each other's rows."""
    loads = []
    barrier = threading.Barrier(4, timeout=15)

    def register_all():
        loads.append(1)
        time.sleep(0.2)
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", register_all))

    results = []

    def read():
        barrier.wait()
        results.append(sorted(registry.list_all()))

    readers = [threading.Thread(target=read, daemon=True) for _ in range(4)]
    for thread in readers:
        thread.start()
    for thread in readers:
        thread.join(20)

    assert not any(thread.is_alive() for thread in readers)
    assert loads == [1], f"discovery ran {len(loads)} times for one first read"
    assert results == [["thermal.scan"]] * 4


def test_a_concurrent_read_waits_for_a_forced_pass_too(registry, installed):
    """The escape the first version of this left open.

    ``force=True`` rebuilds a registry that is *already* initialised, and never
    lowers ``_initialized`` while it does. A reader that asked "is it
    initialised?" before "is a pass running?" was therefore told yes and went
    straight to the module dict — mid-rebuild, past the lock, reading exactly
    the partial state the lock exists to hide. Every forced rediscovery is this
    case, including every ``refresh()``, so it is the common one rather than the
    corner.
    """
    reader_may_start = threading.Event()
    seen = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reader_may_start.set()
        time.sleep(0.3)
        registry.register("thermal.probe", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", register_all, value="thermal_pkg:register_all"))

    # The pass below is a *re*discovery: the registry is initialised and already
    # holds a first-party module before it starts.
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry._initialized = True
    assert registry._initialized

    def read():
        reader_may_start.wait(10)
        seen.append(sorted(registry.list_all()))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    registry.discover_plugins(force=True)
    reader.join(15)

    assert not reader.is_alive(), "The waiting reader never woke up."
    assert seen == [["http.get", "thermal.probe", "thermal.scan"]], (
        "A reader was answered from the middle of a forced rediscovery because "
        "_initialized was still standing from the previous pass."
    )


def test_a_concurrent_snapshot_waits_for_a_forced_pass_too(registry, installed):
    """Same escape, at the surface where it costs the most.

    ``get_snapshot()`` is what a resumed execution is matched against, so a
    snapshot taken from the middle of a refresh binds a checkpoint to a
    module set that never existed."""
    reader_may_start = threading.Event()
    snapshots = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reader_may_start.set()
        time.sleep(0.3)
        registry.register("thermal.probe", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", register_all, value="thermal_pkg:register_all"))
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry._initialized = True

    def read():
        reader_may_start.wait(10)
        snapshots.append(registry.get_snapshot())

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    registry.discover_plugins(force=True)
    reader.join(15)

    assert not reader.is_alive()
    here = registry.get_snapshot()
    assert snapshots[0].module_count == here.module_count == 3
    assert snapshots[0].modules_hash == here.modules_hash


def test_a_forced_pass_does_not_deadlock_its_own_thread(registry, installed):
    """Checking the pass before the flag must not cost the reentrancy escape:
    a plugin reading the catalog during a *forced* pass is still answered."""
    reached = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reached.append(sorted(registry.list_all()))

    installed(_EntryPoint("thermal", register_all))
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry._initialized = True

    assert _run_bounded(lambda: registry.discover_plugins(force=True)), (
        "A forced pass deadlocked on its own thread."
    )
    assert reached == [["http.get", "thermal.scan"]]


def test_the_discovering_thread_is_forgotten_when_the_pass_ends(registry, installed):
    """A leaked owner id would let a later, unrelated caller on the same thread
    skip discovery entirely and read an empty registry as the truth."""
    installed(_EntryPoint("thermal", _explodes_after("thermal.scan")))
    registry.discover_plugins(force=True)

    assert registry._discovery_thread is None
    assert registry._discovering is False


# -- the read itself is the critical section -------------------------------
#
# Serialising the *decision* to discover left the last gap. `_ensure_discovered`
# took the lock, concluded "already initialised", and dropped it — and only then
# did the caller copy `_modules` or walk `_metadata`. Everything below that line
# ran unprotected, so a forced pass starting in that window rewrote the dicts
# under a read already in progress. That is worse than a stale answer: the
# caller gets half a registry from before the rebuild and half from after, or a
# `RuntimeError: dictionary changed size during iteration` on a bad interleave.
#
# The fix is that a public read holds the lock for its whole body. The test
# below is the one that can tell the two designs apart, because it puts the
# reader exactly where the old code was unprotected: past the fast path, before
# the copy.


def test_a_forced_pass_waits_for_a_reader_that_is_past_the_fast_path(
    registry, installed, monkeypatch
):
    """The gap `_ensure_discovered` alone could not close.

    Every other concurrency test here starts the reader *before* the decision
    point, so the lock inside `_ensure_discovered` is enough to hold it. This one
    starts it *after*: the registry is already initialised, the reader takes the
    fast path, and is then suspended at the precise instant the old code had
    nothing held — between the check and the copy.

    Two things must hold from there. A forced pass arriving in that window must
    not mutate anything until the reader returns, and what the reader returns
    must be the whole pre-pass registry rather than some blend of the two. Then,
    once it does return, the forced pass must run to completion and leave a whole
    new registry behind — the lock must delay the rebuild, not cancel it.
    """
    order = []
    reader_inside = threading.Event()
    reader_may_finish = threading.Event()
    reader_saw = []
    reader_ident = []
    paused = []

    # Captured before the patch below replaces the attribute, so the hook can
    # still run the real fast-path check rather than stub it out. The pause has
    # to sit *after* a genuine `_ensure_discovered`, or the test proves nothing
    # about the path a real reader takes.
    real_ensure = registry._ensure_discovered

    def hook(cls):
        real_ensure()
        # Only the reader is suspended, and only once. The hook is on the class,
        # so the setup and assertion reads below arrive here too; pausing those
        # would hang the test thread on an event only the test thread can set.
        if paused or not reader_ident or threading.get_ident() != reader_ident[0]:
            return
        paused.append(True)
        # The fast path is the route under test. If discovery were running, or
        # the registry were uninitialised, the reader would have blocked inside
        # `real_ensure` above and this test would be re-proving 1.2.0.
        assert cls._initialized is True
        assert cls._discovery_thread is None
        order.append("reader-past-fast-path")
        reader_inside.set()
        assert reader_may_finish.wait(15), "the test never released the reader"

    monkeypatch.setattr(ModuleRegistry, "_ensure_discovered", classmethod(hook))

    def register_all():
        order.append("discovery-mutates")
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        registry.register("thermal.probe", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", register_all, value="thermal_pkg:register_all"))

    # The pre-pass registry: initialised, non-empty, and entirely first-party.
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry.register("http.post", _Original, {"version": "1.0.0"})
    registry._initialized = True
    before = registry.get_snapshot()

    def read():
        # Published before the read starts, so the hook can tell this thread
        # from the test thread that set everything up.
        reader_ident.append(threading.get_ident())
        reader_saw.append(sorted(registry.list_all()))

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    assert reader_inside.wait(15), "the reader never reached the fast path"

    discovery_done = threading.Event()
    forcer_entered = threading.Event()

    def rediscover():
        # Set immediately before the call, so waiting on it below means the
        # forced pass has actually been attempted. Without it the negative
        # assertion that follows can pass for the wrong reason: a thread that
        # has not yet reached `discover_plugins` at all — still starting up,
        # descheduled, or slow under a loaded CI box — has not completed a pass
        # either, and the test would report the lock holding when nothing had
        # tried to take it.
        forcer_entered.set()
        registry.discover_plugins(force=True)
        discovery_done.set()

    forcer = threading.Thread(target=rediscover, daemon=True)
    forcer.start()
    assert forcer_entered.wait(15), "the forcing thread never reached discovery"

    # Every chance to get in front of the suspended reader. Under the old design
    # it took it: `discover_plugins(force=True)` acquires an uncontended lock,
    # because the reader let go of it the moment the fast path returned.
    assert not discovery_done.wait(0.5), (
        "A forced pass completed while a reader was mid-read."
    )
    assert order == ["reader-past-fast-path"], (
        "A forced pass mutated the registry underneath a reader that had already "
        "passed the initialised fast path."
    )
    # Read directly, not through the API: the point is the underlying rows, and
    # a locked accessor would simply block here.
    assert sorted(registry._modules) == ["http.get", "http.post"]

    reader_may_finish.set()
    reader.join(15)
    assert not reader.is_alive(), "The paused reader never returned."

    # A whole *old* snapshot. Not one module of the pass that was already queued
    # behind it leaked in, and none of its own were lost.
    assert reader_saw == [["http.get", "http.post"]], (
        f"The reader was answered from a rebuild in progress: {reader_saw}"
    )

    # Delayed, not cancelled: the pass resumes the instant the reader lets go.
    assert discovery_done.wait(15), "The queued forced pass never ran."
    forcer.join(5)
    assert not forcer.is_alive()
    assert order == ["reader-past-fast-path", "discovery-mutates"]

    # A whole *new* snapshot, and one nobody observed an intermediate state of.
    after = registry.get_snapshot()
    assert sorted(registry.list_all()) == [
        "http.get",
        "http.post",
        "thermal.probe",
        "thermal.scan",
    ]
    assert after.module_count == 4
    assert after.modules_hash != before.modules_hash
    assert registry.get_plugins()["thermal"].module_count == 2


def test_a_locked_read_keeps_its_name_and_docstring():
    """`@_synchronized` wraps the whole public surface, and
    `docs/reference/python-api.md` is generated by introspecting that surface.
    Without `functools.wraps` every method would be reported as `guarded` with
    no docstring, so the reference silently stops describing the registry."""
    for name in ("get", "list_all", "get_snapshot", "register", "clear"):
        method = getattr(ModuleRegistry, name)
        assert method.__name__ == name
        assert method.__doc__, f"{name} lost its docstring to the decorator"
        assert method.__module__ == registry_core.__name__


def test_a_plugin_still_reads_and_writes_during_its_own_pass(registry, installed):
    """The lock is an RLock for a reason, and the reason is reachable from
    plugin code: `register_all` runs with the lock already held by the pass that
    called it, and every registration and catalog read it makes now goes through
    the same lock. A non-reentrant one would deadlock the discovering thread
    against itself on the plugin's very first `register()`."""
    reached = []

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        reached.append(sorted(registry.list_all()))
        registry.unregister("http.post")
        reached.append(registry.has("http.post"))
        reached.append(registry.module_count())
        reached.append(sorted(registry.get_all_metadata(filter_by_stability=False)))

    installed(_EntryPoint("thermal", register_all, value="thermal_pkg:register_all"))
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry.register("http.post", _Original, {"version": "1.0.0"})
    registry._initialized = True

    assert _run_bounded(lambda: registry.discover_plugins(force=True)), (
        "A plugin deadlocked against the pass running it: the discovery lock "
        "stopped being reentrant."
    )
    assert reached == [
        ["http.get", "http.post", "thermal.scan"],
        False,
        2,
        ["http.get", "thermal.scan"],
    ]


# -- what discovery hands back is a copy ------------------------------------
#
# `_plugins` is process-global and discovery rewrites it in place, so handing a
# caller the dict itself hands them a live view of registry state rather than an
# answer. Two things go wrong with that, and the lock stops neither.
#
# The mapping keeps changing after the lock is released. A caller that keeps
# what it was given — a runtime that records the plugin set at startup, a
# snapshot written beside a checkpoint — finds it gaining and losing plugins on
# somebody else's schedule, and iterating it while a pass runs raises
# `RuntimeError: dictionary changed size during iteration`. That is exactly the
# torn read `@_synchronized` exists to prevent, smuggled out past it inside the
# return value.
#
# And a write to what the caller was handed *is* a write to the registry's
# record of what is installed, made without calling `register()` and without
# holding the lock. `get_plugins()` has always copied for this reason; the
# discovery paths did not, and `refresh()` — the call most likely to be used for
# exactly this bookkeeping — returned `discover_plugins`' value straight through.


def test_no_discovery_path_hands_back_the_live_plugin_dict(registry, installed):
    """Every route out, including the two that return without running a pass:
    the reentrant answer to plugin code, the already-initialised fast path, the
    pass itself, and `refresh()`."""
    from_inside = []

    def reads_during_its_own_pass():
        registry.register("vision.observe", _Original, {"version": "1.0.0"})
        # Plugin code, re-entering a pass that is still writing to _plugins.
        # This is the path where aliasing costs the most.
        from_inside.append(registry.discover_plugins())

    installed(
        _EntryPoint("thermal", _registers("thermal.scan")),
        _EntryPoint(
            "vision", reads_during_its_own_pass, value="vision_pkg:register_all"
        ),
    )

    forced = registry.discover_plugins(force=True)
    fast_path = registry.discover_plugins()
    refreshed = registry.refresh()

    assert from_inside, "the reentrant path never ran"
    # Not an incidental check: the pass had already published thermal by the
    # time vision re-entered, so this is a non-empty mapping and the identity
    # assertion below cannot pass merely because two empty dicts differ.
    assert sorted(from_inside[0]) == ["thermal"]

    for returned in (forced, fast_path, refreshed, *from_inside):
        assert returned is not registry._plugins, (
            "A discovery path handed back the live registry dict, so the caller "
            "holds registry state instead of an answer about it."
        )
    assert sorted(forced) == sorted(refreshed) == ["thermal", "vision"]
    assert sorted(fast_path) == ["thermal", "vision"]


def test_a_caller_cannot_edit_the_registry_through_what_it_was_handed(
    registry, installed
):
    """The mapping is a report, not a handle. Renaming a plugin in it must not
    rename it in the registry — that would be an unlocked write to the record of
    what is installed, by a caller that never called `register()`."""
    installed(_EntryPoint("thermal", _registers("thermal.scan")))

    handed = registry.discover_plugins(force=True)
    assert sorted(handed) == ["thermal"]

    handed["ghost"] = handed.pop("thermal")
    handed["impostor"] = handed["ghost"]

    assert sorted(registry.get_plugins()) == ["thermal"]
    assert registry.get_plugins()["thermal"].module_count == 1
    assert registry.is_plugin_loaded("thermal")
    assert not registry.is_plugin_loaded("ghost")
    assert not registry.is_plugin_loaded("impostor")


def test_a_plugin_cannot_empty_the_registry_record_it_was_handed(registry, installed):
    """Same write, from inside a running pass — where the dict a plugin is
    handed is the very one the pass is still filling in. A plugin that clears it
    would erase the plugins already loaded ahead of it, and the pass would go on
    to publish the rest into a record missing them."""

    def clears_what_it_is_handed():
        registry.register("vision.observe", _Original, {"version": "1.0.0"})
        registry.discover_plugins().clear()

    installed(
        _EntryPoint("thermal", _registers("thermal.scan")),
        _EntryPoint(
            "vision", clears_what_it_is_handed, value="vision_pkg:register_all"
        ),
    )

    registry.discover_plugins(force=True)

    assert sorted(registry.get_plugins()) == ["thermal", "vision"], (
        "A plugin erased the registry's record of the plugins loaded before it "
        "by clearing the mapping discovery handed it."
    )
    assert registry.get_plugins()["thermal"].module_count == 1


def test_a_caller_cannot_edit_the_registry_through_a_value_it_was_handed(
    registry, installed
):
    """Copying the mapping closes the door on the mapping, not on the values in
    it. The copy is shallow — the `PluginInfo` objects in it are the ones in
    `_plugins`, shared deliberately — so a caller that cannot add or remove a
    plugin could still have rewritten what one *says* about itself: its size,
    its version, the entry point it came from. That is the same unlocked write
    to registry state by one shorter route, and `module_count` is the field a
    plugin's billing and an operator's install report are read from.

    `PluginInfo` is frozen, so the write raises rather than landing."""
    installed(_EntryPoint("thermal", _registers("thermal.scan")))

    handed = registry.discover_plugins(force=True)
    info = handed["thermal"]
    # The same object the registry holds: sharing it is the design, freezing it
    # is what makes the sharing safe.
    assert info is registry._plugins["thermal"]

    for field_name, value in (
        ("module_count", 99),
        ("name", "ghost"),
        ("version", "9.9.9"),
        ("entry_point", "impostor_pkg:register_all"),
    ):
        with pytest.raises(AttributeError):
            setattr(info, field_name, value)

    assert registry.get_plugins()["thermal"].module_count == 1
    assert registry.get_plugins()["thermal"].name == "thermal"
    assert registry.get_snapshot().plugins == {
        "thermal": registry._plugins["thermal"].version
    }


def test_a_new_pass_replaces_a_plugin_info_rather_than_editing_it(registry, installed):
    """The freeze must not have been bought by making the registry unable to
    report a change. A plugin whose size changes gets a *new* value, which is
    also the honest record: a count is a fact about the pass that took it."""
    installed(_EntryPoint("thermal", _registers("thermal.scan")))
    registry.discover_plugins(force=True)
    first = registry.get_plugins()["thermal"]
    assert first.module_count == 1

    installed(
        _EntryPoint("thermal", _registers("thermal.scan", "thermal.probe"))
    )
    registry.refresh()

    second = registry.get_plugins()["thermal"]
    assert second.module_count == 2
    assert second is not first
    assert first.module_count == 1, "the earlier report was edited in place"


def test_a_retained_mapping_does_not_change_under_its_caller(registry, installed):
    """The other half: a caller that keeps the result must keep an answer about
    one instant, not a window onto whatever the registry becomes next."""
    installed(_EntryPoint("thermal", _registers("thermal.scan")))
    retained = registry.discover_plugins(force=True)
    assert sorted(retained) == ["thermal"]

    # thermal is uninstalled and vision appears — the widest change a refresh
    # can make to the plugin set.
    installed(_EntryPoint("vision", _registers("vision.observe")))
    registry.refresh()

    assert sorted(retained) == ["thermal"], (
        "A mapping a caller was handed earlier was rewritten by a later refresh."
    )
    assert sorted(registry.get_plugins()) == ["vision"]


# -- a plugin's size is the modules it owns --------------------------------


def test_module_count_is_the_modules_the_plugin_owns(registry, installed):
    installed(
        _EntryPoint("thermal", _registers("thermal.scan", "thermal.probe")),
        _EntryPoint("vision", _registers("vision.observe")),
    )
    registry.discover_plugins(force=True)

    plugins = registry.get_plugins()
    assert plugins["thermal"].module_count == 2
    assert plugins["vision"].module_count == 1


def test_a_second_pass_does_not_report_an_installed_plugin_as_empty(
    registry, installed
):
    """The regression this counts against: measuring a plugin by how much the
    registry grew while it loaded reads 0 on the second pass, because a cached
    import re-registers the same ids instead of adding new ones."""
    installed(
        _EntryPoint("thermal", _registers("thermal.scan", "thermal.probe")),
        _EntryPoint("vision", _registers("vision.observe")),
    )
    registry.discover_plugins(force=True)
    registry.discover_plugins(force=True)

    plugins = registry.get_plugins()
    assert plugins["thermal"].module_count == 2
    assert plugins["vision"].module_count == 1


# -- clear/discover is exact, not lossy ------------------------------------


def test_a_clear_and_rediscover_reproduces_the_same_registry(registry, installed):
    """``register_all`` is a cached no-op the second time, so without the record
    of what each entry point contributed the cycle returns a smaller registry
    than the one it replaced."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", _registers("thermal.scan", "thermal.probe")))
    registry.discover_plugins(force=True)
    before = dict(registry.list_all())

    registry.clear()
    registry.discover_plugins(force=True)

    assert dict(registry.list_all()) == before
    assert registry.get_plugins()["thermal"].module_count == 2
    # flyto-core's own module comes back too: no entry point can re-register it.
    assert registry.get_metadata("http.get")["plugin"] == ""


# -- force is the plugin's whole answer ------------------------------------


def test_force_removes_a_module_the_plugin_stopped_providing(registry, installed):
    """A plugin that re-registers and does not mention a module it used to
    provide has withdrawn it. Leaving the row standing keeps a module nothing
    installed still vouches for, and counts it against the plugin."""
    installed(
        _EntryPoint("thermal", _registers("thermal.scan", "thermal.probe", once=False))
    )
    registry.discover_plugins(force=True)
    assert registry.get_plugins()["thermal"].module_count == 2

    installed(_EntryPoint("thermal", _registers("thermal.scan", once=False)))
    registry.discover_plugins(force=True)

    assert "thermal.probe" not in registry.list_all()
    assert "thermal.scan" in registry.list_all()
    assert registry.get_plugins()["thermal"].module_count == 1


def test_a_withdrawn_module_stays_withdrawn_across_a_clear(registry, installed):
    """The withdrawal has to reach the contribution record too, or the next
    clear/discover cycle replays the module the plugin just retired."""
    installed(
        _EntryPoint("thermal", _registers("thermal.scan", "thermal.probe", once=False))
    )
    registry.discover_plugins(force=True)
    installed(_EntryPoint("thermal", _registers("thermal.scan")))
    registry.discover_plugins(force=True)

    registry.clear()
    registry.discover_plugins(force=True)

    assert "thermal.probe" not in registry.list_all()


def test_a_plugin_that_provides_nothing_is_not_handed_an_earlier_pass(
    registry, installed
):
    """A no-op ``register_all`` on a live registry says nothing. Replaying the
    record there resurrects modules that are deliberately gone; the record
    exists to rebuild a *cleared* registry, not to override the current one."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", _registers("thermal.scan")))
    registry.discover_plugins(force=True)

    registry.unregister("thermal.scan")
    registry.discover_plugins(force=True)

    assert "thermal.scan" not in registry.list_all()
    assert registry.get_plugins()["thermal"].module_count == 0


def test_a_plugin_that_never_provided_anything_stays_empty(registry, installed):
    installed(_EntryPoint("empty", _registers()))
    registry.discover_plugins(force=True)

    assert registry.get_plugins()["empty"].module_count == 0
    assert registry.list_all() == {}


# -- an uninstalled plugin takes its modules with it -----------------------


def test_an_uninstalled_plugin_and_its_modules_are_forgotten(registry, installed):
    installed(
        _EntryPoint("thermal", _registers("thermal.scan")),
        _EntryPoint("vision", _registers("vision.observe")),
    )
    registry.discover_plugins(force=True)

    installed(_EntryPoint("vision", _registers("vision.observe")))
    registry.discover_plugins(force=True)

    assert "thermal.scan" not in registry.list_all()
    assert "thermal" not in registry.get_plugins()
    assert "vision.observe" in registry.list_all()


def test_an_uninstalled_plugin_is_not_replayed_after_a_clear(registry, installed):
    """Forgetting has to reach the contribution record, or the next
    clear/discover cycle reinstalls a plugin that is gone."""
    installed(_EntryPoint("thermal", _registers("thermal.scan")))
    registry.discover_plugins(force=True)
    installed()
    registry.discover_plugins(force=True)

    registry.clear()
    registry.discover_plugins(force=True)

    assert "thermal.scan" not in registry.list_all()
    assert "thermal" not in registry.get_plugins()


def test_a_module_owned_by_a_plugin_discovery_never_saw_is_not_a_leftover(
    registry, installed
):
    """Somebody registered it deliberately. Treating an unrecognised owner as a
    leftover makes an unrelated caller's registry shrink the first time
    anything reads the catalog."""
    registry._loading_plugin = "handmade"
    try:
        registry.register("handmade.thing", _Original, {"version": "1.0.0"})
    finally:
        registry._loading_plugin = ""

    installed()
    registry.discover_plugins(force=True)

    assert "handmade.thing" in registry.list_all()


# -- a failed load is rolled back whole ------------------------------------


def _explodes_after(*module_ids, module_class=_Replacement):
    def register_all():
        for module_id in module_ids:
            ModuleRegistry.register(module_id, module_class, {"version": "9.9.9"})
        raise RuntimeError("plugin exploded mid-registration")

    return register_all


def test_a_failed_load_restores_the_plugins_own_rows(registry, installed):
    installed(
        _EntryPoint("thermal", _registers("thermal.scan", "thermal.probe", once=False))
    )
    registry.discover_plugins(force=True)

    installed(_EntryPoint("thermal", _explodes_after("thermal.scan", "thermal.new")))
    registry.discover_plugins(force=True)

    # The half it managed is not a smaller plugin — it is a plugin nobody has
    # vouched for, so the pass leaves no trace at all.
    assert "thermal.new" not in registry.list_all()
    assert registry.list_all()["thermal.scan"] is _Original
    assert registry.get_metadata("thermal.scan")["version"] == "1.0.0"
    assert "thermal.probe" in registry.list_all()
    assert registry.get_plugins()["thermal"].module_count == 2


def test_a_failed_load_gives_back_a_first_party_row_it_overwrote(registry, installed):
    """The row was flyto-core's. The failing registration stamped it with the
    plugin's name on the way past, so dropping everything the plugin appears to
    own deletes flyto-core's module instead of returning it."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", _explodes_after("http.get")))

    registry.discover_plugins(force=True)

    assert registry.list_all()["http.get"] is _Original
    assert registry.get_metadata("http.get")["plugin"] == ""
    assert registry.get_metadata("http.get")["version"] == "1.0.0"


def test_a_failed_load_gives_back_another_plugins_row_it_overwrote(registry, installed):
    installed(
        _EntryPoint("vision", _registers("vision.observe")),
        _EntryPoint("thermal", _explodes_after("vision.observe")),
    )
    registry.discover_plugins(force=True)

    assert registry.list_all()["vision.observe"] is _Original
    assert registry.get_metadata("vision.observe")["plugin"] == "vision"
    assert registry.get_plugins()["vision"].module_count == 1
    assert "thermal" not in registry.get_plugins()


# A failed pass can also have reached the registry by *deleting* from it.
# ``register_all`` is arbitrary code with the whole registry in reach, so
# removing a row is as available to it as overwriting one — and a removal leaves
# no trace in what the plugin owns, what it registered, or what its writes
# displaced. A rollback that only replays the writes therefore honours the
# deletions of a pass nobody has vouched for.


def _unregisters_then_explodes(*module_ids, registering=()):
    def register_all():
        for module_id in registering:
            ModuleRegistry.register(module_id, _Replacement, {"version": "9.9.9"})
        for module_id in module_ids:
            ModuleRegistry.unregister(module_id)
        raise RuntimeError("plugin exploded mid-registration")

    return register_all


def test_a_failed_load_gives_back_a_first_party_row_it_unregistered(
    registry, installed
):
    """flyto-core's own module, uninstalled on behalf of a plugin that crashed.
    Nothing else in the process re-registers it, so without rollback it is gone
    for the life of the process."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", _unregisters_then_explodes("http.get")))

    registry.discover_plugins(force=True)

    assert registry.list_all()["http.get"] is _Original
    assert registry.get_metadata("http.get")["plugin"] == ""
    assert registry.get_metadata("http.get")["version"] == "1.0.0"


def test_a_failed_load_gives_back_another_plugins_row_it_unregistered(
    registry, installed
):
    """One plugin must not be able to uninstall another's modules by failing."""
    installed(
        _EntryPoint("vision", _registers("vision.observe")),
        _EntryPoint("thermal", _unregisters_then_explodes("vision.observe")),
    )
    registry.discover_plugins(force=True)

    assert registry.list_all()["vision.observe"] is _Original
    assert registry.get_metadata("vision.observe")["plugin"] == "vision"
    assert registry.get_plugins()["vision"].module_count == 1
    assert "thermal" not in registry.get_plugins()


def test_a_failed_load_that_deletes_and_writes_restores_the_whole_registry(
    registry, installed
):
    """The contract, stated whole: whatever a failed pass did — overwrote a row,
    deleted one, added one, or deleted one it had just added — the registry it
    leaves behind is the one it started from, module classes and metadata
    alike."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry.register("http.post", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("vision", _registers("vision.observe", "vision.track")))
    registry.discover_plugins(force=True)

    before_modules = dict(registry.list_all())
    before_metadata = {
        module_id: registry.get_metadata(module_id) for module_id in before_modules
    }
    before_counts = {
        name: info.module_count for name, info in registry.get_plugins().items()
    }

    installed(
        _EntryPoint("vision", _registers("vision.observe", "vision.track")),
        _EntryPoint(
            "thermal",
            _unregisters_then_explodes(
                # another plugin's row, flyto-core's own, and one of its own
                # writes from this same pass
                "vision.observe",
                "http.get",
                "thermal.scratch",
                registering=("thermal.scratch", "vision.track"),
            ),
        ),
    )
    registry.discover_plugins(force=True)

    assert dict(registry.list_all()) == before_modules
    assert {
        module_id: registry.get_metadata(module_id) for module_id in registry.list_all()
    } == before_metadata
    assert {
        name: info.module_count for name, info in registry.get_plugins().items()
    } == before_counts
    # And the pass genuinely had something to lose: the rows it tried to delete
    # are the ones still standing.
    assert "http.get" in before_modules and "vision.observe" in before_modules
    assert "thermal.scratch" not in before_modules


def test_a_failed_load_cannot_edit_the_rows_it_will_be_rolled_back_to(
    registry, installed
):
    """Rollback is only as good as the record it restores from.

    Both copies on that path were one level deep, and together they formed a
    loop. `get_metadata` handed the plugin the live row's own nested objects, so
    editing the list it was given edited what the registry stored; `_capture`
    then banked that row with the same nested objects again, so the record the
    rollback restores from was the poisoned list. The pass "failed", the
    registry was "restored", and `http.get` came out of it declaring a
    permission flyto-core never declared — attributed to flyto-core, which is
    the identity the process-global grant reaches.
    """
    registry.register(
        "http.get",
        _Original,
        {"version": "1.0.0", "required_permissions": ["network.read"]},
    )

    def register_all():
        # Reach the row through the public read first, so the edit lands before
        # the overwrite banks it.
        handed = ModuleRegistry.get_metadata("http.get")
        handed["required_permissions"].append("shell.execute")
        ModuleRegistry.register("http.get", _Replacement, {"version": "9.9.9"})
        raise RuntimeError("plugin exploded after poisoning a row it displaced")

    installed(_EntryPoint("thermal", register_all))
    registry.discover_plugins(force=True)

    restored = registry.get_metadata("http.get")
    assert registry.list_all()["http.get"] is _Original
    assert restored["required_permissions"] == ["network.read"]
    assert restored["version"] == "1.0.0"
    assert restored["plugin"] == ""
    assert "thermal" not in registry.get_plugins()


def test_a_captured_row_is_not_an_alias_of_the_live_one(registry):
    """What `_capture` banks must describe the row as it stood, and keep saying
    so afterwards. A one-level copy shared the nested values with the live row,
    so anything that mutated the row in place also rewrote the record of how it
    used to look."""
    registry.register("http.get", _Original, {"version": "1.0.0", "tags": ["net"]})

    captured = registry._capture(["http.get"])
    registry._metadata["http.get"]["tags"].append("smuggled")

    assert captured["http.get"][1]["tags"] == ["net"]

    # And a row that declines to be copied cannot bank itself. `deepcopy` alone
    # would return the live row, so the "record of how it used to look" and the
    # row it is meant to describe would be one object — a rollback would then
    # restore the registry to whatever the failed pass last wrote.
    hostile = _ALIASING_DICT({"version": "1.0.0", "plugin": "", "tags": ["net"]})
    registry._modules["http.head"] = _Original
    registry._metadata["http.head"] = hostile

    banked = registry._capture(["http.head"])["http.head"][1]
    assert banked is not hostile, "the bank aliased the live row"
    assert type(banked) is dict
    hostile["tags"].append("smuggled")
    assert banked["tags"] == ["net"]


def test_a_restored_row_is_not_an_alias_of_the_record(registry):
    """`_core_baseline` and `_plugin_contributions` are replayed more than once
    in a process, so a restore that hands the registry the recorded objects
    themselves lets the restored row edit the record every later replay reads."""
    rows = {"http.get": (_Original, {"version": "1.0.0", "tags": ["net"]})}

    registry._restore(rows)
    registry._metadata["http.get"]["tags"].append("smuggled")

    assert rows["http.get"][1]["tags"] == ["net"]

    # The second replay still reproduces the row the record describes.
    registry._restore(rows)
    assert registry._metadata["http.get"]["tags"] == ["net"]

    # A recorded row that declines to be copied would be *installed as* the live
    # row, collapsing the record and the registry into one object: the first
    # replay's row and the record every later replay reads would be the same
    # dict, so editing the restored row rewrites the record.
    hostile = _ALIASING_DICT({"version": "1.0.0", "tags": ["net"]})
    hostile_rows = {"http.head": (_Original, hostile)}

    registry._restore(hostile_rows)
    restored = registry._metadata["http.head"]
    assert restored is not hostile, "the restored row aliased the record"
    assert type(restored) is dict
    restored["tags"].append("smuggled")
    assert hostile["tags"] == ["net"]

    registry._restore(hostile_rows)
    assert registry._metadata["http.head"]["tags"] == ["net"]


def test_a_failed_load_restores_the_snapshot_a_resume_is_matched_against(
    registry, installed
):
    """The rollback has to hold at the layer callers actually persist.

    ``get_snapshot()`` is the artifact a checkpoint records and a resumed
    execution is matched against, and it is derived state — ``module_count`` and
    ``modules_hash`` come off ``_modules``, the plugin map off ``_plugins``. A
    failed pass that took a foreign row out with it would leave a registry that
    still looks plausible but hashes differently, so every checkpoint written
    before the failure would stop matching the process that wrote it.

    Row-level assertions elsewhere in this file do not cover this: the hash is
    computed from module *ids*, so it cannot see a class or metadata swap, and
    the row assertions never read the snapshot. Both halves are asserted here —
    the snapshot for the rows the failed pass deleted, and identity for the ones
    it overwrote, which the hash is blind to.
    """
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry.register("http.post", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("vision", _registers("vision.observe", "vision.track")))
    registry.discover_plugins(force=True)

    before = registry.get_snapshot()

    installed(
        _EntryPoint("vision", _registers("vision.observe", "vision.track")),
        _EntryPoint(
            "thermal",
            _unregisters_then_explodes(
                # deletes another plugin's row and flyto-core's own, having
                # first overwritten a second row belonging to that plugin
                "vision.observe",
                "http.get",
                registering=("thermal.scratch", "vision.track"),
            ),
        ),
    )
    registry.discover_plugins(force=True)

    after = registry.get_snapshot()

    # The deletions: both would move the hash and the count if they stood.
    assert after.modules_hash == before.modules_hash
    assert after.module_count == before.module_count
    # The failed plugin never earns a version line, and the one it interfered
    # with keeps the version it was already reporting.
    assert after.plugins == before.plugins
    assert "thermal" not in after.plugins
    assert after.registry_version == before.registry_version

    # The overwrite, which the hash cannot see: the row is the original class,
    # still owned by the plugin that registered it, at its own version.
    assert registry.list_all()["vision.track"] is _Original
    assert registry.get_metadata("vision.track")["plugin"] == "vision"
    assert registry.get_metadata("vision.track")["version"] == "1.0.0"

    # And the pass genuinely had something to lose.
    assert registry.list_all()["vision.observe"] is _Original
    assert registry.list_all()["http.get"] is _Original
    assert registry.get_metadata("http.get")["plugin"] == ""
    assert "thermal.scratch" not in registry.list_all()


# clear() is the third route a register_all has into the registry, alongside
# registering and unregistering. It is the widest of the three — it drops every
# row at once — and it was the only one that also destroyed the record rollback
# is reconstructed from.


def test_a_plugin_cannot_launder_its_modules_by_clearing_the_registry(
    registry, installed
):
    """Ownership has to survive the widest thing a plugin can do to the registry.

    ``clear()`` used to reset the loading owner, so a plugin that called it
    part-way through its own ``register_all`` had everything it registered
    afterwards stamped with no plugin at all. An absent owner reads as
    flyto-core's own, and first-party is precisely the identity the
    process-global permission grant reaches — so the clear was a way to claim
    the one thing ``register()`` assigns rather than accepts.
    """

    def clears_then_registers():
        ModuleRegistry.clear()
        ModuleRegistry.register("thermal.scan", _Original, {"version": "1.0.0"})

    installed(_EntryPoint("thermal", clears_then_registers))
    registry.discover_plugins(force=True)

    assert registry.get_metadata("thermal.scan")["plugin"] == "thermal"
    assert "thermal.scan" not in registry._first_party_ids()
    assert registry.get_plugins()["thermal"].module_count == 1


def test_a_failed_load_that_cleared_the_registry_is_still_rolled_back_whole(
    registry, installed
):
    """A cleared row is neither a write nor an unregister, so nothing else banks
    it. Without clear() feeding the ledger, the rollback ran against an empty
    record at exactly the moment it described the most damage — every other
    plugin's modules and flyto-core's own, gone on behalf of a pass that
    crashed."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("vision", _registers("vision.observe")))
    registry.discover_plugins(force=True)

    before_modules = dict(registry.list_all())
    before_metadata = {
        module_id: registry.get_metadata(module_id) for module_id in before_modules
    }
    before_counts = {
        name: info.module_count for name, info in registry.get_plugins().items()
    }
    before_hash = registry.get_snapshot().modules_hash

    def wipes_then_explodes():
        ModuleRegistry.clear()
        raise RuntimeError("plugin exploded after wiping the registry")

    installed(
        _EntryPoint("vision", _registers("vision.observe")),
        _EntryPoint("thermal", wipes_then_explodes),
    )
    registry.discover_plugins(force=True)

    assert dict(registry.list_all()) == before_modules
    assert {
        module_id: registry.get_metadata(module_id) for module_id in registry.list_all()
    } == before_metadata
    # The reported plugin set is part of "as it found it": the wipe took every
    # entry point's PluginInfo, not just the failing one's.
    assert {
        name: info.module_count for name, info in registry.get_plugins().items()
    } == before_counts
    assert registry.get_snapshot().modules_hash == before_hash
    assert "thermal" not in registry.get_plugins()


def test_the_registry_contract_version_records_the_transaction_semantics(
    registry, installed
):
    """REGISTRY_VERSION rides in every snapshot so a checkpoint taken under one
    set of discovery semantics can be told apart from one taken under another.
    Making rollback total changed what a caller may conclude from a registry
    that survived a failed load, so it had to move.

    Serialising the first discovery moved it again, to 1.2.0: a snapshot taken
    from another thread during discovery used to describe a half-built registry,
    so two snapshots of one install could disagree on module_count and
    modules_hash. A checkpoint carrying 1.1.0 cannot be assumed to have been
    matched against a complete registry; one carrying 1.2.0 can.

    Holding the lock across the whole read moved it again, to 1.3.0. 1.2.0
    serialised the decision to discover but released the lock before the caller
    touched a row, so a read that had already passed the "already initialised"
    fast path copied and iterated the registry with nothing held; a forced pass
    starting in that window tore it. A checkpoint carrying 1.2.0 was matched
    against a registry that was complete when the check ran, which is not the
    same claim as complete when the answer was assembled; one carrying 1.3.0 is
    matched against a registry that stood whole at a single instant.

    Making the row boundaries deep moved it again, to 1.4.0. Through 1.3.0 every
    copy — registration, capture, restore, and the localised read — was one
    level deep, so a caller on either side of the boundary kept live handles on
    the nested values: the stored `required_permissions` list, the stored
    `params_schema`. A checkpoint carrying 1.3.0 was matched against a registry
    whose *shape* stood whole at one instant but whose rows could have been
    edited afterwards by anyone who had ever handed one in or been handed one
    back, without the lock and without passing through `register`. One carrying
    1.4.0 was matched against rows the registry holds alone.

    Pinned deliberately: the guard is here to make the next semantic change bump
    it on purpose rather than inherit a version that no longer describes the
    behaviour. Bump both together — never edit this to match the source."""
    assert registry_core.REGISTRY_VERSION == "1.4.0"

    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", _unregisters_then_explodes("http.get")))
    registry.discover_plugins(force=True)

    # The snapshot a resumed execution is matched against carries it.
    assert registry.get_snapshot().registry_version == "1.4.0"
    assert registry.get_snapshot().to_dict()["registry_version"] == "1.4.0"


def test_a_failed_load_leaves_no_deletion_record_behind(registry, installed):
    """The per-pass touch record spans exactly one register_all, like the
    registration record beside it; a leaked one would have the next plugin's
    deletions judged against the wrong baseline."""
    registry.register("http.get", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", _unregisters_then_explodes("http.get")))
    registry.discover_plugins(force=True)

    assert registry._pass_touched is None
    assert registry._pass_registered is None
    assert registry._pass_displaced == {}


def test_a_successful_load_may_still_unregister(registry, installed):
    """Rollback is for failure only. A pass that finishes has been vouched for,
    so a module it deliberately retired stays retired."""

    def register_all():
        registry.register("thermal.scan", _Original, {"version": "1.0.0"})
        registry.unregister("http.legacy")

    # http.get keeps flyto-core represented after the retirement, so the
    # assertion below is about rollback and not about the separate replay that
    # rebuilds a first-party set the pass emptied entirely.
    registry.register("http.get", _Original, {"version": "1.0.0"})
    registry.register("http.legacy", _Original, {"version": "1.0.0"})
    installed(_EntryPoint("thermal", register_all))

    registry.discover_plugins(force=True)

    assert "http.legacy" not in registry.list_all()
    assert "http.get" in registry.list_all()
    assert "thermal.scan" in registry.list_all()


def test_a_failed_first_load_leaves_no_plugin_behind(registry, installed):
    installed(_EntryPoint("thermal", _explodes_after("thermal.scan")))
    registry.discover_plugins(force=True)

    assert "thermal" not in registry.get_plugins()
    assert registry.list_all() == {}


def test_a_failed_load_does_not_stop_the_pass(registry, installed):
    installed(
        _EntryPoint("thermal", _explodes_after("thermal.scan")),
        _EntryPoint("vision", _registers("vision.observe")),
    )
    registry.discover_plugins(force=True)

    assert "vision.observe" in registry.list_all()
    assert registry.get_plugins()["vision"].module_count == 1


def test_a_failed_load_leaves_no_registration_record_behind(registry, installed):
    """The per-pass record is what makes rollback exact; if it survived the
    failure, the next plugin's registrations would be judged against it."""
    installed(_EntryPoint("thermal", _explodes_after("thermal.scan")))
    registry.discover_plugins(force=True)

    assert registry._pass_registered is None
    assert registry._pass_displaced == {}
    assert registry._loading_plugin == ""
