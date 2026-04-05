# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AgentTool Implementation

Wraps any flyto module as a tool for the AI Agent.
Handles schema conversion (module metadata → JSON Schema) and execution.

Migrated from _tools.py build_tool_definitions + execute_tool.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ._interfaces import ToolCallRequest

logger = logging.getLogger(__name__)


def _get_registry():
    """Lazy import to avoid circular dependencies."""
    from ...registry import get_registry
    return get_registry()


# ── Schema Conversion ────────────────────────────────────────────


_TYPE_MAP = {
    "string": "string",
    "text": "string",
    "select": "string",
    "number": "number",
    "integer": "integer",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
    "file": "string",
    "path": "string",
}


def _params_to_json_schema(params_schema) -> Dict[str, Any]:
    """Convert flyto params_schema to JSON Schema for OpenAI function calling.

    Handles both dict-keyed and list-of-dicts formats.
    """
    if isinstance(params_schema, dict):
        params_list = [
            {**v, "name": k} for k, v in params_schema.items() if isinstance(v, dict)
        ]
    elif isinstance(params_schema, list):
        params_list = params_schema
    else:
        return {"type": "object", "properties": {}, "required": []}

    properties = {}
    required = []

    for param in params_list:
        name = param.get("name")
        if not name:
            continue

        flyto_type = param.get("type", "string")
        json_type = _TYPE_MAP.get(flyto_type, "string")

        prop: Dict[str, Any] = {
            "type": json_type,
            "description": param.get("description", ""),
        }

        # Array: require items (OpenAI function calling spec)
        if json_type == "array":
            items_schema = param.get("items")
            if isinstance(items_schema, dict):
                prop["items"] = items_schema
            else:
                prop["items"] = {"type": "string"}

        # Object: include properties if defined
        if json_type == "object" and param.get("properties"):
            prop["properties"] = param["properties"]

        # Select → enum
        if flyto_type == "select" and param.get("options"):
            values = [
                opt["value"] for opt in param["options"] if isinstance(opt, dict) and "value" in opt
            ]
            if values:
                prop["enum"] = values

        if "enum" in param and "enum" not in prop:
            prop["enum"] = param["enum"]
        if "default" in param:
            prop["default"] = param["default"]

        properties[name] = prop

        if param.get("required"):
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


# ── ModuleAgentTool ──────────────────────────────────────────────


class ModuleAgentTool:
    """Wraps a flyto module as an AI Agent tool.

    Satisfies the AgentTool protocol:
    - name: tool name (double-dash format for OpenAI compat)
    - description: from module metadata
    - to_tool_call_request(): builds JSON Schema definition
    - invoke(): executes the module
    """

    def __init__(
        self,
        module_id: str,
        description: str = "",
        parent_context: Optional[Dict[str, Any]] = None,
    ):
        self._module_id = module_id
        self._custom_description = description
        self._parent_context = parent_context or {}
        self._metadata = None  # lazy loaded

    def _get_metadata(self) -> Dict[str, Any]:
        if self._metadata is None:
            registry = _get_registry()
            self._metadata = registry.get_metadata(self._module_id) or {}
        return self._metadata

    @property
    def name(self) -> str:
        return self._module_id.replace(".", "--")

    @property
    def module_id(self) -> str:
        return self._module_id

    @property
    def description(self) -> str:
        if self._custom_description:
            return self._custom_description
        meta = self._get_metadata()
        return meta.get("ui_description") or meta.get("description", f"Execute {self._module_id}")

    def to_tool_call_request(self) -> ToolCallRequest:
        """Build tool definition for LLM function calling."""
        meta = self._get_metadata()
        raw_schema = meta.get("params_schema", {})
        parameters = _params_to_json_schema(raw_schema)

        return ToolCallRequest(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )

    async def invoke(
        self,
        arguments: Dict[str, Any],
        agent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the wrapped module with given arguments.

        Args:
            arguments: Tool call arguments from the LLM
            agent_context: Override context from the agent (for _agent_depth,
                          browser context, etc.). Falls back to captured parent_context.
        """
        ctx = agent_context or self._parent_context
        registry = _get_registry()

        # Resolve module ID from tool name (handle all naming formats)
        module_id = self._module_id
        if not registry.has(module_id):
            # Try double-dash → dot
            alt = self._module_id.replace("--", ".")
            if registry.has(alt):
                module_id = alt

        if not registry.has(module_id):
            return {"ok": False, "error": f"Tool module not found: {module_id}"}

        try:
            module_class = registry.get(module_id)
            tool_context = {
                "params": arguments,
                "variables": ctx.get("variables", {}),
                "execution_id": ctx.get("execution_id"),
                "step_id": f"agent_tool_{self.name}",
                "_agent_depth": ctx.get("_agent_depth", 0),
            }

            # Pass through browser/page context if available
            for ctx_key in ("browser", "page", "browser_context"):
                if ctx_key in ctx:
                    tool_context[ctx_key] = ctx[ctx_key]

            module_instance = module_class(arguments, tool_context)
            result = await module_instance.run()
            return result

        except Exception as e:
            logger.error(f"Tool execution error ({module_id}): {e}")
            return {"ok": False, "error": str(e)}
