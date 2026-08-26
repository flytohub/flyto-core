# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module Routes

GET  /v1/modules            — List all modules by category
GET  /v1/modules/{module_id} — Module detail + schema
GET  /v1/capabilities       — Deterministic capability manifest (read-only)
POST /v1/capabilities/refresh — Re-discover plugins, rebuild manifest (auth)
POST /v1/execute            — Execute single module
"""

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from core.session_reaper import touch_session, untrack_session

from ..models import ExecuteModuleRequest, ExecuteModuleResponse
from ..security import module_filter, require_auth

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
# GET /v1/capabilities
# ---------------------------------------------------------------------------

@router.get("/capabilities")
async def get_capabilities():
    """Deterministic capability manifest for this installation.

    Read-only and unauthenticated, matching the other discovery endpoints
    (`/v1/modules`, `/v1/info`): it reports which module ids and capabilities
    are installed, which is the information a client needs *before* it can
    authenticate a call to execute any of them. The document carries no
    timestamps, paths, secrets, or host identity — see
    `core.capability_manifest` for the determinism contract.
    """
    from core.capability_manifest import get_capability_manifest

    return get_capability_manifest()


# ---------------------------------------------------------------------------
# POST /v1/capabilities/refresh
# ---------------------------------------------------------------------------

@router.post("/capabilities/refresh", dependencies=[Depends(require_auth)])
async def refresh_capabilities():
    """Re-run plugin discovery and rebuild the capability manifest.

    Authenticated because it is a state change, not a read: it clears and
    rebuilds the process-wide module registry, which is disruptive to
    in-flight work and is exactly the kind of surface an unauthenticated
    caller could use to churn a server. `GET /v1/capabilities` stays open;
    only the rebuild is gated.
    """
    from core.capability_manifest import refresh_capability_manifest

    return refresh_capability_manifest()


# ---------------------------------------------------------------------------
# Nested-module pre-flight (shared shape with core.mcp_handler.execute_module)
# ---------------------------------------------------------------------------

def _nested_policy_error(module_id: str, params: Dict[str, Any]) -> Optional[str]:
    """Reason string when the request's nested module ids are denied, else None.

    `_collect_module_ids` walks every `module:` declaration in the params —
    including ids inside a verify.spec ruleset and ids smuggled into an inline
    workflow_source/template string — so a module that dispatches children
    cannot be used to reach a module the caller is not allowed to run.
    """
    # The same two helpers the MCP transport pre-flight uses, so the two
    # boundaries cannot drift into disagreeing about what a request contains.
    from core.mcp_handler import (
        _collect_workflow_module_ids,
        _module_missing_permissions,
    )

    try:
        nested_module_ids = sorted(
            m for m in _collect_workflow_module_ids(params) if m != module_id
        )
    except (AttributeError, TypeError, ValueError, RecursionError):
        # Malformed params are the caller's problem, and the module's own
        # validation reports them. An unreadable payload declares no nested
        # module, and BaseModule.run() still gates whatever it does reach.
        nested_module_ids = []

    smuggled = [m for m in nested_module_ids if not module_filter.is_allowed(m)]
    if smuggled:
        return (
            f"Module '{module_id}' declares nested module(s) blocked by security "
            f"policy: {', '.join(smuggled)}"
        )

    for nested_module_id in nested_module_ids:
        missing = _module_missing_permissions(nested_module_id)
        if missing:
            return (
                f"Nested module '{nested_module_id}' requires permission(s) "
                f"{missing} that have not been granted. These grant host code "
                "execution or money movement and must be enabled explicitly via "
                "FLYTO_GRANTED_PERMISSIONS."
            )

    return None


# ---------------------------------------------------------------------------
# POST /v1/execute
# ---------------------------------------------------------------------------

@router.post("/execute", response_model=ExecuteModuleResponse, dependencies=[Depends(require_auth)])
async def execute_module(body: ExecuteModuleRequest, request: Request):
    """Execute a single module."""
    # Module filter check
    if not module_filter.is_allowed(body.module_id):
        return ExecuteModuleResponse(
            ok=False, error=f"Module blocked by security policy: {body.module_id}"
        )

    # SECURITY (GHSA-wmwj-g59x-c8px): the top-level id is not the whole request.
    # A nested-execution module (verify.spec rulesets, flow.invoke /
    # template.invoke inline workflows) names its child modules inside its own
    # params, so an allowed parent can carry a denied child. BaseModule.run() is
    # the process-wide backstop; this boundary check matches the MCP transport
    # (core.mcp_handler.execute_module), fails before the parent does any work,
    # and returns the precise reason. Mirrors the same pre-flight there.
    nested = _nested_policy_error(body.module_id, body.params)
    if nested:
        return ExecuteModuleResponse(ok=False, error=nested)

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
        is_reverse = body.module_id.startswith("reverse.")

        # Browser session injection (same logic as mcp_server.py). reverse.attach
        # needs a live browser session too — it CDP-attaches to ctx['browser'].
        if (is_browser and body.module_id != "browser.launch") or body.module_id == "reverse.attach":
            session_id = ctx.get("browser_session")
            if session_id and session_id in state.browser_sessions:
                ctx["browser"] = state.browser_sessions[session_id]
                touch_session(state.session_activity, session_id)
            elif not session_id and len(state.browser_sessions) == 1:
                only_id = next(iter(state.browser_sessions))
                ctx["browser"] = state.browser_sessions[only_id]
                session_id = only_id
                touch_session(state.session_activity, session_id)
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

        # Debugger session injection — every reverse.* call except attach
        # rehydrates the ReverseSession minted by reverse.attach.
        if is_reverse and body.module_id != "reverse.attach":
            debugger_session_id = ctx.get("debugger_session")
            if debugger_session_id and debugger_session_id in state.debugger_sessions:
                ctx["reverse_session"] = state.debugger_sessions[debugger_session_id]
                touch_session(state.session_activity, debugger_session_id)
            elif not debugger_session_id and len(state.debugger_sessions) == 1:
                only_id = next(iter(state.debugger_sessions))
                ctx["reverse_session"] = state.debugger_sessions[only_id]
                debugger_session_id = only_id
                touch_session(state.session_activity, debugger_session_id)
            elif not debugger_session_id and len(state.debugger_sessions) > 1:
                return ExecuteModuleResponse(
                    ok=False,
                    error=(
                        f"Multiple debugger sessions active ({len(state.debugger_sessions)}). "
                        f"Pass debugger_session in context. IDs: {list(state.debugger_sessions.keys())}"
                    ),
                )
            elif debugger_session_id and debugger_session_id not in state.debugger_sessions:
                return ExecuteModuleResponse(
                    ok=False,
                    error=f"Debugger session not found: {debugger_session_id}. Active: {list(state.debugger_sessions.keys())}",
                )
            else:
                return ExecuteModuleResponse(
                    ok=False,
                    error="No active debugger session. Call reverse.attach first.",
                )

        module_instance = module_class(body.params, ctx)
        result = await module_instance.run()

        browser_session_id = None
        debugger_session_id = None

        # After browser.launch — persist driver
        if is_browser and body.module_id == "browser.launch":
            driver = ctx.get("browser")
            if driver:
                browser_session_id = str(uuid.uuid4())[:8]
                state.browser_sessions[browser_session_id] = driver
                if isinstance(result, dict):
                    result["browser_session"] = browser_session_id
                touch_session(state.session_activity, browser_session_id)

        # After browser.close — remove session
        if is_browser and body.module_id == "browser.close":
            session_id = ctx.get("browser_session")
            if session_id and session_id in state.browser_sessions:
                del state.browser_sessions[session_id]
                untrack_session(state.session_activity, session_id)
            elif len(state.browser_sessions) == 1:
                for stale_id in list(state.browser_sessions):
                    untrack_session(state.session_activity, stale_id)
                state.browser_sessions.clear()

        # After reverse.attach — persist ReverseSession
        if body.module_id == "reverse.attach":
            reverse_session = ctx.get("reverse_session")
            if reverse_session:
                debugger_session_id = str(uuid.uuid4())[:8]
                state.debugger_sessions[debugger_session_id] = reverse_session
                if isinstance(result, dict):
                    result["debugger_session"] = debugger_session_id
                touch_session(state.session_activity, debugger_session_id)

        # After reverse.detach — remove session
        if body.module_id == "reverse.detach":
            session_id = ctx.get("debugger_session")
            if session_id and session_id in state.debugger_sessions:
                del state.debugger_sessions[session_id]
                untrack_session(state.session_activity, session_id)
            elif len(state.debugger_sessions) == 1:
                for stale_id in list(state.debugger_sessions):
                    untrack_session(state.session_activity, stale_id)
                state.debugger_sessions.clear()

        duration_ms = int((time.time() - t0) * 1000)

        data = result if isinstance(result, dict) else {"result": result}
        return ExecuteModuleResponse(
            ok=True,
            data=data,
            browser_session=browser_session_id,
            debugger_session=debugger_session_id,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return ExecuteModuleResponse(ok=False, error=str(e), duration_ms=duration_ms)
