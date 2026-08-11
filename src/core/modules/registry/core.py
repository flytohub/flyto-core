# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module Registry - Core Registration and Lookup

Manages all registered modules and their metadata.
Supports plugin discovery via entry_points for Open Core architecture.
"""
# Registry version for sync tracking.
#
# This is a contract version, not a package version: it rides along in every
# RegistrySnapshot, so a checkpoint taken under one set of discovery semantics
# can be told apart from one taken under another when it is resumed. Bump it
# whenever discovery, ownership, or the registration transaction changes what a
# caller can conclude from the registry — not merely when this file is edited.
#
# 1.1.0 — a failed plugin load is rolled back whole. Rollback previously
#   replayed only the rows a plugin overwrote, so a pass that removed rows
#   before raising left those removals standing; it now restores every row the
#   pass disturbed by any route, deletions included.
# 1.2.0 — the first discovery is serialised. A read arriving from another
#   thread while discovery ran used to be answered from the half-built
#   registry, so two threads in one process could take snapshots with
#   different module_count/modules_hash for the same install. Such a read now
#   waits for the pass and sees the whole registry; re-entry from the
#   discovering thread itself is still answered from the partial state, which
#   is the only answer that cannot deadlock.
# 1.3.0 — a read is whole for its whole duration. 1.2.0 serialised the decision
#   to discover but released the lock before the caller touched a single row, so
#   a read that had already passed the "already initialised" fast path went on to
#   copy and iterate ``_modules``/``_metadata`` with nothing held. A forced pass
#   starting in that window mutated the dicts underneath it, which is a torn
#   answer — or a RuntimeError — rather than a merely stale one. Every public
#   read and every direct write now holds ``_discovery_lock`` across its entire
#   body, so a caller receives a snapshot that stood whole at one instant.
# 1.4.0 — a metadata row is the registry's alone, all the way down. Every copy on
#   the registration, rollback and read boundaries was one level deep, so the
#   nested values — ``params_schema``, ``tags``, ``required_permissions`` — stayed
#   shared with whoever handed them in or was handed them back. A package could
#   register metadata, keep its reference, and afterwards append to the stored
#   ``required_permissions`` list; a caller could do the same through
#   ``get_metadata()``. Either edits registry state from outside the lock and
#   without passing through ``register()``, which is the one place ownership and
#   defaults are assigned. Rollback aliased the live rows the same way, so the
#   state a failed load would be restored from could be rewritten before it was
#   used. Those boundaries now copy deeply, so a row a caller holds and a row the
#   registry holds are separate objects at every depth.
REGISTRY_VERSION = "1.4.0"

import copy  # noqa: E402, I001
import functools  # noqa: E402
import hashlib  # noqa: E402
import logging  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from datetime import datetime  # noqa: E402
from importlib.metadata import entry_points, version as get_version  # noqa: E402
from typing import Any, Dict, List, Optional, Set, Tuple, Type  # noqa: E402

from ...constants import ErrorMessages  # noqa: E402
from ..base import BaseModule  # noqa: E402
from ..types import (  # noqa: E402
    TIER_DISPLAY_ORDER,
    ModuleTier,
    StabilityLevel,
    get_current_env,
    is_module_visible,
)


@dataclass(frozen=True)
class PluginInfo:
    """Information about a discovered plugin package.

    Frozen, and for the same reason the discovery paths hand back a copy of the
    plugin mapping rather than the mapping itself. Copying the dict stops a
    caller from adding or removing plugins; it does not stop one from reaching
    through a value it was handed, because the ``PluginInfo`` objects in the
    copy are the ones in ``_plugins`` — a shallow copy shares them by design, so
    ``handed["thermal"].module_count = 99`` would rewrite the registry's own
    record of that plugin, from outside the lock and without calling
    ``register()``.

    Sharing them is still right: this is a description of what discovery
    observed at one instant, not registry state a caller is meant to steer. What
    was wrong was that the description could be edited. Freezing makes the value
    say only what the pass that built it found, so handing the same object to
    every caller is safe and no defensive deep copy is needed on a hot read.

    Registry code never mutates one either — ``_load_plugin`` replaces the whole
    entry when a plugin's contents change, which is the honest way to record it:
    a plugin's size is a fact about a pass, so a new pass writes a new value
    rather than editing the old pass's report of itself.
    """
    name: str
    version: str
    module_count: int
    loaded_at: datetime = field(default_factory=datetime.now)
    entry_point: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "module_count": self.module_count,
            "loaded_at": self.loaded_at.isoformat(),
            "entry_point": self.entry_point
        }


@dataclass
class RegistrySnapshot:
    """Snapshot of registry state for execution version binding"""
    registry_version: str
    plugins: Dict[str, str]  # plugin_name -> version
    module_count: int
    modules_hash: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry_version": self.registry_version,
            "plugins": self.plugins,
            "module_count": self.module_count,
            "modules_hash": self.modules_hash,
            "created_at": self.created_at.isoformat()
        }


def get_localized_value(value: Any, lang: str = 'en') -> str:
    """
    Extract localized string from value.

    Stub implementation - actual translations provided by flyto-i18n.
    Supports:
    1. String: returns as-is
    2. Dict: {"en": "...", "zh": "...", "ja": "..."}
    """
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        if lang in value:
            return value[lang]
        if 'en' in value:
            return value['en']
        return next(iter(value.values())) if value else ''
    return str(value) if value else ''


logger = logging.getLogger(__name__)


ENTRY_POINT_GROUP = "flyto.modules"

# One registry row as discovery remembers it: the class, and the metadata that
# was stored alongside it (None for a module registered without any).
RegistryRow = Tuple[Optional[Type[BaseModule]], Optional[Dict[str, Any]]]


def _iter_entry_points(group: str = ENTRY_POINT_GROUP) -> List[Any]:
    """The entry points in ``group``, as a list.

    Materialised rather than passed around lazily: discovery walks the group
    twice — once to load each plugin, once to decide which previously loaded
    plugins are no longer installed — and an exhausted iterator would make the
    second walk conclude that everything had been uninstalled.

    Read through the module-level ``entry_points`` name so a test can substitute
    a group without building and installing a distribution to do it.
    """
    if sys.version_info >= (3, 10):
        return list(entry_points(group=group))
    return list(entry_points().get(group, []))


def _synchronized(method):
    """Hold ``ModuleRegistry._discovery_lock`` for the whole of ``method``.

    Serialising the *decision* to discover was not enough. A read used to take
    the lock only long enough for ``_ensure_discovered`` to conclude that the
    registry was already initialised, drop it, and then copy or iterate
    ``_modules`` and ``_metadata`` with nothing held at all. A forced pass
    starting in that window — ``discover_plugins(force=True)``, and so every
    ``refresh()`` — rewrites those dicts while the read is walking them. The
    result is not a stale answer, which would at least describe some install
    that existed; it is a torn one, half of it from before the rebuild and half
    from after, or a ``RuntimeError: dictionary changed size during iteration``
    if the timing is unluckier still.

    So the lock spans the entire call: the ``_ensure_discovered`` check *and*
    every copy, iteration, hash and filter that follows it. What a caller gets
    back is a registry that stood whole at one instant.

    The lock is an ``RLock``, and that is load-bearing rather than incidental.
    Discovery holds it for the length of a pass with plugin code running inside,
    and a plugin's ``register_all`` legitimately reads the catalog and registers
    modules — both of which now arrive here. A plain ``Lock`` would have the
    discovering thread wait on itself for work only it can do. Re-entry from
    that thread is still *answered from the partial state*: the lock decides
    when a caller runs, ``_discovery_thread`` decides whether it discovers, and
    conflating the two is what an ``RLock`` alone would do.

    ``functools.wraps`` is not cosmetic here. These are the registry's public
    surface, and ``docs/reference/python-api.md`` is generated by introspecting
    it; an unwrapped closure would rename every method to ``guarded`` and strip
    the docstring the reference is built from.

    Ordering note for anyone adding to this: the lock must stay the innermost
    thing the registry waits on. Discovery already imports plugin packages while
    holding it, so a *second* lock acquired underneath it — most realistically
    the import lock, via a module that registers as an import side effect on
    another thread — is the one way to build a cycle here. Do not decorate
    anything that awaits, blocks on I/O, or calls out to code that may.
    """

    @functools.wraps(method)
    def guarded(cls, *args, **kwargs):
        with cls._discovery_lock:
            return method(cls, *args, **kwargs)

    return guarded


class ModuleRegistry:
    """
    Module Registry - Singleton Pattern

    Manages all registered modules and their metadata.
    Provides querying, filtering, and execution capabilities.

    Supports plugin discovery via entry_points:
    - flyto-core registers 'community' modules
    - flyto-modules-pro can register 'pro' modules
    - Any package can add modules via entry_points
    """

    _instance = None
    _modules: Dict[str, Type[BaseModule]] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}
    _plugins: Dict[str, PluginInfo] = {}
    _initialized: bool = False
    # Monotonic counter over every change to the three dicts above — the exact
    # state a capability manifest is derived from. It answers one question a
    # reader cannot otherwise answer: *when* did the state I just read exist,
    # relative to the state somebody else read?
    #
    # A build that reads the registry, is descheduled, and finishes after a
    # concurrent refresh has already published a newer document would otherwise
    # overwrite that document with an older one — a cache that goes backwards.
    # Carrying the generation out with the snapshot lets the cache reject the
    # older store instead of taking it (see ``core.capability_manifest``).
    #
    # Process-local and meaningless across hosts, so it is deliberately *not*
    # part of the manifest document: two machines with the same installed
    # distributions must still produce byte-identical manifests.
    #
    # Only ever incremented, never reset — a reset would make an older snapshot
    # compare as newer, which is the bug this exists to prevent. Bumped under
    # ``_discovery_lock`` at every site that mutates registry content.
    _generation: int = 0
    # The plugin whose register_all() is currently running, or "" for
    # flyto-core's own modules. Set only inside discover_plugins so that
    # ownership is a fact about how a module arrived, not something a module
    # can claim about itself.
    _loading_plugin: str = ""
    # True for the span of a discovery pass. A read that arrives while plugins
    # are still registering is answered from the partial state rather than
    # starting a second pass underneath the first one.
    _discovering: bool = False
    # Serialises discovery so a first read never observes a half-built
    # registry. Reentrant, because discovery legitimately re-enters itself: a
    # plugin's register_all reads the catalog, that read calls
    # _ensure_discovered, and a plain Lock would have the discovering thread
    # wait for a pass only it can finish.
    #
    # The lock alone is not enough, which is why _discovery_thread exists
    # beside it. Re-entry must be answered from the partial state rather than
    # by running a second pass underneath the first, and an RLock cannot tell
    # those apart — it would happily let the owner recurse. So the owning
    # thread's id decides *whether* to discover, and the lock decides *when*.
    _discovery_lock = threading.RLock()
    # The thread running the current pass, or None. Safe to read whether or not
    # the lock is held — it is a single attribute load, and the only thread that
    # can see its own id there is the one that put it there. ``discover_plugins``
    # still consults it *before* the lock, deliberately: the lock is reentrant,
    # so the owning thread would acquire it and run a second pass underneath the
    # first. Readers reach it with the lock already held, via @_synchronized.
    #
    # It, not _initialized, is what a reader must consult first. A forced pass
    # rebuilds an already-initialised registry without ever lowering that flag,
    # so the flag answers "has a pass completed", never "is one running".
    _discovery_thread: Optional[int] = None
    # What each entry point contributed the last time it actually registered
    # anything, and what flyto-core's own modules were before any plugin ran.
    # Registration usually happens as an import side effect, and an import
    # happens once per process; without this record the second discovery in a
    # process rebuilds an emptier registry than the first one did.
    _plugin_contributions: Dict[str, Dict[str, RegistryRow]] = {}
    _core_baseline: Dict[str, RegistryRow] = {}
    # The ids the plugin currently loading has registered, and the rows those
    # registrations displaced. Non-None only for the span of one register_all();
    # see _load_plugin. Ownership metadata cannot stand in for either: it says
    # who owns a row now, not whether this pass put it there, so it cannot tell
    # a module the plugin still provides from one left over from a previous
    # pass, nor a row the plugin created from one it overwrote.
    _pass_registered: Optional[Set[str]] = None
    _pass_displaced: Dict[str, RegistryRow] = {}
    # Every id the pass has *changed*, by any route, and so every id whose
    # pre-pass row has already been banked in _pass_displaced. Deliberately
    # wider than _pass_registered: removing a row changes the registry just as
    # much as overwriting one, and a rollback that only knows about writes puts
    # back the rows the plugin clobbered while leaving the ones it deleted gone.
    # Kept separate rather than folded into _pass_registered because that set
    # answers a different question — which modules the plugin still provides —
    # and an id the plugin only deleted must not count as one it provides.
    _pass_touched: Optional[Set[str]] = None
    # Set by clear(), consumed by the next discovery pass. Replay is a repair
    # for a cleared registry, so the condition has to be "clear() happened", not
    # "the registry is empty": a registry emptied deliberately, by unregistering
    # a plugin's modules one at a time, looks identical to a cleared one and
    # must not have those modules replayed back into it.
    _cleared: bool = False
    # _cleared as the current pass found it, snapshotted once because plugins
    # registering during the pass do not change what the pass started from.
    _started_empty: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def _bump_generation(cls) -> None:
        """Record that registry content changed.

        Called from every site that writes ``_modules``, ``_metadata`` or
        ``_plugins``, always with ``_discovery_lock`` already held — either
        through ``@_synchronized`` or from inside a discovery pass — so the
        read-modify-write below is atomic with respect to the change it
        describes.

        Deliberately coarse: it counts *changes*, not distinct states. Two
        bumps that happen to leave identical content still advance the counter,
        which costs a redundant manifest store and never a wrong one. The
        opposite error — a mutation that forgets to bump — is the one that
        matters, because it lets two different states share a generation and so
        lets the older of the two win the cache.
        """
        cls._generation += 1

    @classmethod
    @_synchronized
    def current_generation(cls) -> int:
        """The mutation counter as it stands now.

        The cheap half of ``capability_snapshot``. A caller holding a document
        built from generation *G* needs one thing to know whether that document
        is still true: has the registry moved since? Rebuilding the whole
        snapshot to find out would make every cache validation cost as much as
        the rebuild it is trying to avoid, and would copy every metadata row to
        return an integer.

        The counter is monotonic and never rewound, so ``G ==
        current_generation()`` is exactly "nothing has changed since that
        document was built". A caller may serve what it holds only on that
        equality; any other value — larger because the registry advanced, or
        smaller because the caller's own bookkeeping is wrong — means the
        document is not known to describe the live registry and must be
        rebuilt. Callers should compare with ``==`` rather than ``>=`` so a
        corrupt or pinned stored generation fails closed into a rebuild
        instead of pinning a stale document open forever. This is what lets
        ``core.capability_manifest`` keep a cache at all: without it the only
        honest options are to rebuild on every read or to serve a document that
        silently stops describing the installation.

        Deliberately does **not** call ``_ensure_discovered``. This is a
        question about bookkeeping, not about the catalog, and answering it must
        not import plugin packages or run ``register_all`` — a staleness probe
        sitting on a hot read path is the last place that work belongs. Nothing
        is lost by leaving it out: a caller with no usable document goes on to
        build one, and that build's ``capability_snapshot`` discovers under the
        same lock.

        Read under ``_discovery_lock`` rather than as a bare attribute load.
        The lock is what makes the number describe a registry that stood whole:
        a pass in flight has bumped the counter several times and is not
        finished bumping it, so an unlocked read could return a generation for
        a state no caller can ever obtain a snapshot of, and a rebuild ordered
        against it would compare two states that never coexisted. Waiting is
        also the cheaper error — the worst case is one redundant rebuild.

        Process-local and meaningless across hosts; see ``_generation``. It must
        not be copied into any document that is compared between machines.
        """
        return cls._generation

    @classmethod
    @_synchronized
    def register(cls, module_id: str, module_class: Type[BaseModule], metadata: Optional[Dict[str, Any]] = None):
        """
        Register a module

        Args:
            module_id: Unique module identifier (e.g., "browser.goto")
            module_class: Module class inheriting from BaseModule
            metadata: Module metadata (optional)
        """
        cls._note_pass_touch(module_id)
        if cls._pass_registered is not None:
            cls._pass_registered.add(module_id)
        cls._modules[module_id] = module_class
        if not metadata and cls._loading_plugin:
            # A module registered by a plugin with no metadata would otherwise
            # carry no owner, and an absent owner reads as flyto-core's own —
            # which is precisely the identity a denied plugin would want. Give
            # it the minimum needed to be attributable.
            metadata = {}
        if metadata is not None and (metadata or cls._loading_plugin):
            # Copy before stamping or storing. Both matter, for the same reason.
            # Stamping in place would edit a dict the caller still owns, and
            # storing that same object would leave the registry holding an alias
            # to caller state: a package could hand over metadata, keep its
            # reference, and afterwards set ``plugin`` to another plugin's name
            # or to '' — which reads as flyto-core's own. The assignment below
            # is unconditional precisely so ownership cannot be claimed, and
            # that guarantee is only worth as much as the registry's exclusive
            # hold on the row. _restore already copies on the way in and out;
            # this is the same discipline at the entry point.
            #
            # Deep, not one level, and over an exact ``dict``. A shallow copy
            # detaches only the top mapping, so every nested value stays the
            # caller's object — a live handle on the stored ``params_schema``,
            # ``required_permissions``, ``tags`` and ``can_connect_to``. And
            # ``deepcopy`` alone is a copy the caller can refuse: it dispatches
            # on the exact type and otherwise asks the value how to copy itself,
            # so a ``dict`` subclass whose ``__deepcopy__`` returns ``self`` is
            # handed back and the registry holds the caller's row after all.
            # Enforcement reads the stored row, so a permission grown after
            # registration — or an owner rewritten — is one nobody vouched for.
            metadata = copy.deepcopy(dict(metadata))
            # Ensure required fields
            metadata.setdefault('module_id', module_id)
            metadata.setdefault('version', '1.0.0')
            metadata.setdefault('category', module_id.split('.')[0])
            metadata.setdefault('tags', [])
            # Which plugin this module arrived from, assigned rather than
            # accepted: it is overwritten unconditionally, so a package cannot
            # register a module claiming to belong to another plugin — or to
            # none, which is the more valuable lie because flyto-core's own
            # modules are the ones the process-global permission grant reaches.
            metadata['plugin'] = cls._loading_plugin
            cls._metadata[module_id] = metadata
        cls._bump_generation()
        logger.debug(f"Module registered: {module_id}")

    @classmethod
    @_synchronized
    def unregister(cls, module_id: str):
        """Remove a module from registry"""
        if module_id in cls._modules:
            # Banked before the deletion, which is the last moment the row
            # exists. A plugin removing a module is doing so as part of a
            # registration that has not been vouched for yet, so the removal is
            # provisional in exactly the way a write is.
            cls._note_pass_touch(module_id)
            del cls._modules[module_id]
            if module_id in cls._metadata:
                del cls._metadata[module_id]
            cls._bump_generation()
            logger.debug(f"Module unregistered: {module_id}")

    # ========================================
    # Ownership and state bookkeeping (private)
    # ========================================

    @classmethod
    def _note_pass_touch(cls, module_id: str) -> None:
        """Bank the row standing at ``module_id`` before this pass disturbs it.

        No-op outside a plugin's ``register_all``: registrations that are not
        part of a pass are nobody's to roll back.

        Only the first touch of an id is recorded, so a plugin that writes an id
        twice — or deletes one it wrote, or rewrites one it deleted — is rolled
        back to the row that stood there before *any* of that, not to the
        intermediate state its previous touch happened to leave. An id that held
        nothing is recorded as no entry, which is what tells rollback to delete
        it rather than restore it.
        """
        if cls._pass_touched is None or module_id in cls._pass_touched:
            return
        cls._pass_displaced.update(cls._capture([module_id]))
        cls._pass_touched.add(module_id)

    @classmethod
    @_synchronized
    def _ensure_discovered(cls) -> None:
        """Make a catalog read answer about what is installed.

        Reading the catalog is not a reason to run anything. Discovery imports
        the packages that declare a ``flyto.modules`` entry point and lets them
        register — the same work ``get()`` has always triggered — and never
        instantiates a module or calls ``execute()``. Before this existed the
        registry answered honestly only after somebody had asked for a module by
        id, so ``capabilities()`` and ``list_all()`` reported an empty install
        until an execution happened to warm them.

        A read from a thread that is not the one discovering waits for the pass
        instead of being answered from it. That wait is the point: the partial
        registry is not a smaller install, it is an install nobody has finished
        describing, and handing it to a caller produced snapshots that disagreed
        about the same machine depending on which thread asked first.

        Whether a pass is in flight is therefore asked *before* whether the
        registry is initialised, and the order is the whole guarantee. A forced
        rediscovery — ``discover_plugins(force=True)``, and so ``refresh()`` —
        rebuilds a registry that is already initialised and never lowers the
        flag, so a reader that consults ``_initialized`` first sails past the
        lock and reads the registry mid-rebuild. That is the same partial read
        this method exists to prevent, arriving by the one route where the fast
        path is wrong: the flag says a pass has completed, not that none is
        running.

        Deciding correctly is only half of it. Every public read reaches here
        through ``@_synchronized`` and keeps the lock for its whole body, so the
        answer this method licenses cannot be invalidated by a forced pass
        between the check and the caller's copy of ``_modules``. Returning early
        below therefore means "the registry is whole *and stays whole* until you
        return", not merely "a pass finished at some point before now".
        """
        owner = cls._discovery_thread
        if owner is not None:
            if owner == threading.get_ident():
                # This thread's own pass, re-entered — from a plugin's
                # register_all, or from a catalog read that plugin made. Waiting
                # here would be waiting for work only this thread can do, so
                # answer from the partial state, exactly as before.
                return
            # Somebody else is mid-pass. Fall through to the lock and wait,
            # whatever _initialized currently claims.
        elif cls._initialized:
            return

        with cls._discovery_lock:
            # Reached either because no pass had run, or because one was in
            # flight and has now finished. In the second case the registry is
            # whole and initialised, so this starts nothing.
            if not cls._initialized:
                cls.discover_plugins()

    @classmethod
    def _owned_by(cls, plugin_name: str) -> List[str]:
        """Module ids whose metadata says they arrived from ``plugin_name``.

        Ownership is the only trustworthy count of what a plugin contributed:
        it survives a re-registration that overwrites rows instead of adding
        them, which is what a second discovery pass does and what made an
        installed plugin report ``module_count`` 0.
        """
        return [
            module_id
            for module_id, metadata in cls._metadata.items()
            if (metadata or {}).get('plugin', '') == plugin_name
        ]

    @classmethod
    def _first_party_ids(cls) -> List[str]:
        """Module ids that no plugin owns — flyto-core's own registrations."""
        return [
            module_id
            for module_id in cls._modules
            if not (cls._metadata.get(module_id) or {}).get('plugin', '')
        ]

    @classmethod
    def _capture(cls, module_ids: Any) -> Dict[str, RegistryRow]:
        """Copy the registry rows for ``module_ids``, for replay or rollback.

        The metadata is copied deeply. A capture is a record of how a row stood
        at one instant, and a one-level copy is not that: the nested values stay
        the live row's objects, so a plugin that mutates the stored
        ``params_schema`` or ``required_permissions`` in place edits the record
        rollback will restore from. The pass would then be "undone" back to
        state it wrote itself, which is the failure banking the row exists to
        prevent. The module class is shared deliberately — a class is the thing
        being remembered, not a container of it, and copying one would restore a
        different type than the registry held.
        """
        captured: Dict[str, RegistryRow] = {}
        for module_id in module_ids:
            if module_id not in cls._modules and module_id not in cls._metadata:
                continue
            metadata = cls._metadata.get(module_id)
            captured[module_id] = (
                cls._modules.get(module_id),
                copy.deepcopy(dict(metadata)) if metadata is not None else None,
            )
        return captured

    @classmethod
    def _restore(cls, rows: Dict[str, RegistryRow], drop: Any = ()) -> None:
        """Put ``rows`` back exactly, after removing every id in ``drop``.

        Deep on the way out as well as in. ``_core_baseline`` and
        ``_plugin_contributions`` are replayed more than once across a process,
        so handing the registry the recorded nested objects themselves would let
        the next pass — or anything holding the restored row — edit the record
        every later replay is rebuilt from.
        """
        for module_id in drop:
            cls._modules.pop(module_id, None)
            cls._metadata.pop(module_id, None)
        for module_id, (module_class, metadata) in rows.items():
            if module_class is not None:
                cls._modules[module_id] = module_class
            if metadata is None:
                cls._metadata.pop(module_id, None)
            else:
                cls._metadata[module_id] = copy.deepcopy(dict(metadata))
        cls._bump_generation()

    @classmethod
    @_synchronized
    def get(cls, module_id: str) -> Type[BaseModule]:
        """
        Get module class by ID

        Args:
            module_id: Module identifier

        Returns:
            Module class

        Raises:
            ValueError: If module not found
        """
        cls._ensure_discovered()
        if module_id not in cls._modules:
            raise ValueError(
                ErrorMessages.format(
                    ErrorMessages.MODULE_NOT_FOUND,
                    module_id=module_id
                )
            )
        return cls._modules[module_id]

    @classmethod
    @_synchronized
    def has(cls, module_id: str) -> bool:
        """Check if module exists"""
        cls._ensure_discovered()
        return module_id in cls._modules

    @classmethod
    @_synchronized
    def module_count(cls) -> int:
        """Get number of registered modules"""
        cls._ensure_discovered()
        return len(cls._modules)

    @classmethod
    @_synchronized
    def capabilities(cls) -> Dict[str, List[str]]:
        """What the installed modules can do, by capability.

        The plugin contribution point, read side. A package declares
        ``provides_capability`` on a module, and this is how a host discovers
        that installing it made a capability available — without anyone having
        to hand-type the capability name into a command somewhere else.

        Returns ``{capability: [module_id, ...]}``, module ids sorted so the
        answer is stable across runs and can be compared or cached. Modules
        declaring nothing are absent rather than present with an empty key,
        which is almost all of them: a capability is about work a *resource*
        must be chosen for, and most modules are software that needs none.

        A capability with several providers is normal and not an error. Two
        packages may both be able to read a code, and which one runs is a
        binding decision the host makes with the resources it has, not one this
        registry is entitled to make by discarding a provider.
        """
        cls._ensure_discovered()
        found: Dict[str, List[str]] = {}
        for module_id, metadata in cls._metadata.items():
            capability = (metadata or {}).get("provides_capability") or ""
            capability = capability.strip()
            if not capability:
                continue
            found.setdefault(capability, []).append(module_id)
        return {name: sorted(ids) for name, ids in sorted(found.items())}

    @classmethod
    @_synchronized
    def clear(cls):
        """Clear all registered modules and metadata (for hot-reload).

        Outside a discovery pass the loading owner is reset too: a caller that
        clears the registry while a plugin's registration is unwound is
        otherwise left with that plugin's name attached to whatever registers
        next.

        Inside one it is kept, along with the pass ledger — see below.

        What discovery previously observed each entry point contribute is not
        cleared, because it is not registry content — it is the only way to
        rebuild that content. A plugin that registers as an import side effect
        can be asked exactly once per process; on the next discovery its
        ``register_all`` is a cached no-op, so without the record a
        clear/discover cycle would silently return a smaller registry than the
        one it replaced. Nothing but discovery reads it.
        """
        # A plugin's register_all reaches clear() as easily as it reaches
        # register() or unregister(), and clear() was the one route of the three
        # that took the pass's identity and its rollback ledger with it.
        in_pass = cls._pass_touched is not None

        # Bank every row before dropping it, so a pass that clears the registry
        # and then raises is rolled back whole like any other. Without this the
        # ledger is empty at exactly the moment it describes the most damage:
        # rows cleared this way are neither a write nor an unregister, so
        # nothing else records them.
        if in_pass:
            for module_id in list(cls._modules) + list(cls._metadata):
                cls._note_pass_touch(module_id)

        cls._modules.clear()
        cls._metadata.clear()
        cls._plugins.clear()
        cls._bump_generation()
        cls._initialized = False
        if not in_pass:
            cls._loading_plugin = ""
            # The in-flight registration record goes with the owner it belongs
            # to. Leaving it live would have the next registration recorded
            # against a plugin that is no longer being credited with it.
            cls._pass_registered = None
            cls._pass_touched = None
            cls._pass_displaced = {}
        # Inside a pass both are kept. Dropping the owner would stamp everything
        # the plugin registers next with no plugin at all — which reads as
        # flyto-core's own, and first-party is the one identity the
        # process-global permission grant reaches. register() assigns ownership
        # rather than accepting it precisely so that a package cannot make that
        # claim about itself; letting it clear the owner instead would hand over
        # the same escalation by a longer route. Nothing is lost by keeping it:
        # _load_plugin and discover_plugins both reset it in `finally`, so it
        # cannot outlive the pass either way.
        # Licenses the next discovery pass to replay what each entry point
        # contributed, since a cached import cannot be asked to do it again.
        cls._cleared = True
        logger.debug("Registry cleared")

    @classmethod
    @_synchronized
    def list_all(
        cls,
        filter_by_stability: bool = False,
        env: Optional[str] = None
    ) -> Dict[str, Type[BaseModule]]:
        """
        List all registered module classes

        Args:
            filter_by_stability: If True, filter by stability level based on environment
            env: Environment override (production/staging/development/local)

        Returns:
            Dict of module_id -> module class
        """
        cls._ensure_discovered()
        if not filter_by_stability:
            return cls._modules.copy()

        current_env = env or get_current_env()
        result = {}

        for module_id, module_class in cls._modules.items():
            metadata = cls._metadata.get(module_id, {})
            stability_str = metadata.get('stability', 'stable')
            try:
                stability = StabilityLevel(stability_str)
            except ValueError:
                stability = StabilityLevel.STABLE

            if is_module_visible(stability, current_env):
                result[module_id] = module_class

        return result

    @classmethod
    @_synchronized
    def get_all_metadata(
        cls,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all module metadata (with optional filtering)

        Args:
            category: Filter by category (e.g., "browser", "data")
            tags: Filter by tags (module must have at least one matching tag)
            lang: Language code for localized fields
            filter_by_stability: If True, filter modules by stability level based on environment
            env: Environment override (production/staging/development/local), defaults to FLYTO_ENV

        Returns:
            Dict of module_id -> metadata
        """
        cls._ensure_discovered()
        result = {}
        current_env = env or get_current_env()

        for module_id, metadata in cls._metadata.items():
            # Filter by stability (environment-aware)
            if filter_by_stability:
                stability_str = metadata.get('stability', 'stable')
                try:
                    stability = StabilityLevel(stability_str)
                except ValueError:
                    stability = StabilityLevel.STABLE
                if not is_module_visible(stability, current_env):
                    continue

            # Filter by category
            if category and metadata.get('category') != category:
                continue

            # Filter by tags
            if tags:
                module_tags = metadata.get('tags', [])
                if not any(tag in module_tags for tag in tags):
                    continue

            # Localize fields
            localized_metadata = cls._localize_metadata(metadata, lang)
            result[module_id] = localized_metadata

        return result

    @classmethod
    @_synchronized
    def get_metadata(cls, module_id: str, lang: str = 'en') -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific module

        Args:
            module_id: Module identifier
            lang: Language code

        Returns:
            Localized metadata or None if not found
        """
        cls._ensure_discovered()
        metadata = cls._metadata.get(module_id)
        if not metadata:
            return None
        return cls._localize_metadata(metadata, lang)

    @classmethod
    def _localize_metadata(cls, metadata: Dict[str, Any], lang: str) -> Dict[str, Any]:
        """
        Localize metadata fields based on language

        Fields that support i18n: label, description, and nested labels in params_schema

        This is the public read boundary: every caller-facing metadata route —
        ``get_metadata``, ``get_all_metadata``, and so ``get_catalog`` and
        ``get_start_modules`` — hands back what this returns, so what this
        returns must be the caller's alone. The copy was one level deep, and the
        localisation below happens to copy ``params_schema`` and its parameter
        dicts a second time, which made the hole look closed while every other
        nested value stayed an alias to the live row: ``tags``,
        ``required_permissions``, ``can_receive_from``, ``can_connect_to``,
        ``presets``, and any dict nested more than two levels inside
        ``params_schema``. A caller only had to append to the list it was
        handed to change what the registry stores and what policy enforcement
        later reads — no lock held, no ``register()`` call, and the change
        outliving the caller because the row is process-global.

        So the row is copied deeply here, once, and the shallower copies below
        then operate on state nobody else can see. They are kept because they
        express what localisation replaces; they are no longer what makes the
        answer safe to hand out.
        """
        result = copy.deepcopy(dict(metadata))

        # Localize top-level fields
        if 'ui_label' in result:
            result['ui_label'] = get_localized_value(result['ui_label'], lang)
        if 'ui_description' in result:
            result['ui_description'] = get_localized_value(result['ui_description'], lang)

        # Localize params_schema labels
        if 'params_schema' in result:
            params = result['params_schema'].copy()
            for param_name, param_def in params.items():
                if isinstance(param_def, dict):
                    param_copy = param_def.copy()
                    if 'label' in param_copy:
                        param_copy['label'] = get_localized_value(param_copy['label'], lang)
                    if 'description' in param_copy:
                        param_copy['description'] = get_localized_value(param_copy['description'], lang)
                    if 'placeholder' in param_copy:
                        param_copy['placeholder'] = get_localized_value(param_copy['placeholder'], lang)

                    # Localize select options
                    if 'options' in param_copy and isinstance(param_copy['options'], list):
                        localized_options = []
                        for opt in param_copy['options']:
                            if isinstance(opt, dict) and 'label' in opt:
                                opt_copy = opt.copy()
                                opt_copy['label'] = get_localized_value(opt['label'], lang)
                                localized_options.append(opt_copy)
                            else:
                                localized_options.append(opt)
                        param_copy['options'] = localized_options

                    params[param_name] = param_copy
            result['params_schema'] = params

        return result

    @classmethod
    async def execute(cls, module_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute a module

        Args:
            module_id: Module identifier
            params: Parameters to pass to module
            context: Execution context (shared state, browser instance, etc.)

        Returns:
            Module execution result
        """
        # Deliberately *not* @_synchronized. The lookup below is, and that is the
        # only part that touches registry state; the rest constructs a module and
        # awaits arbitrary user work — network calls, browser drives, sleeps.
        # Holding the discovery lock across that await would let one slow module
        # block every catalog read in the process, and a module that re-entered
        # the registry from another task would find it already held.
        module_class = cls.get(module_id)
        module_instance = module_class(params, context)
        return await module_instance.execute()

    # ========================================
    # Plugin Discovery (Open Core Architecture)
    # ========================================

    @classmethod
    def discover_plugins(cls, force: bool = False) -> Dict[str, PluginInfo]:
        """
        Discover and load module plugins via entry_points.

        Uses Python's entry_points mechanism to find packages that provide
        flyto modules. Each plugin package should define:

            [project.entry-points."flyto.modules"]
            plugin_name = "package.module:register_all"

        The register_all function should call ModuleRegistry.register()
        for each module it provides.

        Discovery is idempotent and lossless. Calling it again — with ``force``,
        or after ``clear()`` — reproduces the same registry rather than a
        smaller one, and reports each plugin's size from the modules that plugin
        owns rather than from how much the registry happened to grow while it
        loaded.

        It is also serialised. Only one pass runs at a time per process, and a
        caller on another thread waits for the running pass and is answered from
        the finished registry rather than from the middle of one.

        Every route out of here hands back a *copy* of the plugin mapping, and
        that is part of the same guarantee rather than defensive habit. Handing
        out ``_plugins`` itself gives the caller a live view of process-global
        state: it keeps changing after the lock is released, so the mapping a
        caller holds can gain and lose plugins mid-iteration — the torn read the
        lock exists to prevent, smuggled out past it — and a caller that writes
        to what it was handed edits the registry's own record of what is
        installed without ever calling ``register()``. A copy is a fact about one
        instant, which is the only kind of answer a caller can safely keep.

        The copy is shallow, and the ``PluginInfo`` values in it are the objects
        in ``_plugins``, shared as they are from ``get_plugins()``. That is safe
        because ``PluginInfo`` is frozen: the one way left to reach registry
        state through the return value — editing a value rather than the mapping
        — raises instead. See ``PluginInfo``.

        Args:
            force: If True, reload all plugins even if already initialized

        Returns:
            Dict of plugin_name -> PluginInfo. A copy; mutating it does not
            change the registry, and it does not change underneath the caller.
        """
        if cls._discovery_thread == threading.get_ident():
            # Re-entered from inside a plugin's register_all — directly, or via
            # a catalog read that plugin made. A second pass would load every
            # plugin again underneath the first one; answer from what is known.
            # Checked before the lock rather than after: the lock is reentrant,
            # so acquiring it here would succeed and run that second pass.
            #
            # Copied like every other return path, and most necessary on this
            # one: the caller is plugin code, running inside a pass that is still
            # writing to _plugins.
            return cls._plugins.copy()

        with cls._discovery_lock:
            # Re-tested inside the lock. A thread that queued behind a first
            # discovery asked before there was an answer; by the time it holds
            # the lock there is one, and re-running the pass it just waited for
            # would defeat the point of waiting.
            if cls._initialized and not force:
                return cls._plugins.copy()
            return cls._discover_locked()

    @classmethod
    def _discover_locked(cls) -> Dict[str, PluginInfo]:
        """One discovery pass. Caller holds ``_discovery_lock``.

        Returns a copy of the plugin mapping, for the reason given on
        ``discover_plugins``: this is one of its return paths, reached by both
        ``discover_plugins(force=True)`` and ``refresh()``.
        """
        cls._discovering = True
        cls._discovery_thread = threading.get_ident()
        try:
            eps = _iter_entry_points()

            # Whether this pass follows a clear(), which is the cycle the
            # contribution record exists to rebuild. Read by _load_plugin, so it
            # is snapshotted here rather than recomputed once plugins have
            # started registering.
            cls._started_empty = cls._cleared

            # flyto-core's own modules, before any plugin has run. Refreshed on
            # every pass that has some, so an intentional unregistration is not
            # undone; kept when a pass starts empty, which is what a cleared
            # registry looks like.
            baseline = cls._capture(cls._first_party_ids())
            if baseline:
                cls._core_baseline = baseline

            for ep in eps:
                cls._load_plugin(ep)

            cls._forget_uninstalled_plugins(
                {getattr(ep, "name", "") for ep in eps}
            )

            if not cls._first_party_ids() and cls._core_baseline:
                # No entry point can re-register flyto-core's own modules, so a
                # cleared registry would stay short of them for the rest of the
                # process. Only replayed when the pass produced none at all.
                cls._restore(cls._core_baseline)

            cls._initialized = True
        finally:
            # Whatever happened, discovery does not hand the next registration
            # somebody else's identity.
            cls._loading_plugin = ""
            cls._discovering = False
            # Released before the lock is, so a thread waiting on the lock
            # cannot wake up still believing a pass is in flight.
            cls._discovery_thread = None
            cls._started_empty = False
            # The clear has been answered, whether or not the pass completed.
            cls._cleared = False
            # Belt and braces: _load_plugin unwinds these itself, but anything
            # raising after the loop would otherwise leave the next register()
            # recording into a pass that is over.
            cls._pass_registered = None
            cls._pass_touched = None
            cls._pass_displaced = {}

        return cls._plugins.copy()

    @classmethod
    def _load_plugin(cls, ep: Any) -> None:
        """Load one entry point, or leave it exactly as it was.

        Failure is the interesting case. A plugin that raises halfway through
        ``register_all`` has published a set of modules it never meant to
        publish, and the half it managed is not a smaller plugin — it is a
        plugin whose contents nobody has vouched for. So every row the failed
        pass disturbed is put back as it stood, anything it newly created is
        dropped, and its previously reported ``PluginInfo`` stands.

        "Disturbed" covers removals as well as writes. ``register_all`` is
        arbitrary code with the whole registry in reach, and a pass that deleted
        rows before raising is no more trustworthy than one that wrote them, so
        a failed load leaves the registry exactly as it found it either way.
        """
        name = getattr(ep, "name", "") or ""
        value = getattr(ep, "value", "") or ""

        remembered = cls._plugin_contributions.get(name, {})
        before_ids = set(cls._owned_by(name)) | set(remembered)
        prior_rows = cls._capture(before_ids)
        # The whole reported plugin set, not just this entry point's line in it.
        # A pass that reaches clear() drops every other plugin's PluginInfo as
        # well as its own, and restoring one name would leave the rest of the
        # pass's damage standing in what get_plugins() reports.
        prior_plugins = dict(cls._plugins)

        registered: Set[str] = set()
        touched: Set[str] = set()
        displaced: Dict[str, RegistryRow] = {}
        try:
            # The plugin's name is set for exactly the span of its own
            # registration, and cleared in `finally` so a plugin that raises
            # part-way through cannot leave its name attached to the next
            # plugin's modules — or, worse, to flyto-core's. The registration
            # record spans exactly the same window, for the same reason.
            register_func = ep.load()
            cls._loading_plugin = name
            cls._pass_registered = registered
            cls._pass_touched = touched
            cls._pass_displaced = displaced
            try:
                if callable(register_func):
                    register_func()
            finally:
                cls._loading_plugin = ""
                cls._pass_registered = None
                cls._pass_touched = None
                cls._pass_displaced = {}

            if registered:
                # The plugin spoke for itself this pass, so its answer is the
                # whole answer: a module it owned before and did not register
                # again is one it has stopped providing, and stays gone rather
                # than lingering as a row nothing installed still vouches for.
                # Only rows it still owns are dropped — one that another plugin
                # has since taken over is that plugin's to account for.
                for module_id in sorted(before_ids - registered):
                    if (cls._metadata.get(module_id) or {}).get('plugin', '') == name:
                        cls.unregister(module_id)
                owned = set(cls._owned_by(name))
                cls._plugin_contributions[name] = cls._capture(owned)
            elif remembered and cls._started_empty:
                # The plugin registered nothing into an empty registry. That is
                # what a clear/discover cycle looks like when a package
                # registers as an import side effect: the import is cached, so
                # ``register_all`` is a no-op and the modules an earlier pass
                # produced would simply be gone. Replay them so the cycle is
                # exact instead of lossy.
                cls._restore(remembered)
                owned = set(cls._owned_by(name))
            else:
                # Registered nothing into a registry that already had contents.
                # The call said nothing, so neither does this: a plugin that
                # legitimately provides nothing is left providing nothing
                # instead of being handed an earlier pass's modules, and one
                # whose rows are still standing keeps exactly those.
                owned = set(cls._owned_by(name))
                if name in cls._plugin_contributions:
                    # The record still has to track what is actually there, or a
                    # plugin emptied by unregistering its modules one at a time
                    # would be replayed back into existence by the next clear().
                    cls._plugin_contributions[name] = cls._capture(owned)

            try:
                pkg_version = get_version(value.split(':')[0].split('.')[0])
            except Exception:
                pkg_version = "unknown"

            cls._plugins[name] = PluginInfo(
                name=name,
                version=pkg_version,
                module_count=len(owned),
                entry_point=value,
            )
            cls._bump_generation()

            logger.info(
                f"Plugin loaded: {name} ({len(owned)} modules, v{pkg_version})"
            )

        except Exception as e:
            cls._loading_plugin = ""
            cls._pass_registered = None
            cls._pass_touched = None
            cls._pass_displaced = {}
            # Undo the failed pass exactly. Every id the plugin disturbed is
            # restored to the row that stood there beforehand, and only the ids
            # that held nothing are deleted. Two distinctions carry this:
            #
            # A module the failed registration overwrote — flyto-core's own, or
            # another plugin's — was stamped with this plugin's name on the way
            # past, so deleting everything the plugin appears to own would
            # destroy the displaced row instead of returning it to its owner.
            #
            # And the ids to put back are the ones the pass *touched*, not the
            # ones it registered. A plugin can also reach the registry by
            # deleting from it, and a row it unregistered leaves no trace in
            # what it owns, what it registered, or what it displaced by writing.
            # Rolling back only the writes would honour the deletions of a pass
            # nobody has vouched for — silently uninstalling flyto-core's own
            # modules, or another plugin's, on behalf of one that crashed.
            cls._restore(displaced, drop=touched - set(displaced))
            # Rows the plugin owned going in, for the case where the failure
            # took them out by some route other than being overwritten.
            cls._restore(prior_rows)
            cls._plugins.clear()
            cls._plugins.update(prior_plugins)
            cls._bump_generation()
            logger.error(f"Failed to load plugin {name}: {e}")

    @classmethod
    def _forget_uninstalled_plugins(cls, present: Any) -> None:
        """Drop what a plugin left behind once its entry point is gone.

        Only plugins discovery has actually loaded are candidates. A module
        stamped with an owner discovery has never seen is somebody's deliberate
        registration, not a leftover, and removing it would make an unrelated
        caller's registry shrink the first time anything read the catalog.
        """
        present = set(present)
        known = set(cls._plugins) | set(cls._plugin_contributions)
        for name in sorted(known - present):
            if not name:
                continue
            removed = cls._owned_by(name)
            for module_id in removed:
                cls.unregister(module_id)
            cls._plugins.pop(name, None)
            cls._plugin_contributions.pop(name, None)
            cls._bump_generation()
            logger.info(
                f"Plugin no longer installed: {name} ({len(removed)} modules removed)"
            )

    @classmethod
    @_synchronized
    def validate_connection_graph(cls) -> Dict[str, List[str]]:
        """
        Validate that all connection rules reference patterns that resolve
        to at least one registered module.

        Checks can_receive_from and can_connect_to for each module.
        Wildcard patterns (e.g., "browser.*") are checked against category prefixes.
        Special patterns ("*", "start", "end") are always valid.

        Returns:
            Dict with keys 'orphaned_receive' and 'orphaned_connect', each
            containing a list of "module_id: pattern" strings for patterns
            that don't match any registered module.
        """
        from ..connection_rules import matches_pattern

        cls._ensure_discovered()
        all_module_ids = list(cls._modules.keys())
        # Pre-compute categories for wildcard matching
        categories = {mid.split('.')[0] for mid in all_module_ids}
        special_patterns = {'*', 'start', 'end', 'start.*'}

        orphaned_receive: List[str] = []
        orphaned_connect: List[str] = []

        for module_id, metadata in cls._metadata.items():
            for pattern in metadata.get('can_receive_from', []):
                if pattern in special_patterns:
                    continue
                # Wildcard: check if category exists
                if pattern.endswith('.*'):
                    prefix = pattern[:-2]
                    if prefix not in categories:
                        orphaned_receive.append(f"{module_id}: {pattern}")
                    continue
                # Exact match: check if module exists
                if not any(matches_pattern(mid, pattern) for mid in all_module_ids):
                    orphaned_receive.append(f"{module_id}: {pattern}")

            for pattern in metadata.get('can_connect_to', []):
                if pattern in special_patterns:
                    continue
                if pattern.endswith('.*'):
                    prefix = pattern[:-2]
                    if prefix not in categories:
                        orphaned_connect.append(f"{module_id}: {pattern}")
                    continue
                if not any(matches_pattern(mid, pattern) for mid in all_module_ids):
                    orphaned_connect.append(f"{module_id}: {pattern}")

        result = {
            'orphaned_receive': orphaned_receive,
            'orphaned_connect': orphaned_connect,
        }

        total = len(orphaned_receive) + len(orphaned_connect)
        if total > 0:
            logger.warning(
                f"Connection graph validation: {total} orphaned pattern(s) found. "
                f"receive={len(orphaned_receive)}, connect={len(orphaned_connect)}"
            )
            for entry in orphaned_receive[:10]:
                logger.warning(f"  orphaned can_receive_from: {entry}")
            for entry in orphaned_connect[:10]:
                logger.warning(f"  orphaned can_connect_to: {entry}")
        else:
            logger.info("Connection graph validation: all patterns resolve OK")

        return result

    @classmethod
    def refresh(cls) -> Dict[str, PluginInfo]:
        """
        Refresh the registry by re-discovering all plugins.

        This is used for hot-update scenarios where packages have been
        updated via pip. Note: This does NOT reload already-imported
        Python modules. For true hot-reload, the worker process should
        be restarted.

        Returns:
            Dict of plugin_name -> PluginInfo, copied by ``discover_plugins``
            below. A refresh is the case that most needs it: the caller asked
            for the registry to be rebuilt, so a live mapping handed back here
            would be one the *next* refresh empties under them.
        """
        logger.info("Refreshing module registry...")

        with cls._discovery_lock:
            # Held across both halves. Between them the registry is empty and
            # _initialized is False, which is precisely the state a reader on
            # another thread would rebuild from; holding the lock makes the
            # refresh one step from the outside instead of two.
            #
            # Reentrant on purpose: a refresh from inside a plugin's
            # register_all already owns this lock, and discover_plugins below
            # returns immediately for that thread rather than nesting a pass.

            # Clear existing state — including the loading owner, which clear()
            # resets so a refresh cannot inherit a half-finished registration.
            cls.clear()

            # Re-discover plugins
            return cls.discover_plugins(force=True)

    @classmethod
    @_synchronized
    def capability_snapshot(cls) -> Dict[str, Any]:
        """Metadata, capabilities and plugins as they stood at one instant.

        The three reads a capability manifest needs are individually safe —
        ``_synchronized`` sees to that — but calling them one after another is
        not. Each drops the lock on the way out, so a ``refresh()`` landing in
        either gap yields a document whose module list came from before the
        rebuild and whose plugin list came from after: a registry state that
        never existed, and one whose hash therefore names nothing. This is the
        same tear ``_synchronized`` describes, moved up one level from a single
        read to a group of them.

        Holding the lock across all three closes the gaps. The nested calls
        re-enter the ``RLock`` this thread already owns, which is exactly the
        re-entry that decorator was made reentrant for.

        ``filter_by_stability=False`` is deliberate: the stability filter
        consults ``FLYTO_ENV``, so leaving it on would make the snapshot — and
        any hash taken over it — depend on the environment rather than on what
        is installed.

        ``generation`` is read under the same hold as the three registry
        views, so it is the mutation counter *for this exact state* rather than
        for whatever the registry became afterwards. That is what lets a
        caller order two snapshots taken by different threads: the higher
        generation is unambiguously the later state, so a slow build cannot
        publish an older document over a newer one. It is process-local and
        must not be copied into any document that is compared across hosts.

        Returns a dict with ``metadata``, ``capabilities``, ``plugins`` (as
        ``PluginInfo``), ``registry_version``, and ``generation``. Every value
        is already a copy owned by the caller.
        """
        cls._ensure_discovered()
        return {
            "registry_version": REGISTRY_VERSION,
            "generation": cls._generation,
            "metadata": cls.get_all_metadata(filter_by_stability=False),
            "capabilities": cls.capabilities(),
            "plugins": cls.get_plugins(),
        }

    @classmethod
    @_synchronized
    def get_snapshot(cls) -> RegistrySnapshot:
        """
        Get a snapshot of current registry state.

        Used for execution version binding - each workflow execution
        should record the registry snapshot to ensure checkpoint/resume
        uses the same module versions.

        Returns:
            RegistrySnapshot with version info and module hash
        """
        # Ensure plugins are discovered
        cls._ensure_discovered()

        # Build plugins version dict
        plugins = {name: info.version for name, info in cls._plugins.items()}

        # Calculate modules hash (for detecting changes)
        module_ids = sorted(cls._modules.keys())
        hash_input = "|".join(module_ids)
        modules_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

        return RegistrySnapshot(
            registry_version=REGISTRY_VERSION,
            plugins=plugins,
            module_count=len(cls._modules),
            modules_hash=modules_hash
        )

    @classmethod
    @_synchronized
    def get_plugins(cls) -> Dict[str, PluginInfo]:
        """Get information about all loaded plugins"""
        cls._ensure_discovered()
        return cls._plugins.copy()

    @classmethod
    @_synchronized
    def is_plugin_loaded(cls, plugin_name: str) -> bool:
        """Check if a specific plugin is loaded"""
        cls._ensure_discovered()
        return plugin_name in cls._plugins

    @classmethod
    @_synchronized
    def get_plugin_modules(cls, plugin_name: str) -> List[str]:
        """
        Get list of module IDs provided by a specific plugin.

        Note: This requires modules to have 'plugin' in their metadata.
        """
        cls._ensure_discovered()
        return cls._owned_by(plugin_name)

    # ========================================
    # Catalog Service (Frontend API)
    # ========================================

    @classmethod
    @_synchronized
    def get_catalog(
        cls,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None,
        include_internal: bool = False,
    ) -> Dict[str, Any]:
        """
        Get module catalog grouped by tier for frontend display.

        Returns a structured catalog optimized for node picker dialogs:
        - Modules grouped by tier (featured, standard, toolkit)
        - Within each tier, grouped by category
        - Sorted by tier display order

        Args:
            lang: Language code for localization
            filter_by_stability: Filter modules by stability/environment
            env: Environment override
            include_internal: Include INTERNAL tier modules (default False)

        Returns:
            {
                "tiers": [
                    {
                        "id": "featured",
                        "label": "Featured",
                        "display_order": 1,
                        "categories": [
                            {
                                "id": "browser",
                                "label": "Browser",
                                "modules": [...]
                            }
                        ]
                    },
                    ...
                ],
                "total_count": 305,
                "tier_counts": {"featured": 10, "standard": 200, "toolkit": 95}
            }
        """
        # Get all visible metadata
        all_metadata = cls.get_all_metadata(
            lang=lang,
            filter_by_stability=filter_by_stability,
            env=env,
        )

        # Group by tier
        tier_groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        tier_counts: Dict[str, int] = {}

        for _module_id, metadata in all_metadata.items():
            tier_value = metadata.get('tier', 'standard')

            # Skip internal unless explicitly requested
            if tier_value == 'internal' and not include_internal:
                continue

            category = metadata.get('category', 'other')

            if tier_value not in tier_groups:
                tier_groups[tier_value] = {}
                tier_counts[tier_value] = 0

            if category not in tier_groups[tier_value]:
                tier_groups[tier_value][category] = []

            tier_groups[tier_value][category].append(metadata)
            tier_counts[tier_value] += 1

        # Build structured response
        tiers = []
        for tier_enum in ModuleTier:
            tier_value = tier_enum.value
            if tier_value not in tier_groups:
                continue
            if tier_value == 'internal' and not include_internal:
                continue

            categories = []
            for cat_id, modules in sorted(tier_groups[tier_value].items()):
                categories.append({
                    "id": cat_id,
                    "label": cat_id.replace('_', ' ').title(),
                    "modules": sorted(modules, key=lambda m: m.get('ui_label', m.get('module_id', ''))),
                })

            tiers.append({
                "id": tier_value,
                "label": tier_value.replace('_', ' ').title(),
                "display_order": TIER_DISPLAY_ORDER.get(tier_enum, 99),
                "categories": categories,
            })

        # Sort tiers by display order
        tiers.sort(key=lambda t: t['display_order'])

        return {
            "tiers": tiers,
            "total_count": sum(tier_counts.values()),
            "tier_counts": tier_counts,
        }

    @classmethod
    @_synchronized
    def get_start_modules(
        cls,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get modules that can be used as workflow start nodes.

        Filters catalog to only include modules where can_be_start=True.

        Args:
            lang: Language code
            filter_by_stability: Filter by stability level
            env: Environment override

        Returns:
            Same structure as get_catalog() but filtered
        """
        all_metadata = cls.get_all_metadata(
            lang=lang,
            filter_by_stability=filter_by_stability,
            env=env,
        )

        # Group by tier, only include start-capable modules
        tier_groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        tier_counts: Dict[str, int] = {}

        for _module_id, metadata in all_metadata.items():
            # Skip non-start modules
            if not metadata.get('can_be_start', False):
                continue

            tier_value = metadata.get('tier', 'standard')
            # Skip internal for start modules
            if tier_value == 'internal':
                continue

            category = metadata.get('category', 'other')

            if tier_value not in tier_groups:
                tier_groups[tier_value] = {}
                tier_counts[tier_value] = 0

            if category not in tier_groups[tier_value]:
                tier_groups[tier_value][category] = []

            tier_groups[tier_value][category].append(metadata)
            tier_counts[tier_value] += 1

        # Build structured response
        tiers = []
        for tier_enum in ModuleTier:
            tier_value = tier_enum.value
            if tier_value not in tier_groups:
                continue

            categories = []
            for cat_id, modules in sorted(tier_groups[tier_value].items()):
                categories.append({
                    "id": cat_id,
                    "label": cat_id.replace('_', ' ').title(),
                    "modules": sorted(modules, key=lambda m: m.get('ui_label', m.get('module_id', ''))),
                })

            tiers.append({
                "id": tier_value,
                "label": tier_value.replace('_', ' ').title(),
                "display_order": TIER_DISPLAY_ORDER.get(tier_enum, 99),
                "categories": categories,
            })

        tiers.sort(key=lambda t: t['display_order'])

        return {
            "tiers": tiers,
            "total_count": sum(tier_counts.values()),
            "tier_counts": tier_counts,
        }
