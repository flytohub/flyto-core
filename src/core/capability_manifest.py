# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Capability Manifest — ``flyto.core.capability-manifest.v1``

A deterministic, in-process description of what this installation can do,
derived entirely from :class:`~core.modules.registry.ModuleRegistry`.

This is a *catalog*, not a process manager. Nothing here starts, stops, or
supervises a subprocess. It answers one question — "given the packages that
are installed right now, which module ids and capabilities exist?" — and it
answers it identically on every host that has the same packages installed.

Determinism is the contract. The document contains:

* module ids, sorted;
* capabilities with their providers, sorted;
* categories with counts, sorted;
* the id, version, and module count of every plugin that registered modules;
* the registry contract version and the flyto-core package version;
* a SHA-256 over the canonical form of all of the above.

It deliberately contains **no** timestamps, filesystem paths, hostnames,
usernames, environment values, credentials, or hardcoded device identities.
Two machines with the same installed distributions produce byte-identical
documents, so the hash can be compared across hosts to decide whether two
workers are running the same capability surface.

Usage::

    from core.capability_manifest import get_capability_manifest

    manifest = get_capability_manifest()
    manifest["hash"]          # stable fingerprint of the capability surface
    manifest["capabilities"]  # [{"capability": ..., "providers": [...]}, ...]
"""

from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy
from typing import Any, Dict, Optional

__all__ = [
    "MANIFEST_SCHEMA",
    "build_capability_manifest",
    "get_capability_manifest",
    "refresh_capability_manifest",
    "compute_manifest_hash",
]

#: Schema identifier for the document produced by this module. Bump the
#: trailing version when a field is removed or its meaning changes; adding a
#: new field is backward compatible and does not require a bump.
MANIFEST_SCHEMA = "flyto.core.capability-manifest.v1"

# Cached document. Building walks the whole registry, so the result is worth
# keeping — but only for as long as it is still true.
#
# It is not true for the life of the process. An earlier note here claimed the
# capability surface "cannot change inside a running process without an
# explicit refresh", and that was wrong in the ordinary case rather than the
# exotic one: `ModuleRegistry.register`, `unregister` and `clear` are public,
# a discovery pass rewrites the whole registry, and a plugin's `register_all`
# reaches all of them. Any of those leaves the slot holding a document that
# describes an installation that no longer exists — carrying a hash that names
# it. That is worse than holding nothing, because the hash is precisely what a
# host compares to decide whether two workers expose the same surface, so a
# stale document does not read as out of date, it reads as agreement.
#
# So the slot is *validated*, not trusted: see `_cached_generation` below and
# the check in `get_capability_manifest`.
#
# `_cache_lock` guards the cache *slot* — nothing else. It is held only across
# a pointer read or a pointer write, never across a build and never across the
# registry read that validates a hit.
#
# That restriction is a deadlock fix, not a style preference. An earlier
# version held this lock while building, and building acquires the registry's
# `_discovery_lock`. Meanwhile discovery holds `_discovery_lock` while running
# a plugin's `register_all`, and a plugin may legitimately call
# `get_capability_manifest()` — which wanted `_cache_lock`. Two threads, two
# locks, opposite orders: a textbook inversion that deadlocks the registry and
# every reader behind it. The earlier note here claimed "nothing in the
# registry reaches back into this module"; that was wrong, because plugin code
# runs *inside* the registry lock and plugin code can call anything.
#
# The invariant that replaces it, and the one to preserve when editing this
# module: **never hold `_cache_lock` while acquiring the registry lock or while
# running plugin code.** Build first with no lock held, then take `_cache_lock`
# just long enough to store the result. With the cache lock now a leaf — it is
# never held while waiting on anything — no ordering cycle can form.
#
# A stored manifest is never mutated in place, only rebound, so a reference
# captured under the lock stays safe to copy after releasing it.
_cache_lock = threading.RLock()
_cached: Optional[Dict[str, Any]] = None
# The registry generation the cached document was built from, or -1 when the
# slot is empty. It answers two different questions, and both of them are ones
# the document itself cannot.
#
# The first is whether a cache hit is still *valid*. `_cached is not None` only
# says a manifest was built at some point; it says nothing about whether the
# registry has changed since. Comparing the stored generation against
# `ModuleRegistry.current_generation()` says exactly that, because the counter
# is bumped by every site that mutates the registry content a manifest is
# derived from — register, unregister, clear, rollback, plugin load, plugin
# removal. Only an *equal* generation means the surface has not moved and the
# document still stands; anything else — a lower value because the registry
# advanced, or a higher one that no honest build could have produced — is
# rebuilt rather than served.
#
# The second is which of two concurrent builds should win the slot. Building
# outside the lock is what makes that necessary.
#
# Two builds can be in flight at once, and nothing makes them finish in the
# order they started. Left alone, whichever stores *last* wins — so a build
# that read the registry before a refresh, then lost the CPU, republishes that
# pre-refresh state over the post-refresh document already in the slot. Every
# subsequent cache hit is then served a manifest describing an installation
# that no longer exists, with a hash that names it, and nothing ever corrects
# it: the slot is only rewritten by the next build, which may lose the same
# race again. The refresh appears to have silently done nothing.
#
# Ordering by generation replaces "last store wins" with "newest state wins".
# `ModuleRegistry.capability_snapshot` reports the generation under the same
# lock hold that produced the data, so the comparison below is between the
# states themselves rather than between two thread schedules.
#
# Kept beside the document rather than inside it on purpose. The manifest must
# stay byte-identical across hosts, and a process-local mutation count is
# exactly the kind of host-shaped detail that would break that.
_cached_generation: int = -1


def _core_version() -> str:
    """The installed flyto-core package version, or ``"0.0.0"`` if unknown.

    Read through ``core.__version__`` so there is one answer in the process
    rather than a second, possibly divergent, ``importlib.metadata`` lookup.
    """
    try:
        from core import __version__

        return str(__version__)
    except Exception:
        return "0.0.0"


def compute_manifest_hash(payload: Dict[str, Any]) -> str:
    """Hash a manifest body into a stable hex digest.

    Canonicalized with sorted keys, no insignificant whitespace, and
    ``ensure_ascii`` so that a non-ASCII capability name cannot make the
    digest depend on the writer's encoding choices. The ``hash`` key itself
    is excluded, so hashing a complete manifest reproduces its own digest.
    """
    body = {key: value for key, value in payload.items() if key != "hash"}
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_with_generation() -> tuple[Dict[str, Any], int]:
    """Build the manifest and report the registry generation it describes.

    Split out from :func:`build_capability_manifest` so the cache can order
    concurrent builds without the generation leaking into the public document.
    The returned integer is process-local bookkeeping; the dict is the
    cross-host-comparable artifact.

    Every registry read comes from a single ``capability_snapshot()`` call,
    which gathers metadata, capabilities and plugins under one hold of the
    registry lock. Reading them separately would let a concurrent ``refresh()``
    land between two of them and produce a manifest describing a mixture of
    the old and new registries — a state that never existed, carrying a hash
    that names nothing.

    The snapshot is taken with the stability filter off, so the document
    describes what is *installed* rather than what ``FLYTO_ENV`` happens to
    expose; see ``ModuleRegistry.capability_snapshot``.
    """
    from core.modules.registry import ModuleRegistry

    snapshot = ModuleRegistry.capability_snapshot()
    all_metadata = snapshot["metadata"]

    module_ids = sorted(all_metadata)

    # Capabilities: {capability: [module_id, ...]}, already sorted both ways
    # by the registry. Re-sorted here anyway so this function does not depend
    # on that guarantee holding forever.
    capabilities = [
        {"capability": name, "providers": sorted(providers)}
        for name, providers in sorted(snapshot["capabilities"].items())
    ]

    # Categories, counted over the same unfiltered view as `modules` so the
    # counts always sum to `module_count`. Plugin-contributed categories are
    # included exactly like built-in ones — the registry does not distinguish
    # them here, and neither should the manifest.
    category_counts: Dict[str, int] = {}
    for metadata in all_metadata.values():
        category = (metadata or {}).get("category") or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1
    categories = [
        {"category": name, "module_count": count}
        for name, count in sorted(category_counts.items())
    ]

    # Plugins. `PluginInfo.loaded_at` is a wall-clock timestamp and
    # `entry_point` is an import path; both are omitted so the document stays
    # reproducible and free of host-shaped detail.
    plugins = [
        {
            "id": name,
            "version": info.version,
            "module_count": info.module_count,
        }
        for name, info in sorted(snapshot["plugins"].items())
    ]

    manifest: Dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "registry_version": snapshot["registry_version"],
        "core_version": _core_version(),
        "module_count": len(module_ids),
        "modules": module_ids,
        "capability_count": len(capabilities),
        "capabilities": capabilities,
        "category_count": len(categories),
        "categories": categories,
        "plugin_count": len(plugins),
        "plugins": plugins,
    }
    manifest["hash"] = compute_manifest_hash(manifest)
    return manifest, snapshot["generation"]


def build_capability_manifest() -> Dict[str, Any]:
    """Build the manifest from the live registry, bypassing the cache.

    The document only — see :func:`_build_with_generation` for the same build
    with the registry generation attached, which is what the cache orders on.
    """
    manifest, _ = _build_with_generation()
    return manifest


def get_capability_manifest(refresh: bool = False) -> Dict[str, Any]:
    """Return the capability manifest.

    The result is a deep copy of the cached document, so a caller that mutates
    what it gets back — a route handler adding a field, a test sorting a list
    in place — cannot corrupt the copy the next caller receives.

    The cache is *validated* on every hit rather than trusted. A stored document
    stops being true the moment the registry changes, and the registry changes
    for reasons that have nothing to do with this module: ``register()``,
    ``unregister()`` and ``clear()`` are public and a discovery pass rewrites
    everything. Before this check existed, the default path returned whatever
    had been built first for the rest of the process — so a worker that
    registered a module, or reloaded its plugins, went on reporting the surface
    it had at startup, with a hash naming that surface. The only ways out were
    ``refresh=True`` or ``refresh_capability_manifest()``, which callers of the
    plain accessor have no reason to know they need.

    Validation is one integer comparison against
    ``ModuleRegistry.current_generation()``, so a hit stays far cheaper than a
    build; when it fails, this falls through to the same rebuild-and-publish
    path ``refresh=True`` takes, and the same generation ordering keeps two
    concurrent rebuilds from putting an older document over a newer one.

    Args:
        refresh: Rebuild from the registry as it stands now even if the cached
            document is still current. Redundant for correctness now that hits
            are validated, and kept because it is the honest way to say "build
            me a document, do not hand me a shared one" — it also re-reads the
            registry but does **not** re-run plugin discovery; use
            :func:`refresh_capability_manifest` for that.
    """
    global _cached, _cached_generation

    if not refresh:
        with _cache_lock:
            cached = _cached
            cached_generation = _cached_generation
        # Everything below runs with the cache lock released, and that is the
        # invariant at its most fragile: this is the hot path, and the check it
        # performs reaches into the registry. Taking the registry lock here
        # while still holding `_cache_lock` would rebuild the exact inversion
        # the top of this module documents — and rebuild it on the code path
        # that every reader takes, rather than on a rare one.
        if cached is not None:
            from core.modules.registry import ModuleRegistry

            # `==`, not an ordering. The document is true for exactly one
            # registry state, so the only generation that licenses serving it
            # is the one it was built from. Accepting `>=` also accepted every
            # stored value *above* the live counter, and those are reachable:
            # a test that pins `_cached_generation`, a partially applied reset
            # that rewinds `_generation` without clearing the slot, or any
            # corruption of this process-local pair pins the cache open and the
            # manifest never rebuilds again — the exact stale-hash-reads-as-
            # agreement failure this validation exists to prevent. Equality
            # costs nothing extra and fails closed: a mismatch in either
            # direction rebuilds.
            if cached_generation == ModuleRegistry.current_generation():
                # Copy outside the lock. A stored manifest is only ever
                # rebound, never mutated in place, so this reference cannot
                # change under the copy.
                return deepcopy(cached)
        # Either nothing is cached or what is cached predates a registry
        # change. Both are answered by building, below.

    # Built with NO cache lock held — see the invariant above. Building takes
    # the registry lock, and holding the cache lock across that is exactly the
    # inversion that deadlocks against a plugin calling in during discovery.
    built, generation = _build_with_generation()

    with _cache_lock:
        # Publish only if this build describes registry state at least as new
        # as what is already cached. Building outside the lock means two builds
        # can finish out of order, and an unconditional store would let the
        # older one overwrite the newer — leaving the cache permanently behind
        # a refresh that appears to have succeeded. The empty-slot case is
        # spelled out because a test (or any explicit invalidation) may drop
        # the document without being able to lower the monotonic counter.
        if _cached is None or generation >= _cached_generation:
            _cached = built
            _cached_generation = generation

    # Return what *this* call built rather than re-reading the slot. A build
    # whose store was rejected as stale still describes a registry state that
    # genuinely existed, is wholly self-consistent, and hashes to itself, so it
    # is a truthful answer to the caller who asked for it — just no longer the
    # right thing to serve to everybody else.
    return deepcopy(built)


def refresh_capability_manifest() -> Dict[str, Any]:
    """Re-discover plugins, then rebuild and return the manifest.

    This is the privileged path: it calls ``ModuleRegistry.refresh()``, which
    clears the registry and re-runs entry point discovery, so a distribution
    installed or uninstalled since startup is picked up.

    It cannot reload Python modules that are already imported. A plugin whose
    *code* changed still needs a worker restart; what this recovers is a
    change to the *set* of installed plugins.
    """
    from core.modules.registry import ModuleRegistry

    # No cache lock is held across either step, and deliberately so.
    # `ModuleRegistry.refresh()` re-runs discovery, which executes plugin
    # `register_all` code while holding the registry lock; a plugin that calls
    # back into this module would then wait on a cache lock held by the thread
    # waiting on the registry. Holding nothing here keeps the cache lock a leaf.
    #
    # Two concurrent refreshes may still interleave, but the winner is decided
    # by registry generation rather than by which thread happened to store
    # last, so the cache always ends up holding the newest state either of them
    # observed. The rebuild below returns the document *this* call built, so a
    # caller of refresh receives the state as of their own rebuild even when a
    # newer one has already been published.
    ModuleRegistry.refresh()
    return get_capability_manifest(refresh=True)
