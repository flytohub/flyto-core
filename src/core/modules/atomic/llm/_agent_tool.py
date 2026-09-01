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
    "any": "string",  # OpenAI doesn't support "any" — fallback to string
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
                # Strip non-standard JSON Schema fields (placeholder, label, etc.)
                prop["items"] = {k: v for k, v in items_schema.items()
                                 if k in ("type", "description", "enum", "items", "properties", "default")}
                if "type" not in prop["items"]:
                    prop["items"]["type"] = "string"
                # Fix invalid types (e.g., "any" → "string")
                if prop["items"].get("type") in ("any",):
                    prop["items"]["type"] = "string"
            else:
                prop["items"] = {"type": "string"}

        # Object: include properties if defined
        if json_type == "object":
            raw_props = param.get("properties")
            if isinstance(raw_props, dict):
                # Recursively clean non-standard fields
                prop["properties"] = {
                    k: {sk: sv for sk, sv in v.items()
                         if sk in ("type", "description", "enum", "items", "properties", "default")}
                    if isinstance(v, dict) else v
                    for k, v in raw_props.items()
                }

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
            return _stamp_tool_outcome(None, {"ok": False, "error": f"Tool module not found: {module_id}"})

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
            return _stamp_tool_outcome(module_instance, result)

        except Exception as e:
            logger.error(f"Tool execution error ({module_id}): {e}")
            return _stamp_tool_outcome(None, {"ok": False, "error": str(e)})

def _stamp_tool_outcome(module_instance, result):
    """Give a tool result the same rung a step result would carry.

    A module invoked as an agent tool never touches the step executor -- this
    file builds the class and calls `run()` directly -- so
    `_apply_outcome_contract` had never run on one. Measured by spying on it:
    same module, same params, TOOL path 0 calls, STEP path 1 call. The visible
    consequence is a differential: a module that writes its own envelope
    reaches the model with a rung by accident, because the envelope rides
    inside `data` and the whole dict is serialized; a module that reports
    nothing reaches it with no rung at all, where a step would have said
    `dispatched`.

    NOT `_apply_outcome_contract` DIRECTLY, and this is the whole care in this
    function. Run over the `ok: False` results this path already produces, that
    function stamps `dispatched` on every one of them:

        module not found          -> dispatched
        capability policy block   -> dispatched
        path traversal guard      -> dispatched
        parameter validation      -> dispatched

    Nothing was dispatched in any of those. The module was never reached. On
    the step path the same stamp is harmless because `wrap_legacy_result`
    raises immediately afterwards and the result is discarded; here there is no
    raise, so the stamp is what the model reads. `dispatched` means an
    instruction left us, and telling a model that about a call the policy
    refused is the same class of false claim the ladder exists to stop -- with
    the engine, not a module, as its author.

    So: a module's own envelope is kept and capped. A failure that never ran
    gets FAILED. Only a result that neither failed nor said anything falls
    through to the default.
    """
    from ....engine.outcome import (
        ClaimBy,
        ENVELOPE_KEY,
        Outcome,
        cap,
        ceiling_for,
        default_for,
        envelope,
        read_envelope,
    )

    if not isinstance(result, dict):
        return result

    body = result.get('data')
    body = body if isinstance(body, dict) else result

    module_id = getattr(module_instance, 'module_id', '') or ''
    declared = None
    if module_id:
        from ...registry import ModuleRegistry
        declared = (ModuleRegistry.get_metadata(module_id) or {}).get('postcondition')

    existing = read_envelope(body)
    if existing is not None:
        capped = cap(existing['rung'], ceiling_for(declared))
        if capped.value != existing['rung']:
            body[ENVELOPE_KEY] = dict(existing, rung=capped.value, postcondition=declared)
        return result

    if result.get('ok') is False:
        body[ENVELOPE_KEY] = envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'tool_call_failed',
                'error': str(result.get('error', ''))[:300],
                'measured_by': 'the tool call returned ok: False',
                'detail': (
                    'The call did not succeed. Whether anything reached the '
                    'world before it failed is not claimed here -- only that '
                    'this call did not report success.'
                ),
            }],
        )
        return result

    if module_id:
        stamped = default_for(module_id, ModuleRegistry.get_metadata(module_id) or {})
        if stamped is not None:
            body[ENVELOPE_KEY] = envelope(stamped, claim_by=ClaimBy.NONE, effects=[])
    return result
