"""
Plugin API Routes

HTTP endpoints for plugin management.
Compatible with FastAPI/Starlette.

Endpoints:
- GET  /api/v1/plugins/catalog     - Get available plugins
- GET  /api/v1/plugins/installed   - Get installed plugins
- POST /api/v1/plugins/install     - Install a plugin
- POST /api/v1/plugins/uninstall   - Uninstall a plugin
- POST /api/v1/plugins/{id}/load   - Load (start) a plugin
- POST /api/v1/plugins/{id}/unload - Unload (stop) a plugin
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def create_plugin_router(plugin_service=None):
    """
    Create plugin API router.

    Compatible with FastAPI. Returns a router with plugin endpoints.

    Args:
        plugin_service: Optional PluginService instance

    Returns:
        FastAPI APIRouter with plugin endpoints
    """
    try:
        from fastapi import APIRouter, HTTPException, Query, Response
        from pydantic import BaseModel
    except ImportError:
        logger.warning("FastAPI not available, plugin routes not created")
        return None

    from .service import get_plugin_service

    router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])

    # Get service
    service = plugin_service or get_plugin_service()

    # ==================== Request/Response Models ====================

    class InstallRequest(BaseModel):
        plugin_id: str

    class UninstallRequest(BaseModel):
        plugin_id: str

    class PluginResponse(BaseModel):
        ok: bool
        plugin_id: Optional[str] = None
        error: Optional[str] = None
        version: Optional[str] = None
        steps: Optional[List[str]] = None
        status: Optional[str] = None

    # ==================== Endpoints ====================

    @router.get("/catalog")
    async def get_catalog(
        response: Response,
        include_installed: bool = Query(True, description="Include installed plugins"),
    ) -> List[Dict[str, Any]]:
        """
        Get plugin catalog for marketplace.

        Returns list of available plugins with metadata.
        Supports ETag caching (max-age=300).
        """
        catalog = service.get_catalog(include_installed=include_installed)

        # Add caching headers
        etag = service.get_catalog_etag()
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = "public, max-age=300"

        return catalog

    @router.get("/installed")
    async def get_installed() -> List[Dict[str, Any]]:
        """
        Get installed plugins.

        Returns list of installed plugins with their status.
        """
        return service.get_installed_plugins()

    @router.get("/installed/modules")
    async def get_installed_modules() -> List[Dict[str, Any]]:
        """
        Get modules from installed plugins.

        Returns modules in exact ModuleItem format for frontend.
        This is the key endpoint for zero-frontend-change integration.
        """
        return service.get_installed_modules()

    @router.post("/install")
    async def install_plugin(request: InstallRequest) -> PluginResponse:
        """
        Install a plugin.

        Downloads and installs a plugin from the catalog.
        """
        result = service.install_plugin(request.plugin_id)

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return PluginResponse(
            ok=True,
            plugin_id=result.get("plugin_id"),
            version=result.get("version"),
            steps=result.get("steps"),
        )

    @router.post("/uninstall")
    async def uninstall_plugin(request: UninstallRequest) -> PluginResponse:
        """
        Uninstall a plugin.

        Removes plugin and cleans up resources.
        """
        result = service.uninstall_plugin(request.plugin_id)

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return PluginResponse(
            ok=True,
            plugin_id=result.get("plugin_id"),
        )

    @router.post("/{plugin_id}/load")
    async def load_plugin(plugin_id: str) -> PluginResponse:
        """
        Load (start) a plugin process.

        Starts the plugin subprocess for handling invocations.
        """
        result = service.load_plugin(plugin_id)

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return PluginResponse(
            ok=True,
            plugin_id=plugin_id,
            status=result.get("status"),
        )

    @router.post("/{plugin_id}/unload")
    async def unload_plugin(plugin_id: str) -> PluginResponse:
        """
        Unload (stop) a plugin process.

        Gracefully stops the plugin subprocess.
        """
        result = service.unload_plugin(plugin_id)

        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error"))

        return PluginResponse(
            ok=True,
            plugin_id=plugin_id,
            status=result.get("status"),
        )

    @router.get("/health")
    async def get_plugin_health() -> Dict[str, Any]:
        """
        Get health status of all plugins.

        Returns health information for monitoring.
        """
        # TODO: Integrate with HealthChecker
        installed = service.get_installed_plugins()

        return {
            "total_installed": len(installed),
            "plugins": {
                p["id"]: {
                    "status": p.get("status", "unknown"),
                    "version": p.get("version"),
                }
                for p in installed
            },
        }

    return router


def create_modules_tiered_extension(plugin_service=None):
    """
    Create extension for /modules/tiered endpoint.

    This function returns a callable that can be used to merge
    plugin modules into the existing /modules/tiered response.

    Usage in existing route:
        extend_tiered = create_modules_tiered_extension()

        @router.get("/modules/tiered")
        async def get_tiered_modules(tier: str = "free"):
            core_modules = get_core_modules()
            return extend_tiered(core_modules, tier)
    """
    from .service import get_plugin_service

    service = plugin_service or get_plugin_service()

    def extend_tiered_response(
        core_modules: List[Dict[str, Any]],
        tier: str = "free",
    ) -> List[Dict[str, Any]]:
        """Merge plugin modules into core modules response."""
        return service.get_merged_modules(core_modules, tier)

    return extend_tiered_response
