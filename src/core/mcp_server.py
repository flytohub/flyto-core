#!/usr/bin/env python3
"""
Flyto Core MCP Server

Expose flyto-core module capabilities to Claude via MCP protocol.
This gives Claude "hands and feet" to execute real operations.

Usage:
    python -m core.mcp_server

Claude Code config (~/.claude/mcp_servers.json):
{
    "flyto-core": {
        "command": "python",
        "args": ["-m", "core.mcp_server"],
        "cwd": "/path/to/flyto-core/src"
    }
}
"""

import json
import sys
import os
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, List

# ============================================================
# Local Development: Allow localhost for browser testing
# ============================================================
os.environ.setdefault('FLYTO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

# MCP Protocol
def send_response(id: Any, result: Any):
    response = {"jsonrpc": "2.0", "id": id, "result": result}
    print(json.dumps(response), flush=True)


def send_error(id: Any, code: int, message: str):
    response = {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
    print(json.dumps(response), flush=True)


# ============================================================
# Tool Implementations
# ============================================================

def list_modules(category: str = None) -> dict:
    """
    List all available modules, organized by category.

    Args:
        category: Filter by specific category (optional)

    Returns:
        Categories with module counts and descriptions
    """
    try:
        from core.catalog import get_outline
        from core.modules.registry import ModuleRegistry

        outline = get_outline()

        if category:
            # Filter to specific category
            if category in outline:
                cat_info = outline[category]
                # Get modules in this category
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

        # Return all categories
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
    """
    Search modules by keyword.

    Args:
        query: Search keyword
        category: Filter by category (optional)
        limit: Max results

    Returns:
        List of matching modules
    """
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
    """
    Get detailed module information including params schema and examples.

    Args:
        module_id: Module ID (e.g., 'string.uppercase', 'datetime.format')

    Returns:
        Complete module info with params_schema, examples, etc.
    """
    try:
        from core.catalog.module import get_module_detail

        detail = get_module_detail(module_id)

        if not detail:
            return {"error": f"Module not found: {module_id}"}

        return detail

    except Exception as e:
        return {"error": str(e)}


def execute_module(
    module_id: str,
    params: Dict[str, Any],
    context: Dict[str, Any] = None,
) -> dict:
    """
    Execute a single module.

    Args:
        module_id: Module ID (e.g., 'string.uppercase')
        params: Module parameters
        context: Execution context (optional)

    Returns:
        {"ok": True, "data": {...}} or {"ok": False, "error": "..."}
    """
    try:
        from core.modules.registry import ModuleRegistry

        # Get module class
        module_class = ModuleRegistry.get(module_id)
        if not module_class:
            return {"ok": False, "error": f"Module not found: {module_id}"}

        # Create instance
        ctx = context or {}
        module_instance = module_class(params, ctx)

        # Execute (sync wrapper for async)
        async def run():
            return await module_instance.run()

        result = asyncio.run(run())

        return result

    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_params(module_id: str, params: Dict[str, Any]) -> dict:
    """
    Validate module parameters without executing.

    Args:
        module_id: Module ID
        params: Parameters to validate

    Returns:
        {"valid": True} or {"valid": False, "errors": [...]}
    """
    try:
        from core.modules.registry import ModuleRegistry

        # Get module class
        module_class = ModuleRegistry.get(module_id)
        if not module_class:
            return {"valid": False, "errors": [f"Module not found: {module_id}"]}

        # Create instance and validate
        module_instance = module_class(params, {})

        try:
            module_instance.validate_params()
            return {"valid": True, "module_id": module_id}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

    except Exception as e:
        return {"valid": False, "errors": [str(e)]}


def get_module_examples(module_id: str) -> dict:
    """
    Get usage examples for a module.

    Args:
        module_id: Module ID

    Returns:
        List of examples with params and expected output
    """
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
    # =========================================================================
    # Module Discovery
    # =========================================================================
    {
        "name": "list_modules",
        "description": (
            "List all available flyto-core modules organized by category. "
            "Use this FIRST to discover what capabilities are available. "
            "300+ modules across 50 categories including: "
            "browser (39 modules: launch, goto, click, type, extract, screenshot, evaluate, wait, etc), "
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
    },
    {
        "name": "search_modules",
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
    },
    # =========================================================================
    # Module Details
    # =========================================================================
    {
        "name": "get_module_info",
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
    },
    {
        "name": "get_module_examples",
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
    },
    # =========================================================================
    # Execution
    # =========================================================================
    {
        "name": "execute_module",
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
    },
    {
        "name": "validate_params",
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
    },
]


# ============================================================
# MCP Request Handler
# ============================================================

def handle_request(request: dict):
    """Handle MCP request"""
    method = request.get("method", "")
    id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        send_response(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "flyto-core",
                "version": "1.0.0",
            },
        })

    elif method == "tools/list":
        send_response(id, {"tools": TOOLS})

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
                result = execute_module(
                    module_id=arguments.get("module_id", ""),
                    params=arguments.get("params", {}),
                    context=arguments.get("context"),
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
                send_error(id, -32601, f"Unknown tool: {tool_name}")
                return

            send_response(id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            })
        except Exception as e:
            send_error(id, -32000, str(e))

    elif method == "notifications/initialized":
        pass  # No response needed

    else:
        send_error(id, -32601, f"Method not found: {method}")


def main():
    """MCP Server main loop"""
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            handle_request(request)
        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}), flush=True)


if __name__ == "__main__":
    main()
