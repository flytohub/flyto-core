"""
Module Routes

GET  /v1/modules            — List all modules by category
GET  /v1/modules/{module_id} — Module detail + schema
POST /v1/execute            — Execute single module
"""

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..models import ExecuteModuleRequest, ExecuteModuleResponse

router = APIRouter(tags=["modules"])


# ---------------------------------------------------------------------------
# GET /v1/modules
# ---------------------------------------------------------------------------

@router.get("/modules")
async def list_modules(category: Optional[str] = None):
    """List all available modules, organized by category."""
    from core.catalog import get_outline
    from core.modules.registry import ModuleRegistry

    outline = get_outline()

    if category:
        if category not in outline:
            return JSONResponse({"error": f"Category not found: {category}"}, status_code=404)

        cat_info = outline[category]
        all_metadata = ModuleRegistry.get_all_metadata()
        modules = [
            {
                "module_id": mid,
                "label": meta.get("ui_label", mid),
                "description": (meta.get("ui_description", "") or "")[:100],
            }
            for mid, meta in all_metadata.items()
            if meta.get("category") == category
        ]
        return {
            "category": category,
            "label": cat_info["label"],
            "description": cat_info["description"],
            "count": len(modules),
            "modules": sorted(modules, key=lambda x: x["module_id"]),
        }

    return {
        "total_categories": len(outline),
        "categories": [
            {
                "category": cat,
                "label": info["label"],
                "description": info["description"],
                "count": info["count"],
                "use_cases": info.get("common_use_cases", []),
            }
            for cat, info in sorted(outline.items())
        ],
    }


# ---------------------------------------------------------------------------
# GET /v1/modules/{module_id}
# ---------------------------------------------------------------------------

@router.get("/modules/{module_id:path}")
async def get_module_info(module_id: str):
    """Get detailed module information including params schema and examples."""
    from core.catalog.module import get_module_detail

    detail = get_module_detail(module_id)
    if not detail:
        return JSONResponse({"error": f"Module not found: {module_id}"}, status_code=404)
    return detail


# ---------------------------------------------------------------------------
# POST /v1/execute
# ---------------------------------------------------------------------------

@router.post("/execute", response_model=ExecuteModuleResponse)
async def execute_module(body: ExecuteModuleRequest, request: Request):
    """Execute a single module."""
    state = request.app.state.server
    t0 = time.time()

    try:
        from core.modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(body.module_id)
        if not module_class:
            return ExecuteModuleResponse(
                ok=False, error=f"Module not found: {body.module_id}"
            )

        ctx: Dict[str, Any] = body.context or {}
        is_browser = body.module_id.startswith("browser.")

        # Browser session injection (same logic as mcp_server.py)
        if is_browser and body.module_id != "browser.launch":
            session_id = ctx.get("browser_session")
            if session_id and session_id in state.browser_sessions:
                ctx["browser"] = state.browser_sessions[session_id]
            elif not session_id and len(state.browser_sessions) == 1:
                only_id = next(iter(state.browser_sessions))
                ctx["browser"] = state.browser_sessions[only_id]
                session_id = only_id
            elif not session_id and len(state.browser_sessions) > 1:
                return ExecuteModuleResponse(
                    ok=False,
                    error=(
                        f"Multiple browser sessions active ({len(state.browser_sessions)}). "
                        f"Pass browser_session in context. IDs: {list(state.browser_sessions.keys())}"
                    ),
                )
            elif session_id and session_id not in state.browser_sessions:
                return ExecuteModuleResponse(
                    ok=False,
                    error=f"Browser session not found: {session_id}. Active: {list(state.browser_sessions.keys())}",
                )
            else:
                return ExecuteModuleResponse(
                    ok=False,
                    error="No active browser session. Call browser.launch first.",
                )

        module_instance = module_class(body.params, ctx)
        result = await module_instance.run()

        browser_session_id = None

        # After browser.launch — persist driver
        if is_browser and body.module_id == "browser.launch":
            driver = ctx.get("browser")
            if driver:
                browser_session_id = str(uuid.uuid4())[:8]
                state.browser_sessions[browser_session_id] = driver
                if isinstance(result, dict):
                    result["browser_session"] = browser_session_id

        # After browser.close — remove session
        if is_browser and body.module_id == "browser.close":
            session_id = ctx.get("browser_session")
            if session_id and session_id in state.browser_sessions:
                del state.browser_sessions[session_id]
            elif len(state.browser_sessions) == 1:
                state.browser_sessions.clear()

        duration_ms = int((time.time() - t0) * 1000)

        data = result if isinstance(result, dict) else {"result": result}
        return ExecuteModuleResponse(
            ok=True,
            data=data,
            browser_session=browser_session_id,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return ExecuteModuleResponse(ok=False, error=str(e), duration_ms=duration_ms)
