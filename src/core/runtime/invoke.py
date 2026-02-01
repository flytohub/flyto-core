"""
Runtime Invoker

Abstraction layer for module invocation.
Phase 0: Delegates to in-process legacy modules.
Phase 1+: Can delegate to subprocess plugins.
Phase 2: Dual-track routing (prefer plugin, fallback to legacy).
"""

import logging
import time
from typing import Any, Dict, Optional, TYPE_CHECKING

from .types import InvokeRequest, InvokeResponse, InvokeMetrics, InvokeError, InvokeStatus
from .browser_session import get_browser_manager, BrowserSessionManager
from .exceptions import (
    PluginNotFoundError,
    PluginUnhealthyError,
    RuntimeError as PluginRuntimeError,
)
from .routing import (
    ModuleRouter,
    RoutingConfig,
    RoutingDecision,
    RoutingResult,
    get_router,
)

if TYPE_CHECKING:
    from .manager import PluginManager

logger = logging.getLogger(__name__)


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
            self._router.set_available_plugins(set(manager.list_plugins()))

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
        if "/" in plugin_id:
            plugin_name = plugin_id.split("/")[-1]
        else:
            plugin_name = plugin_id

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
