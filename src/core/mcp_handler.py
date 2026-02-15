"""
Flyto Core MCP Handler — transport-independent MCP logic.

Shared by both STDIO transport (mcp_server.py) and HTTP transport (api/routes/mcp.py).
Contains tool definitions, dispatch, and execution functions.
"""

import json
import importlib.metadata
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


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

SERVER_INFO = {
    "protocolVersion": "2025-11-25",
    "capabilities": {
        "tools": {"listChanged": False},
    },
    "serverInfo": {
        "name": "flyto-core",
        "title": "Flyto Core Execution Engine",
        "version": SERVER_VERSION,
    },
}


# ============================================================
# Tool Implementations
# ============================================================

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


async def execute_module(
    module_id: str,
    params: Dict[str, Any],
    context: Dict[str, Any] = None,
    browser_sessions: Dict[str, Any] = None,
) -> dict:
    """
    Execute a single module.

    Args:
        module_id: Module ID (e.g., 'string.uppercase')
        params: Module parameters
        context: Execution context (optional)
        browser_sessions: Browser session store (injected by transport)
    """
    if browser_sessions is None:
        browser_sessions = {}

    try:
        from core.modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)
        if not module_class:
            return {"ok": False, "error": f"Module not found: {module_id}"}

        ctx = context or {}

        is_browser = module_id.startswith("browser.")
        if is_browser and module_id != "browser.launch":
            session_id = ctx.get("browser_session")
            if session_id and session_id in browser_sessions:
                ctx["browser"] = browser_sessions[session_id]
            elif not session_id and len(browser_sessions) == 1:
                only_id = next(iter(browser_sessions))
                ctx["browser"] = browser_sessions[only_id]
                session_id = only_id
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

        module_instance = module_class(params, ctx)
        result = await module_instance.run()

        if is_browser and module_id == "browser.launch":
            driver = ctx.get("browser")
            if driver:
                session_id = str(uuid.uuid4())[:8]
                browser_sessions[session_id] = driver
                result["browser_session"] = session_id

        if is_browser and module_id == "browser.close":
            session_id = ctx.get("browser_session")
            if session_id and session_id in browser_sessions:
                del browser_sessions[session_id]
            elif len(browser_sessions) == 1:
                browser_sessions.clear()

        return result

    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_params(module_id: str, params: Dict[str, Any]) -> dict:
    try:
        from core.modules.registry import ModuleRegistry

        module_class = ModuleRegistry.get(module_id)
        if not module_class:
            return {"valid": False, "errors": [f"Module not found: {module_id}"]}

        module_instance = module_class(params, {})

        try:
            module_instance.validate_params()
            return {"valid": True, "module_id": module_id}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    except Exception as e:
        return {"valid": False, "errors": [str(e)]}


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
            "300+ modules across 40+ categories including: "
            "browser (38 modules: launch, goto, click, type, extract, screenshot, evaluate, wait, etc), "
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
                        "'browser' (38 modules for web automation and E2E testing), "
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
            "Search for modules by keyword across all categories. "
            "Use this when you know WHAT you want to do but not which module to use. "
            "Examples: 'click button', 'send email', 'resize image', 'parse json'. "
            "Returns: matching modules with ID, label, description, and relevance score."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you want to do. Examples: 'extract text from page', 'take screenshot', 'fill form', 'send slack message'",
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
            "- INTERACTION: browser.click, browser.type, browser.select, browser.scroll, browser.form, browser.login. "
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
                        "browser.wait, browser.find, browser.form, browser.login, "
                        "browser.select, browser.scroll, browser.close"
                    ),
                },
                "params": {
                    "type": "object",
                    "description": "Module parameters. Call get_module_info first to see the exact schema.",
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
]


# ============================================================
# JSON-RPC Dispatch
# ============================================================

async def handle_jsonrpc_request(
    request: dict,
    browser_sessions: Dict[str, Any],
) -> Optional[dict]:
    """
    Handle a single JSON-RPC request. Returns a JSON-RPC response dict,
    or None for notifications (no id).
    """
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": SERVER_INFO}

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "list_modules":
                result = list_modules(
                    category=arguments.get("category"),
                )
            elif tool_name == "search_modules":
                result = search_modules(
                    query=arguments.get("query", ""),
                    category=arguments.get("category"),
                    limit=arguments.get("limit", 20),
                )
            elif tool_name == "get_module_info":
                result = get_module_info(
                    module_id=arguments.get("module_id", ""),
                )
            elif tool_name == "execute_module":
                result = await execute_module(
                    module_id=arguments.get("module_id", ""),
                    params=arguments.get("params", {}),
                    context=arguments.get("context"),
                    browser_sessions=browser_sessions,
                )
            elif tool_name == "validate_params":
                result = validate_params(
                    module_id=arguments.get("module_id", ""),
                    params=arguments.get("params", {}),
                )
            elif tool_name == "get_module_examples":
                result = get_module_examples(
                    module_id=arguments.get("module_id", ""),
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }

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
            return {"jsonrpc": "2.0", "id": req_id, "result": response_body}

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                },
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    elif method.startswith("notifications/"):
        return None  # Notifications have no response

    else:
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return None
