# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Flyto2 Core MCP Handler — transport-independent MCP logic.

Shared by both STDIO transport (mcp_server.py) and HTTP transport (api/routes/mcp.py).
Contains tool definitions, dispatch, and execution functions.
"""

import importlib.metadata
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from core.catalog_facts import (
    BROWSER_MODULE_COUNT,
    CORE_CATALOG_CATEGORY_COUNT,
    CORE_MODULE_COUNT,
)
from core.session_reaper import touch_session, untrack_session


def _get_version() -> str:
    """Read version from installed package or pyproject.toml fallback."""
    try:
        return importlib.metadata.version("flyto-core")
    except importlib.metadata.PackageNotFoundError:
        pass
    toml_path = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    if toml_path.exists():
        for line in toml_path.read_text().splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


SERVER_VERSION = _get_version()

# MCP 2026-07-28 is stateless and selected on every request through `_meta`.
# Older revisions keep the initialize handshake for compatibility.
# Reference:
# https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning
MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
SUPPORTED_PROTOCOL_VERSIONS = (
    MODERN_PROTOCOL_VERSION,
    *LEGACY_PROTOCOL_VERSIONS,
)
_PROTOCOL_VERSION_META_KEY = "io.modelcontextprotocol/protocolVersion"
_CLIENT_CAPABILITIES_META_KEY = "io.modelcontextprotocol/clientCapabilities"
_CLIENT_INFO_META_KEY = "io.modelcontextprotocol/clientInfo"
_SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"
_DISCOVERY_TTL_MS = 60_000
_STATIC_LIST_TTL_MS = 60_000


def _server_info() -> dict:
    return {
        "name": "flyto-core",
        "title": "Flyto2 Core Execution Engine",
        "version": SERVER_VERSION,
        "description": (
            "Execute validated automation modules and recipes through a stable "
            "MCP tool surface."
        ),
        "websiteUrl": "https://github.com/flytohub/flyto-core",
    }


def _server_capabilities() -> dict:
    return {"tools": {"listChanged": False}}


SERVER_CAPABILITIES = {
    "capabilities": _server_capabilities(),
    "serverInfo": _server_info(),
}


def negotiate_protocol_version(client_version: Optional[str]) -> str:
    """Select a supported version, preferring the latest revision."""
    if client_version and client_version in SUPPORTED_PROTOCOL_VERSIONS:
        return client_version
    return SUPPORTED_PROTOCOL_VERSIONS[0]


def negotiate_legacy_protocol_version(client_version: Optional[str]) -> str:
    """Select a handshake revision without crossing into stateless MCP."""
    if client_version and client_version in LEGACY_PROTOCOL_VERSIONS:
        return client_version
    return LEGACY_PROTOCOL_VERSIONS[0]


def build_initialize_response(client_version: Optional[str]) -> dict:
    """Build the legacy `result` payload for an initialize response."""
    return {
        "protocolVersion": negotiate_legacy_protocol_version(client_version),
        **SERVER_CAPABILITIES,
    }


# ============================================================
# Tool Implementations
# ============================================================

def get_capability_manifest() -> dict:
    """Return the deterministic capability manifest for this installation.

    Read-only. Delegates to `core.capability_manifest`, which owns the
    determinism contract; this wrapper exists only to give the MCP surface a
    dispatch target with the same error shape as the other tools.
    """
    try:
        from core.capability_manifest import (
            get_capability_manifest as _build_manifest,
        )

        return _build_manifest()
    except Exception as e:
        return {"error": str(e)}


def list_modules(category: str = None) -> dict:
    try:
        from core.catalog import get_outline
        from core.modules.registry import ModuleRegistry

        outline = get_outline()

        if category:
            if category in outline:
                cat_info = outline[category]
                all_metadata = ModuleRegistry.get_all_metadata()
                modules = []
                for module_id, meta in all_metadata.items():
                    if meta.get('category') == category:
                        modules.append({
                            "module_id": module_id,
                            "label": meta.get('ui_label', module_id),
                            "description": meta.get('ui_description', '')[:100],
                        })

                return {
                    "category": category,
                    "label": cat_info['label'],
                    "description": cat_info['description'],
                    "count": len(modules),
                    "modules": sorted(modules, key=lambda x: x['module_id']),
                }
            else:
                return {"error": f"Category not found: {category}"}

        return {
            "total_categories": len(outline),
            "categories": [
                {
                    "category": cat,
                    "label": info['label'],
                    "description": info['description'],
                    "count": info['count'],
                    "use_cases": info.get('common_use_cases', []),
                }
                for cat, info in sorted(outline.items())
            ],
        }

    except Exception as e:
        return {"error": str(e)}


def search_modules(query: str, category: str = None, limit: int = 20) -> dict:
    try:
        from core.catalog.module import search_modules as catalog_search

        results = catalog_search(query, category=category, limit=limit)

        return {
            "query": query,
            "category_filter": category,
            "total": len(results),
            "results": results,
        }

    except Exception as e:
        return {"error": str(e)}


def get_module_info(module_id: str) -> dict:
    try:
        from core.catalog.module import get_module_detail

        detail = get_module_detail(module_id)

        if not detail:
            return {"error": f"Module not found: {module_id}"}

        return detail

    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Capability policy — the SAME ModuleFilter that guards the REST route, applied
# here so both MCP transports (STDIO + HTTP) are gated. Imported lazily to keep
# the STDIO path free of an import-time FastAPI dependency. The real backstop is
# enforce_module_policy at the engine chokepoint (modules/base.py); these
# boundary checks are the first line and give a clean error before instantiation.
# ---------------------------------------------------------------------------

def _module_is_allowed(module_id: str) -> bool:
    from core.module_policy import module_filter
    return module_filter.is_allowed(module_id)


def _denied_module_response(module_id: str) -> dict:
    return {
        "ok": False,
        "error": (
            f"Module '{module_id}' is blocked by the server capability policy "
            "(FLYTO_MODULE_DENYLIST / FLYTO_MODULE_ALLOWLIST). This category can grant "
            "host code execution, SSRF, or unconfined filesystem access and is denied "
            "by default. An operator must explicitly allow it before it can run."
        ),
        "blocked_by": "module_filter",
    }


def _module_missing_permissions(module_id: str) -> list:
    """Dangerous required_permissions a module declares that aren't granted."""
    from core.module_policy import missing_permissions
    try:
        from core.modules.registry import ModuleRegistry
        meta = ModuleRegistry.get_metadata(module_id) or {}
    except Exception:
        meta = {}
    return missing_permissions(meta.get("required_permissions"))


def _denied_permissions_response(module_id: str, missing: list) -> dict:
    return {
        "ok": False,
        "error": (
            f"Module '{module_id}' requires permission(s) {missing} that have not "
            "been granted. These grant host code execution or money movement and "
            "must be enabled explicitly via FLYTO_GRANTED_PERMISSIONS."
        ),
        "blocked_by": "required_permissions",
        "missing_permissions": missing,
    }


def _collect_module_ids(obj: Any) -> set:
    """Collect every module id declared in a workflow, including ids smuggled
    inside inline workflow_source/template string payloads (flow.invoke vector).

    Delegates to core.module_policy._collect_module_ids (which recurses into
    inline workflow_source/template payloads). Kept here under the historical
    name for the REST/MCP call sites and tests that import it from mcp_handler.
    """
    from core.module_policy import _collect_module_ids as _collect
    return _collect(obj)


# Backward-compatible alias used by run_recipe / execute_module pre-flight.
_collect_workflow_module_ids = _collect_module_ids


async def execute_module(
    module_id: str,
    params: Dict[str, Any],
    context: Dict[str, Any] = None,
    browser_sessions: Dict[str, Any] = None,
    debugger_sessions: Dict[str, Any] = None,
    session_activity: Dict[str, float] = None,
) -> dict:
    """
    Execute a single module.

    Args:
        module_id: Module ID (e.g., 'string.uppercase')
        params: Module parameters
        context: Execution context (optional)
        browser_sessions: Browser session store (injected by transport)
        debugger_sessions: Reverse-debugger (ReverseSession) store (injected by transport)
        session_activity: Last-used timestamp per session id, for the idle-timeout
            reaper (session_reaper.py). Touched on resolve/mint, cleared on removal.
    """
    if browser_sessions is None:
        browser_sessions = {}
    if debugger_sessions is None:
        debugger_sessions = {}
    if session_activity is None:
        session_activity = {}

    # Capability gate — fail closed before any module is resolved/instantiated.
    if not _module_is_allowed(module_id):
        return _denied_module_response(module_id)

    # Second lock: per-module dangerous permissions must be explicitly granted.
    _missing = _module_missing_permissions(module_id)
    if _missing:
        return _denied_permissions_response(module_id, _missing)

    # Inline-payload pre-flight: a nested-execution gadget (flow.invoke /
    # template.invoke / flow.subflow) can carry a denied module inside an opaque
    # workflow_source/template string. Reject if any smuggled module is denied.
    # (The gadget ids themselves are denied by default too, but this also covers
    # operators who deliberately allow the gadget yet not the smuggled module.)
    try:
        nested_module_ids = sorted(
            m for m in _collect_workflow_module_ids(params)
            if m != module_id
        )
    except Exception:
        nested_module_ids = []
    smuggled = [m for m in nested_module_ids if not _module_is_allowed(m)]
    if smuggled:
        return {
            "ok": False,
            "error": (
                f"Module '{module_id}' carries an inline sub-workflow that uses "
                f"modules denied by the server capability policy: {', '.join(smuggled)}."
            ),
            "blocked_by": "module_filter",
            "blocked_modules": smuggled,
        }

    # Match the process-wide BaseModule.run() backstop at the transport edge.
    # This gives callers a precise pre-flight error for nested modules that are
    # allowed by the capability filter but still require an operator grant.
    for nested_module_id in nested_module_ids:
        nested_missing = _module_missing_permissions(nested_module_id)
        if nested_missing:
            return _denied_permissions_response(
                nested_module_id,
                nested_missing,
            )

    try:
        from core.modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)
        if not module_class:
            return {"ok": False, "error": f"Module not found: {module_id}"}

        ctx = context or {}

        is_browser = module_id.startswith("browser.")
        is_reverse = module_id.startswith("reverse.")

        # reverse.attach needs a live browser session, exactly like any other
        # browser.* call — it CDP-attaches to ctx['browser'].real_page.
        if (is_browser and module_id != "browser.launch") or module_id == "reverse.attach":
            session_id = ctx.get("browser_session")
            if session_id and session_id in browser_sessions:
                ctx["browser"] = browser_sessions[session_id]
                touch_session(session_activity, session_id)
            elif not session_id and len(browser_sessions) == 1:
                only_id = next(iter(browser_sessions))
                ctx["browser"] = browser_sessions[only_id]
                session_id = only_id
                touch_session(session_activity, session_id)
            elif not session_id and len(browser_sessions) > 1:
                return {
                    "ok": False,
                    "error": (
                        f"Multiple browser sessions active ({len(browser_sessions)}). "
                        f"Pass browser_session in context. IDs: {list(browser_sessions.keys())}"
                    ),
                }
            elif session_id and session_id not in browser_sessions:
                return {
                    "ok": False,
                    "error": f"Browser session not found: {session_id}. Active: {list(browser_sessions.keys())}",
                }
            else:
                return {
                    "ok": False,
                    "error": "No active browser session. Call browser.launch first.",
                }

        # Every other reverse.* call rehydrates the ReverseSession minted by
        # reverse.attach (mirrors the browser_session rehydration above).
        if is_reverse and module_id != "reverse.attach":
            debugger_session_id = ctx.get("debugger_session")
            if debugger_session_id and debugger_session_id in debugger_sessions:
                ctx["reverse_session"] = debugger_sessions[debugger_session_id]
                touch_session(session_activity, debugger_session_id)
            elif not debugger_session_id and len(debugger_sessions) == 1:
                only_id = next(iter(debugger_sessions))
                ctx["reverse_session"] = debugger_sessions[only_id]
                debugger_session_id = only_id
                touch_session(session_activity, debugger_session_id)
            elif not debugger_session_id and len(debugger_sessions) > 1:
                return {
                    "ok": False,
                    "error": (
                        f"Multiple debugger sessions active ({len(debugger_sessions)}). "
                        f"Pass debugger_session in context. IDs: {list(debugger_sessions.keys())}"
                    ),
                }
            elif debugger_session_id and debugger_session_id not in debugger_sessions:
                return {
                    "ok": False,
                    "error": f"Debugger session not found: {debugger_session_id}. Active: {list(debugger_sessions.keys())}",
                }
            else:
                return {
                    "ok": False,
                    "error": "No active debugger session. Call reverse.attach first.",
                }

        module_instance = module_class(params, ctx)
        result = await module_instance.run()

        if is_browser and module_id == "browser.launch":
            driver = ctx.get("browser")
            if driver:
                session_id = str(uuid.uuid4())[:8]
                browser_sessions[session_id] = driver
                result["browser_session"] = session_id
                touch_session(session_activity, session_id)

        if is_browser and module_id == "browser.close":
            session_id = ctx.get("browser_session")
            if session_id and session_id in browser_sessions:
                del browser_sessions[session_id]
                untrack_session(session_activity, session_id)
            elif len(browser_sessions) == 1:
                for stale_id in list(browser_sessions):
                    untrack_session(session_activity, stale_id)
                browser_sessions.clear()

        if module_id == "reverse.attach":
            reverse_session = ctx.get("reverse_session")
            if reverse_session:
                debugger_session_id = str(uuid.uuid4())[:8]
                debugger_sessions[debugger_session_id] = reverse_session
                result["debugger_session"] = debugger_session_id
                touch_session(session_activity, debugger_session_id)

        if module_id == "reverse.detach":
            debugger_session_id = ctx.get("debugger_session")
            if debugger_session_id and debugger_session_id in debugger_sessions:
                del debugger_sessions[debugger_session_id]
                untrack_session(session_activity, debugger_session_id)
            elif len(debugger_sessions) == 1:
                for stale_id in list(debugger_sessions):
                    untrack_session(session_activity, stale_id)
                debugger_sessions.clear()

        return result

    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_params(module_id: str, params: Dict[str, Any]) -> dict:
    """Validate params and suggest corrections for common mistakes.

    Two-level validation:
    1. Schema-level: check required fields against params_schema
    2. Module-level: call module's own validate_params (if class-based)

    Returns:
        {"valid": True, "module_id": ...} on success.
        {"valid": False, "errors": [...], "suggestions": {...}} on failure.
        suggestions may include auto-corrected params the caller can use directly.
    """
    try:
        from core.modules.registry import ModuleRegistry

        # Check module exists
        meta = ModuleRegistry.get_metadata(module_id)
        if not meta:
            from core.catalog.module import search_modules
            alternatives = search_modules(module_id.replace('.', ' '), limit=5)
            alt_ids = [a['module_id'] for a in alternatives]
            # Sort alternatives by similarity to original module_id
            # Prefer exact partial matches (functions.file.write → file.write)
            parts = module_id.lower().split('.')
            def _sim(mid):
                score = 0
                for part in parts:
                    if part in mid.lower():
                        score += 1
                return -score  # negative for ascending sort
            alt_ids.sort(key=_sim)
            return {
                "valid": False,
                "errors": ["Module not found: {}".format(module_id)],
                "suggestions": {"alternatives": alt_ids[:3]} if alt_ids else {},
            }

        schema = meta.get('params_schema', {})

        # Level 1: Schema-based validation (always runs)
        if schema:
            missing = []
            for field_name, field_meta in schema.items():
                if field_meta.get('required', False) and field_name not in params:
                    missing.append(field_name)

            if missing:
                errors = ["Missing required parameter: {}".format(f) for f in missing]
                suggestions = _suggest_param_fixes(params, schema, "; ".join(errors))
                result = {"valid": False, "errors": errors}
                if suggestions:
                    result["suggestions"] = suggestions
                return result

        # Level 2: Module-level validation (class-based modules)
        module_class = ModuleRegistry.get(module_id)
        if module_class:
            try:
                module_instance = module_class(params, {})
                module_instance.validate_params()
            except Exception as e:
                error_msg = str(e)
                suggestions = _suggest_param_fixes(params, schema, error_msg)
                result = {"valid": False, "errors": [error_msg]}
                if suggestions:
                    result["suggestions"] = suggestions
                return result

        return {"valid": True, "module_id": module_id}

    except Exception as e:
        return {"valid": False, "errors": [str(e)]}


# Field name aliases for auto-correction
_PARAM_ALIASES = {
    "text": ["input", "content", "value", "data", "string", "message", "body", "source"],
    "path": ["file", "file_path", "filepath", "output", "filename", "output_path"],
    "search": ["find", "pattern", "query", "old", "from_text"],
    "replace": ["replacement", "new", "to", "with_text"],
    "url": ["endpoint", "link", "href", "address", "uri"],
    "selector": ["css", "element", "target", "query_selector"],
    "content": ["text", "body", "data", "value", "message"],
}


def _try_alias_fix(
    field_name: str,
    params: Dict[str, Any],
) -> Optional[tuple]:
    """Try to resolve a missing field via alias mapping.

    Returns (alias_used, value) if a match is found, else None.
    """
    aliases = _PARAM_ALIASES.get(field_name)
    if not aliases:
        return None
    for alias in aliases:
        if alias in params:
            return (alias, params[alias])
    return None


def _suggest_param_fixes(
    params: Dict[str, Any],
    schema: Dict[str, Any],
    error_msg: str,
) -> Dict[str, Any]:
    """Generate correction suggestions for invalid params.

    Returns a dict with:
    - corrected_params: auto-fixed version the caller can use directly
    - hints: human-readable fix instructions
    """
    if not schema:
        return {}

    required = {k: v for k, v in schema.items() if v.get('required', False)}
    corrected = dict(params)
    hints = []
    was_corrected = False

    for field_name, field_meta in required.items():
        if field_name in params:
            continue

        # Try alias mapping
        alias_match = _try_alias_fix(field_name, params)
        if alias_match:
            alias, value = alias_match
            corrected[field_name] = value
            hints.append(f"'{alias}' → '{field_name}' (auto-corrected)")
            was_corrected = True
            continue

        # Fill defaults from schema
        if 'default' in field_meta:
            corrected[field_name] = field_meta['default']
            was_corrected = True

    if not was_corrected:
        missing = [f"{k} ({v.get('type','?')})" for k, v in required.items() if k not in params]
        if missing:
            hints.append(f"Missing required: {', '.join(missing)}")

    result = {}
    if was_corrected:
        result["corrected_params"] = corrected
    if hints:
        result["hints"] = hints
    return result


def get_module_examples(module_id: str) -> dict:
    try:
        from core.catalog.module import get_module_detail

        detail = get_module_detail(module_id)
        if not detail:
            return {"error": f"Module not found: {module_id}"}

        return {
            "module_id": module_id,
            "label": detail.get('label', ''),
            "examples": detail.get('examples', []),
            "params_schema": detail.get('params_schema', {}),
        }

    except Exception as e:
        return {"error": str(e)}


def list_recipes() -> dict:
    """List all available recipes with metadata."""
    try:
        from cli.recipe import list_all_recipes
        recipes = list_all_recipes()
        return {
            "total": len(recipes),
            "recipes": recipes,
        }
    except Exception as e:
        return {"error": str(e)}


async def run_recipe(
    recipe_name: str,
    args: Dict[str, Any] = None,
    browser_sessions: Dict[str, Any] = None,
) -> dict:
    """Load and execute a recipe, returning step-by-step results.

    Args:
        recipe_name: Recipe name (without .yaml extension)
        args: Substitution args for {{placeholder}} in recipe
        browser_sessions: Browser session store (injected by transport)
    """
    if args is None:
        args = {}

    try:
        from cli.recipe import load_recipe, substitute_args
        from core.engine.workflow.engine import WorkflowEngine

        recipe = load_recipe(recipe_name)
        if recipe is None:
            return {"ok": False, "error": f"Recipe not found: {recipe_name}"}

        workflow = substitute_args(recipe, args)

        # Capability gate — reject the whole recipe if ANY declared step uses a
        # module denied by the policy (including modules smuggled inside inline
        # workflow_source/template payloads), before the engine runs a step.
        all_ids = _collect_workflow_module_ids(workflow)
        denied = sorted(m for m in all_ids if not _module_is_allowed(m))
        if denied:
            return {
                "ok": False,
                "error": (
                    f"Recipe '{recipe_name}' is blocked: it uses modules denied by the "
                    f"server capability policy: {', '.join(denied)}. An operator must "
                    "explicitly allow these (FLYTO_MODULE_DENYLIST / FLYTO_MODULE_ALLOWLIST) "
                    "before the recipe can run."
                ),
                "blocked_by": "module_filter",
                "blocked_modules": denied,
            }

        # Second lock: reject if any step needs an ungranted dangerous permission.
        perm_blocked = {}
        for m in sorted(all_ids):
            miss = _module_missing_permissions(m)
            if miss:
                perm_blocked[m] = miss
        if perm_blocked:
            return {
                "ok": False,
                "error": (
                    f"Recipe '{recipe_name}' is blocked: step modules need permissions "
                    "that have not been granted (FLYTO_GRANTED_PERMISSIONS): "
                    + ", ".join(f"{m}={miss}" for m, miss in perm_blocked.items())
                ),
                "blocked_by": "required_permissions",
                "blocked_modules": sorted(perm_blocked),
            }

        engine = WorkflowEngine(
            workflow=workflow,
            params=args,
            enable_trace=True,
        )

        error_msg = None
        try:
            await engine.execute()
        except Exception as e:
            error_msg = str(e)

        # Trace is available even on failure (set before re-raise)
        trace = engine.get_execution_trace()
        return _build_recipe_result(recipe_name, trace, error_msg)

    except Exception as e:
        return {"ok": False, "error": str(e)}


def _build_recipe_result(
    recipe_name: str,
    trace: Optional[Any],
    error_msg: Optional[str] = None,
) -> dict:
    """Build the run_recipe response from engine trace."""
    steps = []
    output_files = []

    if trace:
        for st in trace.steps:
            steps.append({
                "stepIndex": st.stepIndex,
                "stepId": st.stepId,
                "moduleId": st.moduleId,
                "status": st.status,
                "durationMs": st.durationMs,
            })

        # Collect output file paths from step inputs (same as CLI)
        for st in trace.steps:
            if st.input and st.input.params:
                for key in ('path', 'output'):
                    val = st.input.params.get(key, '')
                    if isinstance(val, str) and val and not val.startswith('$'):
                        p = Path(val)
                        if p.exists() and str(p) not in output_files:
                            output_files.append(str(p))

    passed = sum(1 for s in steps if s["status"] == "success")

    result = {
        "ok": error_msg is None,
        "recipe_name": recipe_name,
        "steps": steps,
        "totalSteps": len(steps),
        "passedSteps": passed,
        "durationMs": trace.durationMs if trace else 0,
        "output_files": output_files,
    }
    if error_msg:
        result["error"] = error_msg
    return result


# ============================================================
# MCP Tool Definitions
# ============================================================

TOOLS = [
    {
        "name": "list_modules",
        "title": "List Modules",
        "description": (
            "List all available flyto-core modules organized by category. "
            "Use this FIRST to discover what capabilities are available. "
            f"{CORE_MODULE_COUNT} modules across {CORE_CATALOG_CATEGORY_COUNT} catalog categories including: "
            f"browser ({BROWSER_MODULE_COUNT} modules: launch, goto, click, type, extract, screenshot, evaluate, wait, etc), "
            "string, array, datetime, file, image, api, database, notification, and more. "
            "Returns: category names, module counts, descriptions, and common use cases. "
            "Pass a category name to list all modules within that category."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "Filter to a specific category. Key categories: "
                        f"'browser' ({BROWSER_MODULE_COUNT} modules for web automation and E2E testing), "
                        "'string' (text manipulation), 'array' (list operations), "
                        "'file' (file I/O), 'image' (image processing), "
                        "'api' (HTTP requests), 'database' (DB operations), "
                        "'notification' (email/Slack/Telegram). "
                        "Omit to list all categories."
                    ),
                },
            },
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "search_modules",
        "title": "Search Modules",
        "description": (
            "Search the flyto-core MODULE CATALOG by keyword. "
            "⚠️ This searches automation modules ONLY — NOT the web. "
            "Do NOT use this to search for people, news, products, lyrics, weather, or any real-world info. "
            "For web search → use Browser Protocol: execute_module('browser.launch') → execute_module('browser.goto', {url: 'https://www.google.com/search?q=...'}) → execute_module('browser.snapshot'). "
            "Use search_modules ONLY when you need to find which automation module to use. "
            "Good examples: 'click button', 'send email', 'resize image', 'parse json'. "
            "Bad examples: person names, news topics, product names — these need Browser Protocol. "
            "Returns: matching modules with ID, label, description, and relevance score."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Automation task keyword (NOT web search). Good: 'extract text', 'take screenshot', 'fill form', 'send email'. Bad: person names, news topics, real-world queries.",
                },
                "category": {
                    "type": "string",
                    "description": "Narrow search to a specific category (optional)",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Max results to return",
                },
            },
            "required": ["query"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "get_module_info",
        "title": "Get Module Info",
        "description": (
            "Get the full specification of a module: parameter schema (names, types, required, defaults), "
            "output schema, and usage examples. "
            "ALWAYS call this before execute_module to know the exact parameters required. "
            "Returns: params_schema (JSON Schema), output_schema, examples with expected output."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {
                    "type": "string",
                    "description": "Module ID in dot notation. Examples: 'browser.launch', 'browser.extract', 'string.uppercase', 'image.resize'",
                },
            },
            "required": ["module_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "get_capability_manifest",
        "title": "Get Capability Manifest",
        "description": (
            "Get the deterministic capability manifest for this flyto-core installation "
            "(schema 'flyto.core.capability-manifest.v1'). "
            "Read-only: it describes what is installed, it does not start or change anything. "
            "Use this to check whether two workers expose the same modules, or to confirm a "
            "plugin's modules are actually loaded before depending on them. "
            "Returns: sorted module ids, capabilities with their providing module ids, categories "
            "with counts, loaded plugin ids/versions/module counts, the registry and core versions, "
            "and a stable SHA-256 'hash' over all of it. "
            "The hash is comparable across hosts — identical installed packages produce an identical "
            "hash, because the document contains no timestamps, paths, or host identity. "
            "For a module's parameter schema use get_module_info instead; this returns ids, not schemas."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "get_module_examples",
        "title": "Get Module Examples",
        "description": (
            "Get concrete usage examples for a module, showing exact parameter values and expected output. "
            "Use this if get_module_info's examples are not enough to understand usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {
                    "type": "string",
                    "description": "Module ID. Example: 'browser.extract', 'browser.evaluate'",
                },
            },
            "required": ["module_id"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "execute_module",
        "title": "Execute Module",
        "description": (
            "Execute a flyto-core module and return its output. This is the main action tool. "
            "ALWAYS call get_module_info first to know the required parameters. "
            "Returns: {ok: true, data: {...}} on success, {ok: false, error: '...'} on failure. "
            "\n"
            "BROWSER MODULE STRATEGY (important for E2E testing): "
            "- DEFAULT: Use DOM-based modules for accuracy. "
            "  browser.extract → read text, attributes, element properties from DOM. "
            "  browser.evaluate → run JavaScript to inspect page state, read DOM, check conditions. "
            "  browser.snapshot → get full DOM structure (HTML/text) for analysis. "
            "  browser.find → locate elements by selector, get their properties. "
            "  browser.wait → wait for element/condition before acting. "
            "- INTERACTION: browser.click, browser.type, browser.select, browser.scroll, browser.form. "
            "- SCREENSHOT: Use ONLY for visual/style verification (CSS comparison, layout regression, design matching). "
            "  Do NOT use screenshot to read text or find elements — use browser.extract or browser.evaluate instead. "
            "- LIFECYCLE: browser.launch → browser.goto → [actions] → browser.close. "
            "  browser.launch returns a session; all subsequent calls reuse it until browser.close."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {
                    "type": "string",
                    "description": (
                        "Module ID to execute. Common browser modules: "
                        "browser.launch, browser.goto, browser.click, browser.type, "
                        "browser.extract (read DOM elements), browser.evaluate (run JS), "
                        "browser.snapshot (DOM dump), browser.screenshot (visual only), "
                        "browser.wait, browser.find, browser.form, "
                        "browser.select, browser.scroll, browser.close"
                    ),
                },
                "params": {
                    "type": "object",
                    "description": (
                        "Module parameters as a JSON object. Common browser params: "
                        "browser.launch: {} — "
                        "browser.goto: {\"url\": \"https://example.com\"} — "
                        "browser.snapshot: {} or {\"format\": \"text\"} — "
                        "browser.type: {\"selector\": \"#id\", \"text\": \"value\"} — "
                        "browser.click: {\"selector\": \"button.cls\"} — "
                        "browser.screenshot: {\"path\": \"/tmp/shot.png\"} — "
                        "For other modules call get_module_info first."
                    ),
                },
                "context": {
                    "type": "object",
                    "description": "Execution context. For browser modules, pass {browser_session: '...'} to reuse an existing session.",
                },
            },
            "required": ["module_id", "params"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "validate_params",
        "title": "Validate Parameters",
        "description": (
            "Dry-run parameter validation for a module without executing it. "
            "Use this to check if your parameters are correct before running a destructive or slow operation. "
            "Returns: {valid: true} or {valid: false, errors: ['...']}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "module_id": {
                    "type": "string",
                    "description": "Module ID to validate against",
                },
                "params": {
                    "type": "object",
                    "description": "Parameters to validate",
                },
            },
            "required": ["module_id", "params"],
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "list_recipes",
        "title": "List Recipes",
        "description": (
            "List all available flyto-core recipes (pre-built multi-step workflows). "
            "Each recipe is a YAML file that chains multiple modules together. "
            "Returns: recipe names, descriptions, and required args. "
            "Use run_recipe to execute a recipe by name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "run_recipe",
        "title": "Run Recipe",
        "description": (
            "Execute a flyto-core recipe (pre-built multi-step workflow) by name. "
            "Recipes chain multiple modules together (e.g., browser.launch → goto → extract → file.write). "
            "Call list_recipes first to see available recipes and their required args. "
            "Returns: per-step results with status and timing, plus output file paths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe_name": {
                    "type": "string",
                    "description": "Recipe name (without .yaml extension). Example: 'competitor-intel', 'api-pipeline'",
                },
                "args": {
                    "type": "object",
                    "description": "Arguments to substitute into {{placeholder}} values in the recipe. Example: {\"url\": \"https://example.com\", \"username\": \"torvalds\"}",
                },
            },
            "required": ["recipe_name"],
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
]


# ============================================================
# JSON-RPC Dispatch
# ============================================================

def _jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: Optional[dict] = None,
) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _modern_result(
    result: dict,
    *,
    ttl_ms: Optional[int] = None,
    cache_scope: Optional[str] = None,
) -> dict:
    """Add the fields required on successful MCP 2026-07-28 results."""
    modern_result = dict(result)
    modern_result.setdefault("resultType", "complete")
    result_meta = modern_result.get("_meta")
    result_meta = dict(result_meta) if isinstance(result_meta, dict) else {}
    result_meta.setdefault(_SERVER_INFO_META_KEY, _server_info())
    modern_result["_meta"] = result_meta
    if ttl_ms is not None and cache_scope is not None:
        modern_result["ttlMs"] = ttl_ms
        modern_result["cacheScope"] = cache_scope
    return modern_result


def _request_protocol_era(
    request_id: Any,
    method: str,
    params: Any,
) -> tuple[Optional[str], Optional[dict]]:
    """Return the request era plus a structured error when metadata is invalid."""
    if not isinstance(params, dict):
        if method == "server/discover":
            return None, _jsonrpc_error(
                request_id,
                -32602,
                "Request params must be an object",
            )
        return "legacy", None

    metadata = params.get("_meta")
    has_version = (
        isinstance(metadata, dict)
        and _PROTOCOL_VERSION_META_KEY in metadata
    )
    if not has_version:
        if method == "server/discover":
            return None, _jsonrpc_error(
                request_id,
                -32602,
                f"Missing required request metadata: {_PROTOCOL_VERSION_META_KEY}",
            )
        return "legacy", None

    requested = metadata.get(_PROTOCOL_VERSION_META_KEY)
    if not isinstance(requested, str):
        return None, _jsonrpc_error(
            request_id,
            -32602,
            f"{_PROTOCOL_VERSION_META_KEY} must be a string",
        )
    if requested != MODERN_PROTOCOL_VERSION:
        return None, _jsonrpc_error(
            request_id,
            -32022,
            "Unsupported protocol version",
            {
                "requested": requested,
                "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
            },
        )

    client_capabilities = metadata.get(_CLIENT_CAPABILITIES_META_KEY)
    if not isinstance(client_capabilities, dict):
        return None, _jsonrpc_error(
            request_id,
            -32602,
            f"Missing or invalid request metadata: {_CLIENT_CAPABILITIES_META_KEY}",
        )
    client_info = metadata.get(_CLIENT_INFO_META_KEY)
    if client_info is not None and (
        not isinstance(client_info, dict)
        or not isinstance(client_info.get("name"), str)
        or not isinstance(client_info.get("version"), str)
    ):
        return None, _jsonrpc_error(
            request_id,
            -32602,
            f"Invalid request metadata: {_CLIENT_INFO_META_KEY}",
        )
    return "modern", None


def _jsonrpc_result(
    request_id: Any,
    result: dict,
    *,
    modern: bool,
    ttl_ms: Optional[int] = None,
    cache_scope: Optional[str] = None,
) -> dict:
    if modern:
        result = _modern_result(
            result,
            ttl_ms=ttl_ms,
            cache_scope=cache_scope,
        )
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


async def _handle_tool_call(
    request_id: Any,
    params: Any,
    *,
    modern: bool,
    browser_sessions: Dict[str, Any],
    debugger_sessions: Dict[str, Any],
    session_activity: Dict[str, float],
) -> dict:
    if not isinstance(params, dict):
        return _jsonrpc_error(request_id, -32602, "Request params must be an object")
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})
    if not isinstance(tool_name, str) or not isinstance(arguments, dict):
        return _jsonrpc_error(
            request_id,
            -32602,
            "Tool name must be a string and arguments must be an object",
        )

    try:
        if tool_name == "list_modules":
            result = list_modules(category=arguments.get("category"))
        elif tool_name == "search_modules":
            result = search_modules(
                query=arguments.get("query", ""),
                category=arguments.get("category"),
                limit=arguments.get("limit", 20),
            )
        elif tool_name == "get_module_info":
            result = get_module_info(module_id=arguments.get("module_id", ""))
        elif tool_name == "get_capability_manifest":
            result = get_capability_manifest()
        elif tool_name == "execute_module":
            result = await execute_module(
                module_id=arguments.get("module_id", ""),
                params=arguments.get("params", {}),
                context=arguments.get("context"),
                browser_sessions=browser_sessions,
                debugger_sessions=debugger_sessions,
                session_activity=session_activity,
            )
        elif tool_name == "validate_params":
            result = validate_params(
                module_id=arguments.get("module_id", ""),
                params=arguments.get("params", {}),
            )
        elif tool_name == "get_module_examples":
            result = get_module_examples(module_id=arguments.get("module_id", ""))
        elif tool_name == "list_recipes":
            result = list_recipes()
        elif tool_name == "run_recipe":
            result = await run_recipe(
                recipe_name=arguments.get("recipe_name", ""),
                args=arguments.get("args", {}),
                browser_sessions=browser_sessions,
            )
        else:
            return _jsonrpc_error(
                request_id,
                -32601,
                f"Unknown tool: {tool_name}",
            )

        text = json.dumps(result, ensure_ascii=False, indent=2)
        is_error = (
            isinstance(result, dict)
            and (result.get("error") is not None or result.get("ok") is False)
        )
        response_body = {
            "content": [{"type": "text", "text": text}],
            "structuredContent": result,
            "isError": is_error,
        }
        return _jsonrpc_result(request_id, response_body, modern=modern)
    except Exception as exc:
        response_body = {
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        }
        return _jsonrpc_result(request_id, response_body, modern=modern)


async def handle_jsonrpc_request(
    request: dict,
    browser_sessions: Dict[str, Any],
    debugger_sessions: Optional[Dict[str, Any]] = None,
    session_activity: Optional[Dict[str, float]] = None,
) -> Optional[dict]:
    """
    Handle a single JSON-RPC request. Returns a JSON-RPC response dict,
    or None for notifications (no id).
    """
    if debugger_sessions is None:
        debugger_sessions = {}
    if session_activity is None:
        session_activity = {}
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})
    era, protocol_error = _request_protocol_era(req_id, method, params)
    if protocol_error is not None:
        return protocol_error
    modern = era == "modern"

    if method == "initialize" and not modern:
        client_version = params.get("protocolVersion") if isinstance(params, dict) else None
        return _jsonrpc_result(
            req_id,
            build_initialize_response(client_version),
            modern=False,
        )

    if method == "server/discover" and modern:
        return _jsonrpc_result(
            req_id,
            {
                "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "capabilities": _server_capabilities(),
                "instructions": (
                    "Discover, validate, and execute Flyto2 modules and recipes "
                    "through MCP tools."
                ),
            },
            modern=True,
            ttl_ms=_DISCOVERY_TTL_MS,
            cache_scope="public",
        )

    if modern and method in {"initialize", "ping", "logging/setLevel"}:
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    if method == "tools/list":
        return _jsonrpc_result(
            req_id,
            {"tools": TOOLS},
            modern=modern,
            ttl_ms=_STATIC_LIST_TTL_MS,
            cache_scope="public",
        )

    if method == "tools/call":
        return await _handle_tool_call(
            req_id,
            params,
            modern=modern,
            browser_sessions=browser_sessions,
            debugger_sessions=debugger_sessions,
            session_activity=session_activity,
        )

    if method == "ping":
        return _jsonrpc_result(req_id, {}, modern=False)

    if method.startswith("notifications/"):
        return None  # Notifications have no response

    if req_id is not None:
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")
    return None
