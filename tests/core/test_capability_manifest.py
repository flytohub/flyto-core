# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Tests for the ``flyto.core.capability-manifest.v1`` document.

The manifest's whole value is that it is reproducible: two hosts with the same
installed distributions must produce the same bytes, so the hash can be
compared to decide whether two workers expose the same capability surface.
These tests pin that contract, and they pin it against a registry whose
contents the test controls — plugins are described as entry points rather than
built and installed, using the seam `_iter_entry_points` reads through.
"""

import json

import pytest

from core import capability_manifest
from core.capability_manifest import (
    MANIFEST_SCHEMA,
    build_capability_manifest,
    compute_manifest_hash,
    get_capability_manifest,
    refresh_capability_manifest,
)
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry
from core.modules.registry import core as registry_core

# ---------------------------------------------------------------------------
# Fakes — a plugin is *described*, not built and installed.
# ---------------------------------------------------------------------------


class _Module(BaseModule):
    """Minimal registrable module; the manifest never executes anything."""

    async def run(self):  # pragma: no cover - never invoked by these tests
        return {}


class _Groups(list):
    """Entry point group container covering both importlib.metadata shapes.

    `_iter_entry_points` calls `entry_points(group=...)` on 3.10+ and
    `entry_points().get(group, [])` below that. Answering to both keeps these
    tests honest on every interpreter the package supports.
    """

    def get(self, group, default=None):
        return list(self)


class _EntryPoint:
    """A described entry point: discovery only asks for name/value/load()."""

    def __init__(self, name, register=None, value="fake_pkg:register_all"):
        self.name = name
        self.value = value
        self._register = register

    def load(self):
        return self._register if self._register is not None else (lambda: None)


def _registers(*specs):
    """Build a `register_all` that registers (module_id, capability) pairs."""

    def register_all():
        for module_id, capability in specs:
            ModuleRegistry.register(
                module_id,
                _Module,
                {
                    "module_id": module_id,
                    "category": module_id.split(".")[0],
                    "provides_capability": capability,
                    # `stability` and the ui_* pair are normally supplied by
                    # build_module_metadata. Registering raw metadata skips
                    # that, so set them here: without `stability` the
                    # stability filter that catalog reads apply by default
                    # would decide these modules' visibility by accident, and
                    # without `ui_label` catalog search has nothing to score.
                    "stability": "stable",
                    "ui_label": module_id,
                    "ui_description": f"described module {module_id}",
                },
            )

    return register_all


# Every class-level attribute discovery touches, so one test cannot leak a
# registry state into the next.
_REGISTRY_STATE = (
    "_modules",
    "_metadata",
    "_plugins",
    "_initialized",
    "_loading_plugin",
    "_discovering",
    "_discovery_thread",
    "_plugin_contributions",
    "_core_baseline",
    "_pass_registered",
    "_pass_displaced",
    "_pass_touched",
    "_cleared",
    "_started_empty",
)


def _invalidate_manifest_cache():
    """Empty the manifest cache slot, generation bookkeeping included.

    The generation is reset to the sentinel rather than to zero: registry
    generations are monotonic for the life of the process and are never
    rewound, so any value a later build reports must compare as newer than an
    empty slot. Leaving a stale generation beside a cleared document would have
    the first build after a reset judged against a state it did not come from.
    """
    capability_manifest._cached = None
    capability_manifest._cached_generation = -1


def _reset_registry():
    """Return the registry to a virgin, nothing-installed state.

    Deliberately not `clear()`. `clear()` sets `_cleared`, which licenses the
    next discovery pass to replay `_plugin_contributions` — the mechanism that
    lets a plugin whose `register_all` is a cached import no-op survive a
    clear/discover cycle. Correct in production, fatal to a test that needs
    "this plugin is no longer installed" to actually mean that: the removed
    plugin's modules would be replayed straight back in.

    `_pass_registered` and `_pass_touched` are reset to `None`, not to empty
    containers. `clear()` decides whether it is running inside a discovery
    pass with `cls._pass_touched is not None`, so an empty set here would make
    every later `clear()` believe it was mid-pass and keep the loading owner
    and pass ledger alive.

    `_generation` is *not* reset, and is absent from `_REGISTRY_STATE` for the
    same reason. It is an ordering key, not content: rewinding it would let a
    snapshot taken before a reset compare as newer than one taken after, which
    is the precise failure the counter exists to rule out.
    """
    ModuleRegistry._modules = {}
    ModuleRegistry._metadata = {}
    ModuleRegistry._plugins = {}
    ModuleRegistry._plugin_contributions = {}
    ModuleRegistry._core_baseline = {}
    ModuleRegistry._pass_registered = None
    ModuleRegistry._pass_touched = None
    ModuleRegistry._pass_displaced = {}
    ModuleRegistry._loading_plugin = ""
    ModuleRegistry._cleared = False
    ModuleRegistry._started_empty = True
    ModuleRegistry._initialized = False


@pytest.fixture
def registry():
    """Save and restore registry class state around a test."""
    saved = {}
    for name in _REGISTRY_STATE:
        value = getattr(ModuleRegistry, name)
        saved[name] = value.copy() if hasattr(value, "copy") else value
    try:
        yield ModuleRegistry
    finally:
        for name, value in saved.items():
            setattr(ModuleRegistry, name, value)
        _invalidate_manifest_cache()


@pytest.fixture
def installed(monkeypatch):
    """Replace the installed entry points with the ones a test describes."""

    def _install(*eps):
        monkeypatch.setattr(
            registry_core, "entry_points", lambda **kw: _Groups(eps), raising=False
        )
        _reset_registry()
        ModuleRegistry.discover_plugins(force=True)
        _invalidate_manifest_cache()
        return eps

    return _install


# ---------------------------------------------------------------------------
# Entry points appearing and disappearing
# ---------------------------------------------------------------------------


def test_added_plugin_appears_in_manifest(registry, installed):
    """Installing a plugin adds its modules, capability, and plugin entry."""
    installed(
        _EntryPoint("alpha", _registers(("alpha.scan", "barcode.read"))),
    )
    manifest = build_capability_manifest()

    assert "alpha.scan" in manifest["modules"]
    assert {"capability": "barcode.read", "providers": ["alpha.scan"]} in manifest[
        "capabilities"
    ]
    assert [p["id"] for p in manifest["plugins"]] == ["alpha"]
    assert manifest["plugin_count"] == 1


def test_removed_plugin_disappears_after_refresh(registry, installed):
    """Uninstalling a plugin drops its modules and changes the hash."""
    installed(_EntryPoint("alpha", _registers(("alpha.scan", "barcode.read"))))
    before = build_capability_manifest()

    installed()  # nothing installed any more
    after = build_capability_manifest()

    assert "alpha.scan" not in after["modules"]
    assert after["plugins"] == []
    assert "barcode.read" not in [c["capability"] for c in after["capabilities"]]
    assert after["hash"] != before["hash"]


def test_two_plugins_can_provide_one_capability(registry, installed):
    """Several providers for a capability is normal, and both are listed."""
    installed(
        _EntryPoint("alpha", _registers(("alpha.scan", "barcode.read"))),
        _EntryPoint("beta", _registers(("beta.scan", "barcode.read"))),
    )
    manifest = build_capability_manifest()

    providers = {
        c["capability"]: c["providers"] for c in manifest["capabilities"]
    }
    assert providers["barcode.read"] == ["alpha.scan", "beta.scan"]


# ---------------------------------------------------------------------------
# Determinism: ordering and hash
# ---------------------------------------------------------------------------


def test_ordering_is_sorted_everywhere(registry, installed):
    """Every list in the document is sorted, regardless of registration order."""
    installed(
        _EntryPoint("zeta", _registers(("zeta.b", "z.cap"), ("zeta.a", "a.cap"))),
        _EntryPoint("alpha", _registers(("alpha.m", "m.cap"))),
    )
    manifest = build_capability_manifest()

    assert manifest["modules"] == sorted(manifest["modules"])
    assert [c["capability"] for c in manifest["capabilities"]] == sorted(
        c["capability"] for c in manifest["capabilities"]
    )
    assert [c["category"] for c in manifest["categories"]] == sorted(
        c["category"] for c in manifest["categories"]
    )
    assert [p["id"] for p in manifest["plugins"]] == sorted(
        p["id"] for p in manifest["plugins"]
    )
    for capability in manifest["capabilities"]:
        assert capability["providers"] == sorted(capability["providers"])


def test_registration_order_does_not_change_the_hash(registry, installed):
    """The same modules registered in a different order hash identically."""
    installed(_EntryPoint("p", _registers(("p.a", "one"), ("p.b", "two"))))
    first = build_capability_manifest()

    installed(_EntryPoint("p", _registers(("p.b", "two"), ("p.a", "one"))))
    second = build_capability_manifest()

    assert first["hash"] == second["hash"]
    assert first == second


def test_rebuilding_is_byte_identical(registry, installed):
    """Building twice with no change in between produces the same document."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    first = json.dumps(build_capability_manifest(), sort_keys=True)
    second = json.dumps(build_capability_manifest(), sort_keys=True)

    assert first == second


def test_hash_is_sha256_of_the_body(registry, installed):
    """`hash` is a SHA-256 over the document with `hash` itself excluded."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    manifest = build_capability_manifest()

    assert len(manifest["hash"]) == 64
    assert int(manifest["hash"], 16) >= 0  # hex
    assert compute_manifest_hash(manifest) == manifest["hash"]


def test_hash_changes_when_a_capability_changes(registry, installed):
    """A different capability surface must not collide with the old hash."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    before = build_capability_manifest()["hash"]

    installed(_EntryPoint("p", _registers(("p.a", "two"))))
    after = build_capability_manifest()["hash"]

    assert before != after


def test_manifest_carries_no_volatile_or_host_detail(registry, installed):
    """No timestamps, paths, secrets, or device identity anywhere in the doc."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    blob = json.dumps(build_capability_manifest())

    for forbidden in (
        "loaded_at",
        "created_at",
        "timestamp",
        "entry_point",
        "/Users/",
        "/home/",
        "C:\\",
        "token",
        "secret",
        "password",
        "hostname",
        "device",
    ):
        assert forbidden not in blob, f"manifest leaked {forbidden!r}"


def test_counts_agree_with_their_lists(registry, installed):
    """The `*_count` fields are derived, not independently maintained."""
    installed(
        _EntryPoint("p", _registers(("p.a", "one"), ("p.b", "two"))),
        _EntryPoint("q", _registers(("q.a", "three"))),
    )
    manifest = build_capability_manifest()

    assert manifest["module_count"] == len(manifest["modules"])
    assert manifest["capability_count"] == len(manifest["capabilities"])
    assert manifest["category_count"] == len(manifest["categories"])
    assert manifest["plugin_count"] == len(manifest["plugins"])
    # Category counts partition the module set exactly.
    assert sum(c["module_count"] for c in manifest["categories"]) == manifest[
        "module_count"
    ]


def test_schema_and_versions_are_present(registry, installed):
    """Identity fields a consumer needs to interpret the document."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    manifest = build_capability_manifest()

    assert manifest["schema"] == MANIFEST_SCHEMA == "flyto.core.capability-manifest.v1"
    assert isinstance(manifest["registry_version"], str)
    assert manifest["registry_version"]
    assert isinstance(manifest["core_version"], str)
    assert manifest["core_version"]


# ---------------------------------------------------------------------------
# Copy isolation
# ---------------------------------------------------------------------------


def test_caller_mutation_cannot_corrupt_the_cache(registry, installed):
    """A caller that mutates its copy does not affect the next caller."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    first = get_capability_manifest()
    first["modules"].append("injected.module")
    first["capabilities"][0]["providers"].append("injected.module")
    first["hash"] = "tampered"
    first["schema"] = "tampered"

    second = get_capability_manifest()
    assert "injected.module" not in second["modules"]
    assert "injected.module" not in second["capabilities"][0]["providers"]
    assert second["hash"] != "tampered"
    assert second["schema"] == MANIFEST_SCHEMA


def test_each_call_returns_a_distinct_object(registry, installed):
    """Nested containers are copied too, not shared by reference."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    first = get_capability_manifest()
    second = get_capability_manifest()

    assert first == second
    assert first is not second
    assert first["modules"] is not second["modules"]
    assert first["capabilities"][0] is not second["capabilities"][0]


def test_refresh_rediscovers_installed_plugins(registry, monkeypatch):
    """`refresh_capability_manifest` picks up a newly installed distribution."""
    monkeypatch.setattr(
        registry_core, "entry_points", lambda **kw: _Groups(()), raising=False
    )
    # `_reset_registry`, not `clear()` — see its docstring: `clear()` licenses
    # a contribution replay that would put the "uninstalled" plugin straight
    # back and make this test assert nothing.
    _reset_registry()
    ModuleRegistry.discover_plugins(force=True)
    _invalidate_manifest_cache()
    before = get_capability_manifest()
    assert before["plugins"] == []

    # A distribution appears after startup.
    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups((_EntryPoint("late", _registers(("late.a", "late.cap"))),)),
        raising=False,
    )
    after = refresh_capability_manifest()

    assert [p["id"] for p in after["plugins"]] == ["late"]
    assert "late.a" in after["modules"]
    assert after["hash"] != before["hash"]


# ---------------------------------------------------------------------------
# Catalog surfaces stay compatible with plugin-contributed modules
# ---------------------------------------------------------------------------


def test_outline_and_categories_include_plugin_categories(registry, installed):
    """A plugin's new category shows up in the outline, not just the manifest."""
    from core.catalog import get_categories, get_outline

    installed(_EntryPoint("p", _registers(("brandnew.thing", "some.cap"))))

    assert "brandnew" in get_categories()
    outline = get_outline()
    assert "brandnew" in outline
    # An unknown category still gets usable presentation defaults.
    assert outline["brandnew"]["label"]
    assert outline["brandnew"]["count"] == 1


def test_detail_and_search_expose_plugin_modules(registry, installed):
    """Module detail and search see plugin modules with their identity fields."""
    from core.catalog.module import get_module_detail, search_modules

    installed(_EntryPoint("p", _registers(("brandnew.thing", "some.cap"))))

    detail = get_module_detail("brandnew.thing")
    assert detail is not None
    assert detail.get("provides_capability") == "some.cap"
    assert detail.get("plugin") == "p"

    hits = search_modules("brandnew", limit=20)
    assert any(h["module_id"] == "brandnew.thing" for h in hits)


# ---------------------------------------------------------------------------
# Atomicity — a concurrent refresh must not tear the document
# ---------------------------------------------------------------------------


def test_snapshot_is_internally_consistent(registry, installed):
    """Plugin module counts agree with the module list in the same document.

    The cheapest observable signature of a torn read: `plugins[].module_count`
    is recorded by discovery, while `modules` is derived from metadata. If the
    two halves came from different registry states they disagree.
    """
    installed(
        _EntryPoint("p", _registers(("p.a", "one"), ("p.b", "two"))),
        _EntryPoint("q", _registers(("q.a", "three"))),
    )
    manifest = build_capability_manifest()

    by_prefix = {}
    for module_id in manifest["modules"]:
        by_prefix[module_id.split(".")[0]] = by_prefix.get(
            module_id.split(".")[0], 0
        ) + 1
    for plugin in manifest["plugins"]:
        assert plugin["module_count"] == by_prefix.get(plugin["id"], 0)

    # Providers must all be modules that exist in the same document.
    known = set(manifest["modules"])
    for capability in manifest["capabilities"]:
        assert set(capability["providers"]) <= known


def test_cache_lock_is_never_held_while_reading_the_registry(
    registry, installed, monkeypatch
):
    """The lock-ordering invariant, pinned without needing a race to expose it.

    Holding the cache lock across a registry read is what deadlocks against a
    plugin calling back in during discovery. Rather than hope a scheduler
    reproduces that, this observes the invariant directly: every entry into
    `capability_snapshot` asserts the cache lock is currently unheld.

    "Unheld" is probed from another thread, because `RLock` is reentrant and
    would happily re-acquire on the thread that already owns it.
    """
    import threading

    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    violations = []
    real_snapshot = ModuleRegistry.capability_snapshot

    def _cache_lock_is_held():
        held = {"value": True}

        def probe():
            if capability_manifest._cache_lock.acquire(blocking=False):
                capability_manifest._cache_lock.release()
                held["value"] = False

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join(timeout=5)
        return held["value"]

    def watched_snapshot():
        if _cache_lock_is_held():
            violations.append("cache lock held while entering capability_snapshot")
        return real_snapshot()

    # monkeypatch, not manual assignment: the `registry` fixture does not save
    # `capability_snapshot`, so a hand-rolled restore would leak a bound method
    # into the class dict for every later test in the session.
    monkeypatch.setattr(
        ModuleRegistry, "capability_snapshot", staticmethod(watched_snapshot)
    )

    get_capability_manifest(refresh=True)
    build_capability_manifest()
    refresh_capability_manifest()

    assert not violations, violations


def test_plugin_reentrant_manifest_call_does_not_deadlock(registry, monkeypatch):
    """A plugin reading the manifest during its own discovery must not hang.

    This is the inversion in full. Thread B asks for a manifest, which needs
    the registry lock that thread A's discovery is holding. Thread A, inside
    that lock, runs plugin code that asks for a manifest too. If a build ever
    holds the cache lock while waiting on the registry lock, B parks on the
    registry while holding the cache, A parks on the cache while holding the
    registry, and neither moves again.

    Deterministic in the direction that matters: correct code always finishes,
    and the ordering below drives B into its build before A's plugin calls in,
    so broken code hangs and the join times out rather than passing by luck.
    """
    import threading

    b_started = threading.Event()
    plugin_entered = threading.Event()
    plugin_result = {}

    def register_all():
        ModuleRegistry.register(
            "deep.a",
            _Module,
            {
                "module_id": "deep.a",
                "category": "deep",
                "provides_capability": "deep.cap",
                "stability": "stable",
            },
        )
        plugin_entered.set()
        # Let B get as far as it can before re-entering from inside the
        # registry lock. Broken code has B holding the cache lock by now.
        b_started.wait(timeout=5)
        plugin_result["manifest"] = get_capability_manifest(refresh=True)

    _reset_registry()
    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups((_EntryPoint("deep", register_all),)),
        raising=False,
    )
    _invalidate_manifest_cache()

    errors = []

    def thread_a():
        try:
            ModuleRegistry.discover_plugins(force=True)
        except Exception as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    def thread_b():
        try:
            plugin_entered.wait(timeout=5)
            b_started.set()
            get_capability_manifest(refresh=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    a = threading.Thread(target=thread_a, daemon=True)
    b = threading.Thread(target=thread_b, daemon=True)
    a.start()
    b.start()
    a.join(timeout=15)
    b.join(timeout=15)

    assert not a.is_alive(), "discovery thread hung — lock inversion regressed"
    assert not b.is_alive(), "reader thread hung — lock inversion regressed"
    assert not errors, errors
    # The plugin's own read saw the module it had just registered.
    assert "deep.a" in plugin_result["manifest"]["modules"]


def test_concurrent_get_and_refresh_never_tears(registry, monkeypatch):
    """Readers racing refreshers only ever see whole, self-consistent documents.

    The two installs are mutually exclusive, so a blend of both is detectable.
    Assertions are framed as "left implies no right, and vice versa" rather
    than as exact module sets: `refresh()` replays recorded contributions, so
    the registry legitimately carries rows beyond the current entry points, and
    demanding an exact set tested the replay machinery instead of atomicity.
    """
    import threading

    left = _Groups((_EntryPoint("left", _registers(("left.a", "cap.left"))),))
    right = _Groups(
        (
            _EntryPoint(
                "right", _registers(("right.a", "cap.right"), ("right.b", "cap.right"))
            ),
        )
    )
    installs = [left, right]
    picker = {"i": 0}

    def _entry_points(**_kw):
        return installs[picker["i"] % 2]

    _reset_registry()
    monkeypatch.setattr(registry_core, "entry_points", _entry_points, raising=False)
    ModuleRegistry.discover_plugins(force=True)
    _invalidate_manifest_cache()

    errors = []
    stop = threading.Event()

    def check(manifest):
        modules = set(manifest["modules"])
        caps = {c["capability"]: set(c["providers"]) for c in manifest["capabilities"]}

        # Self-consistency, true of any whole snapshot.
        assert manifest["module_count"] == len(modules)
        assert compute_manifest_hash(manifest) == manifest["hash"]
        for providers in caps.values():
            assert providers <= modules

        # A capability is present exactly when its provider is. A tear splits
        # these two halves, which come from different registry reads.
        if "cap.left" in caps:
            assert "left.a" in modules
            assert caps["cap.left"] == {"left.a"}
        if "cap.right" in caps:
            assert "right.a" in modules and "right.b" in modules
            assert caps["cap.right"] == {"right.a", "right.b"}

        # Every declared plugin's module count matches the modules it owns in
        # this same document.
        for plugin in manifest["plugins"]:
            owned = {m for m in modules if m.split(".")[0] == plugin["id"]}
            if owned:
                assert plugin["module_count"] == len(owned), (
                    plugin,
                    sorted(owned),
                )

    def reader():
        try:
            while not stop.is_set():
                check(get_capability_manifest(refresh=True))
        except Exception as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    def refresher():
        try:
            while not stop.is_set():
                picker["i"] += 1
                check(refresh_capability_manifest())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    threads.append(threading.Thread(target=refresher))
    threads.append(threading.Thread(target=refresher))
    for thread in threads:
        thread.daemon = True
        thread.start()
    stop.wait(2.0)
    stop.set()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "thread hung — suspect lock ordering"

    assert not errors, errors


# ---------------------------------------------------------------------------
# Staleness — a slow build must not publish over a newer document
# ---------------------------------------------------------------------------


def test_generation_advances_with_every_registry_change(registry, installed):
    """The snapshot carries a mutation counter that only ever moves forward.

    This is the ordering key the cache uses to reject a stale store, so it has
    to be monotonic and it has to actually move when content changes. A counter
    that stood still across a refresh would let two different registry states
    compare as equally new, which is exactly the tie the cache cannot break.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    first = ModuleRegistry.capability_snapshot()["generation"]

    # A pure read changes nothing and must not advance the counter, or every
    # reader would invalidate every other reader's store for no reason.
    assert ModuleRegistry.capability_snapshot()["generation"] == first

    ModuleRegistry.register(
        "p.b",
        _Module,
        {"module_id": "p.b", "category": "p", "stability": "stable"},
    )
    after_register = ModuleRegistry.capability_snapshot()["generation"]
    assert after_register > first

    ModuleRegistry.unregister("p.b")
    after_unregister = ModuleRegistry.capability_snapshot()["generation"]
    assert after_unregister > after_register

    installed(_EntryPoint("q", _registers(("q.a", "two"))))
    assert ModuleRegistry.capability_snapshot()["generation"] > after_unregister


def test_a_stale_build_cannot_overwrite_a_newer_cached_manifest(
    registry, installed, monkeypatch
):
    """The stale-refresh race, reproduced deterministically rather than raced.

    Two builds run concurrently and nothing orders their *stores*. A build that
    reads the registry, loses the CPU, and finishes after a refresh has already
    published the post-refresh document would — with an unconditional store —
    put the pre-refresh state back. Every later cache hit is then served an
    installation that no longer exists, and nothing corrects it: the refresh
    looks like it succeeded and silently did nothing.

    The interleave is forced with events, not with sleeps or a timing window,
    so this test is deterministic in both directions. Correct code always
    passes; code that stores unconditionally always fails, because the slow
    build's store is guaranteed to land after the refresh's.
    """
    import threading

    installed(_EntryPoint("old", _registers(("old.a", "cap.old"))))

    snapshot_taken = threading.Event()
    newer_published = threading.Event()
    slow_thread = {}

    real_snapshot = ModuleRegistry.capability_snapshot

    def staged_snapshot():
        # `real_snapshot` takes *and releases* the registry lock before it
        # returns, so the wait below parks holding nothing. Pausing inside the
        # registry lock instead would block the refresh this test needs to
        # overtake it, and the test would deadlock rather than assert.
        snapshot = real_snapshot()
        if threading.get_ident() == slow_thread.get("id"):
            snapshot_taken.set()
            newer_published.wait(timeout=10)
        return snapshot

    # staticmethod, and via monkeypatch, for the reason given on
    # `test_cache_lock_is_never_held_while_reading_the_registry`.
    monkeypatch.setattr(
        ModuleRegistry, "capability_snapshot", staticmethod(staged_snapshot)
    )

    errors = []
    stale = {}

    def slow_build():
        slow_thread["id"] = threading.get_ident()
        try:
            stale["manifest"] = get_capability_manifest(refresh=True)
        except Exception as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    worker = threading.Thread(target=slow_build, daemon=True)
    worker.start()
    assert snapshot_taken.wait(timeout=10), "slow build never read the registry"

    # The world moves on while that build is parked: the old distribution is
    # gone and a new one is installed.
    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups((_EntryPoint("new", _registers(("new.a", "cap.new"))),)),
        raising=False,
    )
    newer = refresh_capability_manifest()

    # Only now is the parked build allowed to finish and try to store.
    newer_published.set()
    worker.join(timeout=10)
    assert not worker.is_alive(), "slow build hung"
    assert not errors, errors

    # Precondition: the two documents really are different, or nothing below
    # could distinguish a rejected store from an accepted one.
    assert "old.a" in stale["manifest"]["modules"]
    assert "new.a" in newer["modules"]
    assert stale["manifest"]["hash"] != newer["hash"]

    # The cache serves the newer document. The stale build's store was refused.
    served = get_capability_manifest()
    assert served == newer
    assert served["hash"] == newer["hash"]
    assert compute_manifest_hash(served) == served["hash"]

    # And the losing build still received a whole, self-consistent document —
    # rejected for being old, not corrupted.
    assert compute_manifest_hash(stale["manifest"]) == stale["manifest"]["hash"]


def test_capability_snapshot_reads_under_one_lock(registry, installed):
    """The registry exposes the grouped read the manifest depends on.

    ``generation`` is part of that group deliberately: read separately it would
    describe whatever the registry became after the data was copied, which is
    the wrong answer for ordering two concurrent builds.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    snapshot = ModuleRegistry.capability_snapshot()

    assert set(snapshot) == {
        "registry_version",
        "generation",
        "metadata",
        "capabilities",
        "plugins",
    }
    assert "p.a" in snapshot["metadata"]
    assert snapshot["capabilities"]["one"] == ["p.a"]
    assert "p" in snapshot["plugins"]


def test_current_generation_agrees_with_the_snapshot(registry, installed):
    """The cheap staleness probe reports the same counter as the full read.

    ``get_capability_manifest`` validates a cache hit with
    ``current_generation()`` but publishes with the generation carried out of
    ``capability_snapshot``. If those two disagreed the cache would compare a
    stored value against a differently-scaled one and either never hit or never
    miss, so they are pinned to the same number here.

    A pure read must also leave the counter alone. It counts changes to the
    registry, and a probe that advanced it would make every reader invalidate
    every other reader's document forever.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    generation = ModuleRegistry.current_generation()
    assert generation == ModuleRegistry.capability_snapshot()["generation"]
    assert ModuleRegistry.current_generation() == generation

    ModuleRegistry.register(
        "p.b",
        _Module,
        {"module_id": "p.b", "category": "p", "stability": "stable"},
    )
    assert ModuleRegistry.current_generation() > generation
    assert (
        ModuleRegistry.current_generation()
        == ModuleRegistry.capability_snapshot()["generation"]
    )


# ---------------------------------------------------------------------------
# Coherence — a cached document must not outlive the state it describes
# ---------------------------------------------------------------------------
#
# The cache was previously a one-shot: the first document built in the process
# was returned by every later plain `get_capability_manifest()` call, forever.
# That is only sound if the capability surface cannot change in-process, and it
# can — `register`, `unregister`, `clear` and discovery all change it, and a
# plugin's `register_all` reaches every one of them. A worker that registered a
# module or reloaded its plugins went on publishing the surface it had at
# startup, under a hash naming that surface, so the staleness read as agreement
# rather than as staleness. These tests pin each of those routes.


def test_register_invalidates_the_cached_manifest(registry, installed):
    """A module registered after the first read shows up in the next one."""
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    before = get_capability_manifest()
    assert "p.b" not in before["modules"]

    ModuleRegistry.register(
        "p.b",
        _Module,
        {
            "module_id": "p.b",
            "category": "p",
            "provides_capability": "two",
            "stability": "stable",
        },
    )

    after = get_capability_manifest()
    assert "p.b" in after["modules"]
    assert after["module_count"] == before["module_count"] + 1
    assert "two" in [c["capability"] for c in after["capabilities"]]
    assert after["hash"] != before["hash"]
    # And the fresh document is the one the cache now holds, not a one-off.
    assert get_capability_manifest() == after


def test_unregister_invalidates_the_cached_manifest(registry, installed):
    """A module removed after the first read is gone from the next one.

    The direction that matters most: a manifest that over-reports is what makes
    a host dispatch work to a worker that can no longer do it.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"), ("p.b", "two"))))

    before = get_capability_manifest()
    assert "p.b" in before["modules"]

    ModuleRegistry.unregister("p.b")

    after = get_capability_manifest()
    assert "p.b" not in after["modules"]
    assert "two" not in [c["capability"] for c in after["capabilities"]]
    assert after["hash"] != before["hash"]


def test_clear_invalidates_the_cached_manifest(registry, installed, monkeypatch):
    """A cleared registry is not described by the document built before it.

    The entry points are removed alongside the `clear()`, deliberately. A clear
    on its own licenses the next discovery pass to replay
    `_plugin_contributions`, which correctly rebuilds the same registry — so a
    test that cleared and nothing else would compare a document against its own
    twin and pass whether or not the cache was consulted.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    before = get_capability_manifest()
    assert "p.a" in before["modules"]

    monkeypatch.setattr(
        registry_core, "entry_points", lambda **kw: _Groups(()), raising=False
    )
    ModuleRegistry.clear()

    after = get_capability_manifest()
    assert after["modules"] == []
    assert after["plugins"] == []
    assert after["hash"] != before["hash"]


def test_discovery_invalidates_the_cached_manifest(registry, installed, monkeypatch):
    """A discovery pass nobody told the cache about is still picked up.

    `refresh_capability_manifest()` publishes its own rebuild, so it was never
    the broken route. The broken route is a registry rebuilt by anything else —
    `ModuleRegistry.refresh()` called directly, a forced pass from an admin
    endpoint — after which the plain accessor kept serving the pre-pass surface.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))

    before = get_capability_manifest()
    assert "q.a" not in before["modules"]

    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups(
            (
                _EntryPoint("p", _registers(("p.a", "one"))),
                _EntryPoint("q", _registers(("q.a", "two"))),
            )
        ),
        raising=False,
    )
    ModuleRegistry.discover_plugins(force=True)

    after = get_capability_manifest()
    assert "q.a" in after["modules"]
    assert sorted(p["id"] for p in after["plugins"]) == ["p", "q"]
    assert after["hash"] != before["hash"]


def test_registry_refresh_alone_invalidates_the_cached_manifest(
    registry, installed, monkeypatch
):
    """`ModuleRegistry.refresh()` without the manifest wrapper is enough."""
    installed(_EntryPoint("old", _registers(("old.a", "cap.old"))))

    before = get_capability_manifest()
    assert "old.a" in before["modules"]

    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups((_EntryPoint("new", _registers(("new.a", "cap.new"))),)),
        raising=False,
    )
    ModuleRegistry.refresh()

    after = get_capability_manifest()
    assert "new.a" in after["modules"]
    assert "old.a" not in after["modules"]
    assert after["hash"] != before["hash"]


def test_refresh_manifest_is_visible_to_the_plain_accessor(
    registry, installed, monkeypatch
):
    """What `refresh_capability_manifest()` returns is what the cache serves."""
    installed(_EntryPoint("old", _registers(("old.a", "cap.old"))))
    get_capability_manifest()

    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups((_EntryPoint("new", _registers(("new.a", "cap.new"))),)),
        raising=False,
    )
    refreshed = refresh_capability_manifest()

    served = get_capability_manifest()
    assert served == refreshed
    assert compute_manifest_hash(served) == served["hash"]


def test_an_unchanged_registry_is_still_served_from_the_cache(
    registry, installed, monkeypatch
):
    """Validation must not turn every read into a rebuild.

    The point of the cache is that a read is cheap; a fix that simply rebuilt
    every time would be correct and useless. So this asserts the negative
    directly: with the registry untouched, no further `capability_snapshot`
    happens, and callers still receive distinct objects.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    first = get_capability_manifest()

    builds = []
    real_snapshot = ModuleRegistry.capability_snapshot

    def counted_snapshot():
        builds.append(1)
        return real_snapshot()

    monkeypatch.setattr(
        ModuleRegistry, "capability_snapshot", staticmethod(counted_snapshot)
    )

    second = get_capability_manifest()
    third = get_capability_manifest()

    assert builds == [], "an unchanged registry was rebuilt"
    assert second == first == third
    assert second is not third
    assert second["modules"] is not third["modules"]


def test_a_future_cache_generation_is_not_served(registry, installed, monkeypatch):
    """A stored generation *ahead* of the registry must rebuild, not be served.

    Validation used to accept `cached_generation >= current_generation()`,
    which reads as "monotonic counters can only fall behind" — but the stored
    half of the pair is ordinary process-local state, and nothing about the
    registry's monotonicity constrains it. A test that pins the field, a reset
    that rewinds `_generation` without clearing the slot, or any corruption of
    the pair leaves a document whose generation can never be caught up to.
    Under `>=` that document is served forever: the accessor stops rebuilding,
    and the stale hash it carries does not read as out of date, it reads as
    agreement with whatever host it is compared against.

    Equality fails closed instead. Here the slot is left describing the
    one-module registry while the counter is forced backwards beneath it, so
    the cached generation is unreachably high; the next plain read must ignore
    it, rebuild, and hand back the registry as it actually stands.
    """
    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    stale = get_capability_manifest()
    assert "p.a" in stale["modules"]

    # Register a second module the cached document does not know about, then
    # drive the live counter below the generation stored beside that document.
    ModuleRegistry.register("p.b", _Module, {"category": "test"})
    pinned = capability_manifest._cached_generation
    monkeypatch.setattr(
        ModuleRegistry,
        "current_generation",
        staticmethod(lambda: pinned - 1),
    )
    assert capability_manifest._cached_generation > ModuleRegistry.current_generation()

    served = get_capability_manifest()

    assert served != stale, "a future cache generation was served"
    assert "p.b" in served["modules"]
    assert served["module_count"] == len(served["modules"])
    assert compute_manifest_hash(served) == served["hash"]
    assert served == build_capability_manifest()


def test_cache_lock_is_never_held_while_validating_the_cache(
    registry, installed, monkeypatch
):
    """The hot path reaches the registry, so pin the ordering invariant there.

    Validation moved a registry read onto the path *every* caller takes, which
    is the likeliest place to reintroduce the inversion. Probed the same way as
    `test_cache_lock_is_never_held_while_reading_the_registry`: from another
    thread, because `RLock` would happily re-acquire on the owning one.
    """
    import threading

    installed(_EntryPoint("p", _registers(("p.a", "one"))))
    get_capability_manifest()  # populate the slot so the next call validates it

    violations = []
    real_generation = ModuleRegistry.current_generation

    def _cache_lock_is_held():
        held = {"value": True}

        def probe():
            if capability_manifest._cache_lock.acquire(blocking=False):
                capability_manifest._cache_lock.release()
                held["value"] = False

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join(timeout=5)
        return held["value"]

    def watched_generation():
        if _cache_lock_is_held():
            violations.append("cache lock held while entering current_generation")
        return real_generation()

    monkeypatch.setattr(
        ModuleRegistry, "current_generation", staticmethod(watched_generation)
    )

    get_capability_manifest()
    ModuleRegistry.register(
        "p.b",
        _Module,
        {"module_id": "p.b", "category": "p", "stability": "stable"},
    )
    get_capability_manifest()  # now a miss, so validation is followed by a build

    assert not violations, violations


def test_plugin_reentrant_plain_manifest_call_does_not_deadlock(
    registry, installed, monkeypatch
):
    """The inversion again, on the path validation added.

    `test_plugin_reentrant_manifest_call_does_not_deadlock` covers `refresh=True`,
    which always read the registry. The plain accessor did not, and now does —
    so the same two-thread ordering is replayed against it. The cache is primed
    from an *older* registry first, so the plugin's call is a genuine miss:
    validate, then rebuild, both from inside the discovery lock.

    If a future edit puts the registry read back under the cache lock, thread B
    parks on the registry holding the cache while thread A parks on the cache
    holding the registry, and the joins below time out.
    """
    import threading

    installed(_EntryPoint("stale", _registers(("stale.a", "stale.cap"))))
    primed = get_capability_manifest()
    assert "stale.a" in primed["modules"]

    b_started = threading.Event()
    plugin_entered = threading.Event()
    plugin_result = {}

    def register_all():
        ModuleRegistry.register(
            "deep.a",
            _Module,
            {
                "module_id": "deep.a",
                "category": "deep",
                "provides_capability": "deep.cap",
                "stability": "stable",
            },
        )
        plugin_entered.set()
        # Let B get as far as it can before re-entering from inside the
        # registry lock. Broken code has B holding the cache lock by now.
        b_started.wait(timeout=5)
        plugin_result["manifest"] = get_capability_manifest()

    monkeypatch.setattr(
        registry_core,
        "entry_points",
        lambda **kw: _Groups((_EntryPoint("deep", register_all),)),
        raising=False,
    )

    errors = []

    def thread_a():
        try:
            ModuleRegistry.discover_plugins(force=True)
        except Exception as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    def thread_b():
        try:
            plugin_entered.wait(timeout=5)
            b_started.set()
            get_capability_manifest()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    a = threading.Thread(target=thread_a, daemon=True)
    b = threading.Thread(target=thread_b, daemon=True)
    a.start()
    b.start()
    a.join(timeout=15)
    b.join(timeout=15)

    assert not a.is_alive(), "discovery thread hung — lock inversion regressed"
    assert not b.is_alive(), "reader thread hung — lock inversion regressed"
    assert not errors, errors
    # The plugin's plain read was a miss and rebuilt, so it saw the module it
    # had just registered rather than the primed document.
    assert "deep.a" in plugin_result["manifest"]["modules"]
    assert plugin_result["manifest"]["hash"] != primed["hash"]


def test_concurrent_plain_reads_stay_coherent_and_never_regress(registry, monkeypatch):
    """Plain readers racing refreshers: whole documents, and a cache that only
    moves forward.

    Two guarantees at once, because validation could plausibly break either.

    *Whole*: every document handed to a plain reader must be self-consistent,
    exactly as `test_concurrent_get_and_refresh_never_tears` requires of the
    forced-rebuild path.

    *Forward*: the generation stored beside the cached document must never
    decrease. A build that read the registry before a refresh and stored after
    it would push the cache backwards, and that regression is invisible in any
    single document — it only shows in the slot — so it is watched directly.

    The closing assertion is the coherence contract in one line: with every
    thread stopped, what the cache serves must equal what a fresh build sees.
    """
    import threading

    left = _Groups((_EntryPoint("left", _registers(("left.a", "cap.left"))),))
    right = _Groups(
        (
            _EntryPoint(
                "right", _registers(("right.a", "cap.right"), ("right.b", "cap.right"))
            ),
        )
    )
    installs = [left, right]
    picker = {"i": 0}

    def _entry_points(**_kw):
        return installs[picker["i"] % 2]

    _reset_registry()
    monkeypatch.setattr(registry_core, "entry_points", _entry_points, raising=False)
    ModuleRegistry.discover_plugins(force=True)
    _invalidate_manifest_cache()

    errors = []
    stop = threading.Event()

    def check(manifest):
        modules = set(manifest["modules"])
        caps = {c["capability"]: set(c["providers"]) for c in manifest["capabilities"]}

        assert manifest["module_count"] == len(modules)
        assert compute_manifest_hash(manifest) == manifest["hash"]
        for providers in caps.values():
            assert providers <= modules

        # A capability is present exactly when its provider is; a tear splits
        # these two halves, which come from different registry reads.
        if "cap.left" in caps:
            assert "left.a" in modules
            assert caps["cap.left"] == {"left.a"}
        if "cap.right" in caps:
            assert "right.a" in modules and "right.b" in modules
            assert caps["cap.right"] == {"right.a", "right.b"}

    def reader():
        try:
            while not stop.is_set():
                check(get_capability_manifest())
        except Exception as exc:  # noqa: BLE001 - reported to the main thread
            errors.append(exc)

    def refresher():
        try:
            while not stop.is_set():
                picker["i"] += 1
                check(refresh_capability_manifest())
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def watcher():
        # Sampled under the cache lock so the document and the generation
        # beside it are read from the same store, never from halfway through
        # one. The lock is a leaf, so parking on it here cannot wedge anything.
        highest = -1
        try:
            while not stop.is_set():
                with capability_manifest._cache_lock:
                    seen = capability_manifest._cached_generation
                assert seen >= highest, f"cache regressed: {highest} -> {seen}"
                highest = max(highest, seen)
                # Sampled rather than spun. A tight loop on a leaf lock is the
                # one thread here that could starve the publishers it is
                # watching, which would make the run prove nothing.
                stop.wait(0.001)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    threads.append(threading.Thread(target=refresher))
    threads.append(threading.Thread(target=refresher))
    threads.append(threading.Thread(target=watcher))
    for thread in threads:
        thread.daemon = True
        thread.start()
    stop.wait(2.0)
    stop.set()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "thread hung — suspect lock ordering"

    assert not errors, errors

    # At rest, the cache and the registry agree. A cache left holding a stale
    # or regressed document fails here even if every individual document above
    # was internally whole.
    assert get_capability_manifest() == build_capability_manifest()


def test_snapshot_ignores_the_stability_filter(registry, installed):
    """An alpha module is still installed, so it belongs in the manifest.

    Otherwise the document — and its hash — would depend on FLYTO_ENV, and two
    hosts with identical packages would disagree about what they can do.
    """
    def register_all():
        ModuleRegistry.register(
            "exp.thing",
            _Module,
            {
                "module_id": "exp.thing",
                "category": "exp",
                "provides_capability": "exp.cap",
                "stability": "alpha",
            },
        )

    installed(_EntryPoint("p", register_all))

    manifest = build_capability_manifest()
    assert "exp.thing" in manifest["modules"]
