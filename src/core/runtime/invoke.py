# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Runtime Invoker

Abstraction layer for module invocation.
Phase 0: Delegates to in-process legacy modules.
Phase 1+: Can delegate to subprocess plugins.
Phase 2: Dual-track routing (prefer plugin, fallback to legacy).
"""

import logging
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from .browser_session import BrowserSessionManager, get_browser_manager
from .exceptions import PluginNotFoundError, PluginUnhealthyError
from .routing import ModuleRouter, RoutingDecision, RoutingResult, get_router
from .types import InvokeRequest, InvokeResponse

if TYPE_CHECKING:
    from .manager import PluginManager

logger = logging.getLogger(__name__)


class _MalformedManifestError(Exception):
    """A manifest declaration whose *shape* cannot carry a policy answer.

    Distinct from a read that throws: nothing raised, the data is simply not the
    kind of data the gate knows how to check. ``steps: "scan"`` iterates into
    characters, ``permissions: "shell.execute"`` iterates into letters, and a
    permission that is not a string is not a permission — each one used to walk
    through the gate as "declared nothing dangerous", which is the one answer a
    manifest we cannot read must never produce.

    Carries a structural label only. The offending value is plugin-supplied and
    may not even be renderable, so it is never interpolated, logged, or returned.
    """


class RuntimeInvoker:
    """
    Abstraction layer for module invocation.

    Phase 0: Delegates to in-process modules.
    Phase 1+: Can delegate to subprocess plugins.
    Phase 2: Dual-track routing with fallback support.

    This class provides a unified interface that allows the executor
    to invoke modules without knowing whether they are in-process
    legacy modules or subprocess plugins.
    """

    def __init__(
        self,
        plugin_manager: Optional["PluginManager"] = None,
        router: Optional[ModuleRouter] = None,
        browser_manager: Optional[BrowserSessionManager] = None,
    ):
        """
        Initialize the runtime invoker.

        Args:
            plugin_manager: Optional PluginManager for subprocess plugins
            router: Optional ModuleRouter for routing decisions
            browser_manager: Optional BrowserSessionManager for browser sharing
        """
        self._plugin_manager = plugin_manager
        self._router = router or get_router()
        self._browser_manager = browser_manager
        self._legacy_modules_loaded = False

    def set_browser_manager(self, manager: BrowserSessionManager):
        """Set the browser session manager."""
        self._browser_manager = manager

    async def _prepare_plugin_context(
        self,
        context: Dict[str, Any],
        execution_id: Optional[str] = None,
        plugin_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare context for plugin invocation.

        Transforms non-serializable objects (like browser instances) into
        serializable references (like WebSocket endpoints).

        Security: Browser sessions now require authentication tokens.

        Args:
            context: Original execution context
            execution_id: Optional execution ID for session naming
            plugin_id: Plugin ID for browser session authorization

        Returns:
            Plugin-safe context dictionary
        """
        plugin_context = dict(context)

        # Check if context contains a browser object that needs to be converted
        # to a WebSocket endpoint for cross-process access
        browser = context.get("browser")
        if browser is not None:
            # If browser is already a string (ws_endpoint), use it directly
            if isinstance(browser, str):
                plugin_context["browser_ws_endpoint"] = browser
            # If browser has ws_endpoint attribute (Playwright Browser)
            elif hasattr(browser, "ws_endpoint"):
                plugin_context["browser_ws_endpoint"] = browser.ws_endpoint
                # Remove the non-serializable browser object
                plugin_context.pop("browser", None)
            # Otherwise, create a shared session
            else:
                try:
                    session_id = f"exec-{execution_id}" if execution_id else "default"
                    manager = self._browser_manager or get_browser_manager()
                    # Security: get_or_create_session now returns dict with token
                    session_info = await manager.get_or_create_session(
                        session_id=session_id,
                        headless=True,
                        owner_plugin=plugin_id,
                    )
                    plugin_context["browser_ws_endpoint"] = session_info["ws_endpoint"]
                    plugin_context["browser_session_token"] = session_info["session_token"]
                    plugin_context.pop("browser", None)
                except Exception as e:
                    logger.warning(f"Could not create browser session: {e}")

        # If there's already a browser_ws_endpoint in context, ensure it's passed through
        if "browser_ws_endpoint" in context:
            plugin_context["browser_ws_endpoint"] = context["browser_ws_endpoint"]
        if "browser_session_token" in context:
            plugin_context["browser_session_token"] = context["browser_session_token"]

        return plugin_context

    def set_plugin_manager(self, manager: "PluginManager"):
        """Set the plugin manager for subprocess plugins."""
        self._plugin_manager = manager
        # Update router with available plugins
        if manager:
            self._router.set_available_plugins(self._routable_plugin_ids(manager))

    @staticmethod
    def _read_field(source: Any, *names: str, default: Any = None) -> Any:
        """Read the first present field of ``names`` off a mapping or an object.

        Runtime data crossing this module comes in two shapes and both are real:
        ``PluginManifest.steps`` entries are plain dicts parsed straight from
        manifest JSON, while the policy tests (and any future typed manifest)
        hand over attribute-style objects. Reading only one shape is how the
        gate ends up silently seeing no permissions on a real manifest.
        """
        if isinstance(source, Mapping):
            for name in names:
                if name in source:
                    return source[name]
            return default
        for name in names:
            value = getattr(source, name, None)
            if value is not None:
                return value
        return default

    @classmethod
    def _plugin_id_of(cls, entry: Any) -> str:
        """Coerce one plugin listing entry into its id string.

        ``PluginManager.list_plugins()`` yields *status records* keyed
        ``pluginId``, not ids. ``list_available_plugins()`` yields bare strings.
        Both must reduce to the same thing before the router can hold them.

        May raise: every step here runs against data a plugin supplied, and an
        id whose ``__str__`` or ``pluginId`` property throws is a real listing
        entry, not a programming error. Callers must treat a raise as "this one
        entry is unusable" — see ``_routable_plugin_ids``.
        """
        if isinstance(entry, str):
            return entry.strip()
        if entry is None:
            return ""
        value = cls._read_field(entry, "pluginId", "plugin_id", "id", "name", default="")
        return str(value).strip() if value else ""

    @classmethod
    def _routable_plugin_ids(cls, manager: Any) -> Set[str]:
        """Plugin ids a manager exposes, as hashable strings the router accepts.

        The previous ``set(manager.list_plugins())`` raised ``TypeError:
        unhashable type: 'dict'`` against the real ``PluginManager``, so wiring a
        manager in at all was impossible. Discovered plugins
        (``list_available_plugins``) are preferred because they are already
        plain ids and cover plugins not yet loaded; loaded status records are
        still folded in so a manager exposing only ``list_plugins`` still routes.
        Collected in order and de-duplicated so the result is deterministic
        regardless of which sources a given manager implements.

        Failure is per-entry, not per-manager. A listing is plugin-supplied
        data, so one entry whose id cannot even be rendered — a ``__str__`` that
        throws, a ``pluginId`` property that raises — must cost that entry its
        routing slot and nothing else. Letting it out of here would abort
        ``set_plugin_manager`` and leave the invoker holding a manager whose
        plugins the router never learned about, which is the failure this whole
        helper exists to prevent.
        """
        ids: List[str] = []
        for source in ("list_available_plugins", "list_plugins"):
            lister = getattr(manager, source, None)
            if not callable(lister):
                continue
            try:
                entries = lister() or []
            except Exception as exc:  # noqa: BLE001 - one bad lister must not break wiring
                logger.warning("Plugin manager %s() failed: %s", source, exc)
                continue
            try:
                entries = list(entries)
            except Exception as exc:  # noqa: BLE001 - an unusable listing is not a wiring failure
                logger.warning("Plugin manager %s() is not iterable: %s", source, exc)
                continue
            for position, entry in enumerate(entries):
                try:
                    plugin_id = cls._plugin_id_of(entry)
                except Exception as exc:  # noqa: BLE001 - one bad entry must not break wiring
                    # Positional, because the entry is exactly the thing that
                    # cannot be rendered — %r on it would raise again here.
                    logger.warning(
                        "Plugin manager %s() entry at index %d is unreadable "
                        "and was skipped: %s",
                        source,
                        position,
                        exc,
                    )
                    continue
                if plugin_id and plugin_id not in ids:
                    ids.append(plugin_id)
        return set(ids)

    def _ensure_legacy_modules_loaded(self):
        """Ensure legacy module availability is set in router."""
        if self._legacy_modules_loaded:
            return

        try:
            from ..modules.registry import ModuleRegistry
            available = set(ModuleRegistry.list_all())
            self._router.set_available_legacy(available)
            self._legacy_modules_loaded = True
            logger.debug(f"Loaded {len(available)} legacy modules for routing")
        except ImportError:
            logger.warning("ModuleRegistry not available")
            self._legacy_modules_loaded = True

    async def invoke(
        self,
        module_id: str,
        step_id: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
        timeout_ms: int = 0,
        execution_id: Optional[str] = None,
        step_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a module step.

        Uses dual-track routing to determine whether to use plugin or legacy:
        1. Route decision based on config (prefer plugin by default)
        2. Try primary handler
        3. If fails and fallback enabled, try fallback handler

        Args:
            module_id: Plugin ID (e.g., "flyto-official/database" or legacy "database")
            step_id: Step within plugin (e.g., "query")
            input_data: Input JSON matching inputSchema
            config: Static configuration
            context: Execution context (secrets, permissions, etc.)
            timeout_ms: Timeout in milliseconds (0 = no timeout)
            execution_id: Optional execution ID for tracing
            step_run_id: Optional step run ID for tracing

        Returns:
            {"ok": True, "data": {...}} or {"ok": False, "error": {...}}
        """
        start_time = time.time()

        # Ensure legacy modules are loaded for routing
        self._ensure_legacy_modules_loaded()

        # Resolve legacy module ID for routing
        legacy_module_id = self._resolve_legacy_module_id(module_id, step_id)

        # Get routing decision
        routing = self._router.route(legacy_module_id)

        # SECURITY: the same gate every in-process module passes through at
        # BaseModule.run. Without it this path is a way around the module
        # denylist: a step naming an id the registry does not know falls
        # through to here, and a plugin claiming that id would run it in a
        # subprocess that the chokepoint never sees.
        #
        # Routing has to happen first because it resolves a legacy spelling
        # such as ``database.query`` to the actual plugin identity
        # ``flyto-official/database``. Looking up the manifest under the
        # caller's legacy spelling returns no manifest, silently drops the
        # plugin's required_permissions, and then executes the resolved plugin.
        # The policy still runs before either handler, and the resolved plugin
        # id is retained even when it is only the possible fallback.
        policy_plugin_id = routing.plugin_id or module_id
        denial = self._policy_denial(legacy_module_id, policy_plugin_id, step_id)
        if denial:
            return self._error_response("MODULE_POLICY_DENIED", denial, start_time)

        logger.debug(
            f"Routing decision for {legacy_module_id}: "
            f"decision={routing.decision.value}, use_plugin={routing.use_plugin}, "
            f"fallback_available={routing.fallback_available}"
        )

        # Handle no handler case
        if routing.decision == RoutingDecision.NO_HANDLER:
            return self._error_response(
                "MODULE_NOT_FOUND",
                f"No handler available for {legacy_module_id}: {routing.reason}",
                start_time,
            )

        # Try primary handler
        try:
            if routing.use_plugin:
                result = await self._invoke_plugin(
                    plugin_id=routing.plugin_id,
                    step_id=step_id or legacy_module_id.split(".")[-1],
                    input_data=input_data,
                    config=config,
                    context=context,
                    timeout_ms=timeout_ms,
                    execution_id=execution_id,
                )
            else:
                result = await self._invoke_legacy(
                    module_id=legacy_module_id,
                    input_data=input_data,
                    config=config,
                    context=context,
                )

            # Check if result indicates success
            if result.get("ok", False):
                return self._normalize_response(result, start_time)

            # Primary failed - try fallback if available
            if routing.fallback_available:
                logger.info(
                    f"Primary handler failed for {legacy_module_id}, "
                    f"trying fallback (was_plugin={routing.use_plugin})"
                )
                return await self._try_fallback(
                    routing=routing,
                    legacy_module_id=legacy_module_id,
                    step_id=step_id,
                    input_data=input_data,
                    config=config,
                    context=context,
                    timeout_ms=timeout_ms,
                    execution_id=execution_id,
                    start_time=start_time,
                    primary_error=result.get("error"),
                )

            # No fallback - return the error
            return self._normalize_response(result, start_time)

        except (PluginNotFoundError, PluginUnhealthyError) as e:
            # Plugin-specific errors - try fallback
            if routing.fallback_available:
                logger.info(f"Plugin error for {legacy_module_id}: {e}, trying fallback")
                return await self._try_fallback(
                    routing=routing,
                    legacy_module_id=legacy_module_id,
                    step_id=step_id,
                    input_data=input_data,
                    config=config,
                    context=context,
                    timeout_ms=timeout_ms,
                    execution_id=execution_id,
                    start_time=start_time,
                    primary_error={"code": type(e).__name__, "message": str(e)},
                )
            raise

        except Exception as e:
            # Unexpected error - try fallback if available
            if routing.fallback_available:
                logger.warning(
                    f"Unexpected error for {legacy_module_id}: {e}, trying fallback",
                    exc_info=True,
                )
                return await self._try_fallback(
                    routing=routing,
                    legacy_module_id=legacy_module_id,
                    step_id=step_id,
                    input_data=input_data,
                    config=config,
                    context=context,
                    timeout_ms=timeout_ms,
                    execution_id=execution_id,
                    start_time=start_time,
                    primary_error={"code": "EXECUTION_ERROR", "message": str(e)},
                )

            logger.error(f"Module invocation failed: {e}", exc_info=True)
            return self._error_response("EXECUTION_ERROR", str(e), start_time)

    def _policy_denial(self, legacy_module_id: str, plugin_id: str, step_id: str) -> str:
        """Why policy refuses this step, or empty when it does not.

        Returns a reason rather than raising because ``invoke`` answers with an
        envelope; the caller already treats ``ok: False`` as a stop, so this
        still fails closed.

        ``required_permissions`` come from the plugin's own manifest when one is
        loaded. A plugin that declares none simply declares none — the module
        filter and the plugin allow/deny list still apply, so an unmanifested or
        lying plugin cannot use silence to reach a denied module id.

        The plugin identity defaults to the id the caller actually asked for.
        Blanking it on a manifest miss made every unmanifested plugin step look
        like one of flyto-core's own modules, and ``is_plugin_allowed("")`` is
        unconditionally true — so the allow/deny list, whose whole job is to be
        keyed on that identity, stopped applying exactly where it mattered.
        """
        from ..module_policy import ModulePolicyError, enforce_module_policy

        required: Optional[list] = None
        plugin_name = str(plugin_id or "")
        manager = self._plugin_manager
        if manager is not None:
            try:
                manifest = manager.get_manifest(plugin_id)
            except Exception as exc:  # noqa: BLE001 - a manifest lookup must not gate-fail open
                # Fail closed and say so. Continuing with "no manifest" would
                # decide the permission question by guessing, and the guess it
                # makes is always "allowed".
                logger.warning(
                    "Manifest lookup failed for plugin %r: %s",
                    plugin_id,
                    exc,
                    exc_info=True,
                )
                return self._manifest_denial(
                    legacy_module_id, plugin_name, "the manifest lookup"
                )
            if manifest is not None:
                try:
                    plugin_name, required = self._manifest_step_policy(
                        manifest, step_id, plugin_name
                    )
                except _MalformedManifestError as exc:
                    # A declaration that is the wrong *shape*, as opposed to one
                    # that raised while being read. Same verdict for the same
                    # reason: permissions we cannot enumerate are permissions we
                    # cannot check. Only the structural label is logged — the
                    # value itself is plugin-supplied and may be unrenderable.
                    logger.warning(
                        "Malformed capability manifest for plugin %r step %r: %s",
                        plugin_id,
                        step_id,
                        exc,
                    )
                    return self._manifest_denial(
                        legacy_module_id, plugin_name, "validating the capability manifest"
                    )
                except Exception as exc:  # noqa: BLE001 - a bad manifest must not gate-fail open
                    # Reading the manifest can fail on its own, after the lookup
                    # succeeded: ``steps`` may not be iterable, a step id or a
                    # declared permission may be an object whose ``__str__``
                    # raises. Every one of those is plugin-supplied data, and
                    # every one of them used to escape this method uncaught —
                    # ``_policy_denial`` runs *before* ``invoke``'s try block, so
                    # the exception left ``invoke`` entirely and the step was
                    # neither allowed nor denied, just crashed, with our
                    # traceback attached. Deny instead: a manifest we cannot read
                    # is a manifest whose permissions we cannot check.
                    #
                    # ``plugin_name`` is deliberately read here and not from the
                    # partial result — the tuple only binds on a clean return, so
                    # a half-read manifest leaves the identity at the id the
                    # caller asked for rather than at whatever the manifest was
                    # mid-way through claiming.
                    logger.warning(
                        "Manifest field read failed for plugin %r step %r: %s",
                        plugin_id,
                        step_id,
                        exc,
                        exc_info=True,
                    )
                    return self._manifest_denial(
                        legacy_module_id, plugin_name, "reading the capability manifest"
                    )

        try:
            enforce_module_policy(legacy_module_id, required, plugin=plugin_name)
        except ModulePolicyError as exc:
            return str(exc)
        return ""

    @staticmethod
    def _manifest_denial(legacy_module_id: str, plugin_name: str, what_failed: str) -> str:
        """The denial text for a manifest the gate could not evaluate.

        Says *which* read failed and never why. Whatever made it fail is our
        internal state — a store path, a connection string, a driver traceback,
        an object repr carrying a credential — and the caller reading this
        envelope may be the plugin author or an MCP client, so interpolating the
        cause would turn a policy denial into a disclosure channel. The operator
        gets the whole cause from the log, keyed by the same plugin id the
        denial already names, which is also why the denial must keep naming it:
        a denial that cannot identify the plugin cannot be acted on.
        """
        return (
            f"Module '{legacy_module_id}' cannot be checked against "
            f"capability policy: {what_failed} for plugin "
            f"'{plugin_name}' failed. See the server log for the cause."
        )

    @classmethod
    def _manifest_step_policy(
        cls,
        manifest: Any,
        step_id: str,
        fallback_name: str,
    ) -> tuple:
        """``(plugin_name, required_permissions)`` declared for ``step_id``.

        ``required`` stays ``None`` when the manifest declares no matching step,
        which is distinct from ``[]`` — a step that matched and declared nothing.

        Shape is checked before content, and anything that is not the declared
        shape raises ``_MalformedManifestError`` rather than being coerced. Coercion
        is what made these fail open: ``steps: "scan"`` is iterable, so the old
        walk read its characters, matched no step and reported "nothing
        declared"; ``permissions: "shell.execute"`` likewise decomposed into
        letters, none of which is a dangerous permission; and a non-string
        permission stringified into something the dangerous set could never
        contain. In all three the gate answered "allowed" about a declaration it
        had not actually read.

        Strings are rejected wholesale rather than wrapped into a one-element
        list on purpose. A manifest that spells a list as a scalar is a manifest
        whose author's intent we are guessing at, and the safe guess and the
        convenient guess are not the same one.

        May raise: every read touches plugin-supplied data. Callers must treat a
        raise as "policy cannot be evaluated" — never as "nothing declared".
        """
        declared = cls._read_field(manifest, "id", default="")
        plugin_name = (str(declared) if declared else "") or fallback_name

        wanted = str(step_id)
        for step in cls._require_sequence(
            cls._read_field(manifest, "steps", default=None), "steps"
        ):
            # A step must be something a field can be read off. A bare scalar is
            # not, and letting it through means walking a string's characters.
            if not isinstance(step, Mapping) and not hasattr(step, "id"):
                raise _MalformedManifestError("a step entry is not a step object")
            if str(cls._read_field(step, "id", default="")) != wanted:
                continue
            permissions = cls._require_sequence(
                cls._read_field(
                    step,
                    "required_permissions",
                    "requiredPermissions",
                    "permissions",
                    default=None,
                ),
                "permissions",
            )
            for permission in permissions:
                # ``enforce_module_policy`` tests each of these for membership in
                # a set and interpolates the ungranted ones into a message the
                # caller reads. A non-string is unhashable often enough to raise
                # out of the gate, and renders itself into that message when it
                # is not. Neither belongs past this boundary.
                if not isinstance(permission, str):
                    raise _MalformedManifestError("a declared permission is not a string")
            return plugin_name, list(permissions)
        return plugin_name, None

    @staticmethod
    def _require_sequence(value: Any, what: str) -> Sequence:
        """``value`` as a real list-like, or ``_MalformedManifestError``.

        ``None`` means undeclared and yields an empty sequence — silence is a
        legitimate manifest, and the module filter and plugin allow/deny list
        still apply to it. Everything else must be an actual sequence that is
        not a string, bytes, or mapping: those three are iterable but iterate
        into something other than their elements, which is exactly how a scalar
        declaration used to be read as an empty one.
        """
        if value is None:
            return ()
        if isinstance(value, (str, bytes, bytearray, Mapping)):
            raise _MalformedManifestError(f"{what} is a scalar, not a list")
        if not isinstance(value, Sequence):
            raise _MalformedManifestError(f"{what} is not a list")
        return value

    async def _invoke_plugin(
        self,
        plugin_id: str,
        step_id: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
        timeout_ms: int = 0,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke via plugin subprocess."""
        if not self._plugin_manager:
            raise PluginNotFoundError(plugin_id, step_id)

        logger.debug(f"Invoking plugin: {plugin_id}.{step_id}")

        # Prepare context for plugin (convert browser objects to ws_endpoints)
        # Security: Pass plugin_id for browser session authorization
        plugin_context = await self._prepare_plugin_context(
            context, execution_id, plugin_id=plugin_id
        )

        result = await self._plugin_manager.invoke(
            plugin_id=plugin_id,
            step=step_id,
            input_data=input_data,
            config=config,
            context=plugin_context,
            timeout_ms=timeout_ms,
        )

        return result

    async def _invoke_legacy(
        self,
        module_id: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Invoke via legacy in-process module."""
        logger.debug(f"Invoking legacy module: {module_id}")

        from ..modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)

        if not module_class:
            raise PluginNotFoundError(module_id, "")

        # Merge input_data and config as params
        params = {**input_data, **config}

        # Create module instance
        module_instance = module_class(params, context)

        # Execute module
        result = await module_instance.run()

        return result

    async def _try_fallback(
        self,
        routing: RoutingResult,
        legacy_module_id: str,
        step_id: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any],
        timeout_ms: int,
        execution_id: Optional[str],
        start_time: float,
        primary_error: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Try fallback handler after primary failed."""
        try:
            if routing.use_plugin:
                # Primary was plugin, fallback to legacy
                logger.info(f"Falling back to legacy for {legacy_module_id}")
                result = await self._invoke_legacy(
                    module_id=legacy_module_id,
                    input_data=input_data,
                    config=config,
                    context=context,
                )
            else:
                # Primary was legacy, fallback to plugin
                logger.info(f"Falling back to plugin for {routing.plugin_id}")
                result = await self._invoke_plugin(
                    plugin_id=routing.plugin_id,
                    step_id=step_id or legacy_module_id.split(".")[-1],
                    input_data=input_data,
                    config=config,
                    context=context,
                    timeout_ms=timeout_ms,
                    execution_id=execution_id,
                )

            response = self._normalize_response(result, start_time)

            # Add fallback metadata
            if "metrics" not in response:
                response["metrics"] = {}
            response["metrics"]["usedFallback"] = True
            response["metrics"]["primaryError"] = primary_error

            return response

        except Exception as e:
            logger.error(f"Fallback also failed for {legacy_module_id}: {e}")
            return self._error_response(
                "FALLBACK_FAILED",
                f"Both primary and fallback handlers failed. Primary: {primary_error}, Fallback: {e}",
                start_time,
            )

    def _resolve_legacy_module_id(self, plugin_id: str, step_id: str) -> str:
        """
        Map new plugin/step format to legacy module_id.

        Examples:
            ("flyto-official/database", "query") -> "database.query"
            ("flyto-official/llm", "chat") -> "llm.chat"
            ("database", "query") -> "database.query"
            ("llm.chat", "") -> "llm.chat"  (already legacy format)
        """
        # If step_id is empty or plugin_id already contains dot, use as-is
        if not step_id or "." in plugin_id:
            # Already in legacy format (e.g., "database.query")
            return plugin_id if not step_id else f"{plugin_id}.{step_id}"

        # Remove publisher prefix if present
        # e.g., "flyto-official/database" -> "database"
        plugin_name = plugin_id.split("/")[-1] if "/" in plugin_id else plugin_id

        # Remove any "flyto-official_" or similar prefix
        # e.g., "flyto-official_database" -> "database"
        if "_" in plugin_name and plugin_name.startswith("flyto"):
            parts = plugin_name.split("_")
            if len(parts) >= 2:
                plugin_name = parts[-1]

        return f"{plugin_name}.{step_id}"

    def _normalize_response(
        self,
        result: Any,
        start_time: float,
    ) -> Dict[str, Any]:
        """Ensure response matches standard format."""
        duration_ms = int((time.time() - start_time) * 1000)

        if result is None:
            return {
                "ok": True,
                "data": None,
                "metrics": {"durationMs": duration_ms, "costPointsUsed": 0},
            }

        if isinstance(result, dict):
            # Already has ok field - ensure metrics
            if "ok" in result:
                if "metrics" not in result:
                    result["metrics"] = {"durationMs": duration_ms, "costPointsUsed": 0}
                elif "durationMs" not in result["metrics"]:
                    result["metrics"]["durationMs"] = duration_ms
                return result
            else:
                # Raw data dict - wrap it
                return {
                    "ok": True,
                    "data": result,
                    "metrics": {"durationMs": duration_ms, "costPointsUsed": 0},
                }
        else:
            # Non-dict result - wrap it
            return {
                "ok": True,
                "data": result,
                "metrics": {"durationMs": duration_ms, "costPointsUsed": 0},
            }

    def _error_response(
        self,
        code: str,
        message: str,
        start_time: float,
        retryable: bool = False,
    ) -> Dict[str, Any]:
        """Create error response."""
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            },
            "metrics": {
                "durationMs": duration_ms,
                "costPointsUsed": 0,
            },
        }

    async def invoke_request(self, request: InvokeRequest) -> InvokeResponse:
        """
        Invoke using typed request/response objects.

        This is the preferred interface for new code.
        """
        result = await self.invoke(
            module_id=request.plugin_id,
            step_id=request.step_id,
            input_data=request.input_data,
            config=request.config,
            context=request.context,
            timeout_ms=request.timeout_ms,
            execution_id=request.execution_id,
            step_run_id=request.step_run_id,
        )
        return InvokeResponse.from_dict(result)


# Global singleton
_invoker: Optional[RuntimeInvoker] = None


def get_invoker() -> RuntimeInvoker:
    """Get the global RuntimeInvoker instance."""
    global _invoker
    if _invoker is None:
        _invoker = RuntimeInvoker()
    return _invoker


def reset_invoker():
    """Reset global invoker (for testing)."""
    global _invoker
    _invoker = None


async def invoke(
    module_id: str,
    step_id: str,
    input_data: Dict[str, Any],
    config: Dict[str, Any],
    context: Dict[str, Any],
    timeout_ms: int = 0,
    execution_id: Optional[str] = None,
    step_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function for module invocation.

    This is the primary entry point for invoking modules.
    """
    return await get_invoker().invoke(
        module_id=module_id,
        step_id=step_id,
        input_data=input_data,
        config=config,
        context=context,
        timeout_ms=timeout_ms,
        execution_id=execution_id,
        step_run_id=step_run_id,
    )


def parse_module_id(module_id: str) -> tuple:
    """
    Parse legacy module_id into plugin_id and step_id.

    Examples:
        "database.query" -> ("flyto-official/database", "query")
        "llm.chat" -> ("flyto-official/llm", "chat")
        "string.uppercase" -> ("flyto-official/string", "uppercase")

    Returns:
        Tuple of (plugin_id, step_id)
    """
    parts = module_id.split(".")
    if len(parts) >= 2:
        category = parts[0]
        action = ".".join(parts[1:])
        return (f"flyto-official/{category}", action)
    else:
        return (f"flyto-official/{module_id}", "execute")
