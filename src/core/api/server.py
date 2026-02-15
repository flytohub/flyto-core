"""
flyto-core HTTP Execution API Server

Deterministic execution engine for AI agents, exposed via HTTP.

Usage:
    python -m core.api              # Start on 127.0.0.1:8333
    flyto serve                     # Via CLI
    flyto serve --port 9000         # Custom port
"""

import importlib.metadata
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .state import ServerState
from .routes import modules_router, workflows_router, replay_router
from .security import get_cors_origins, init_auth

logger = logging.getLogger(__name__)


def _get_version() -> str:
    try:
        return importlib.metadata.version("flyto-core")
    except importlib.metadata.PackageNotFoundError:
        pass
    toml_path = Path(__file__).resolve().parent.parent.parent.parent / "pyproject.toml"
    if toml_path.exists():
        for line in toml_path.read_text().splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


SERVER_VERSION = _get_version()


def create_app(
    evidence_path: Optional[Path] = None,
    port: int = 8333,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="flyto-core Execution API",
        version=SERVER_VERSION,
        description="Deterministic execution engine for AI agents. "
                    "300+ atomic modules, workflow execution, evidence collection, and replay.",
    )

    # CORS — configurable via FLYTO_CORS_ORIGINS env var
    cors_origins = get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS origins: %s", cors_origins)

    # Auth — auto-generate token + write to file
    token = init_auth(port)
    if token:
        logger.info("API token: %s", token)

    state = ServerState(evidence_path=evidence_path or Path("./evidence"))
    app.state.server = state

    app.include_router(modules_router, prefix="/v1")
    app.include_router(workflows_router, prefix="/v1")
    app.include_router(replay_router, prefix="/v1")

    # ------------------------------------------------------------------
    # Top-level endpoints
    # ------------------------------------------------------------------

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": SERVER_VERSION}

    @app.get("/v1/info")
    async def info():
        from core.catalog import get_outline
        outline = get_outline()
        total_modules = sum(c["count"] for c in outline.values())
        return {
            "name": "flyto-core",
            "version": SERVER_VERSION,
            "module_count": total_modules,
            "category_count": len(outline),
            "capabilities": [
                "module_execution",
                "workflow_execution",
                "evidence_collection",
                "replay",
                "execution_trace",
            ],
        }

    @app.on_event("shutdown")
    async def shutdown():
        # Close browser sessions
        for sid, driver in list(state.browser_sessions.items()):
            try:
                await driver.close()
            except Exception:
                pass
        state.browser_sessions.clear()
        logger.info("Server shutdown — browser sessions cleaned up")

    return app


def main(host: str = "127.0.0.1", port: int = 8333):
    """Entry point: python -m core.api"""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting flyto-core Execution API v%s on %s:%d", SERVER_VERSION, host, port)

    app = create_app(port=port)
    uvicorn.run(app, host=host, port=port)
