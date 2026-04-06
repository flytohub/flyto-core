# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
TemplateAgentTool — Wraps a flyto template as an AI Agent tool.

When the agent calls this tool, it executes the template via WorkflowEngine
with the agent's arguments as input, and returns the template's output.

This is flyto's equivalent of n8n's "Workflow Tool".
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from ._interfaces import ToolCallRequest

logger = logging.getLogger(__name__)


class TemplateAgentTool:
    """Wraps a flyto template (workflow) as an AI Agent tool.

    Satisfies the AgentTool protocol.
    """

    def __init__(
        self,
        template_id: str,
        tool_name: str,
        tool_description: str,
        input_schema: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 120,
        parent_context: Optional[Dict[str, Any]] = None,
    ):
        self._template_id = template_id
        self._tool_name = tool_name
        self._tool_description = tool_description
        self._input_schema = input_schema or {}
        self._timeout_seconds = timeout_seconds
        self._parent_context = parent_context or {}

    @property
    def name(self) -> str:
        return self._tool_name.replace(".", "--").replace(" ", "_")

    @property
    def module_id(self) -> str:
        return f"template.invoke:{self._template_id}"

    @property
    def description(self) -> str:
        return self._tool_description

    def to_tool_call_request(self) -> ToolCallRequest:
        """Build tool definition for LLM function calling."""
        # Use user-defined input_schema, or a generic one
        if self._input_schema and self._input_schema.get("properties"):
            parameters = self._input_schema
        else:
            parameters = {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Input data for the template"
                    }
                },
                "required": ["input"]
            }

        return ToolCallRequest(
            name=self.name,
            description=self._tool_description,
            parameters=parameters,
        )

    async def invoke(
        self,
        arguments: Dict[str, Any],
        agent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the template with given arguments.

        Uses WorkflowEngine to run the template in-process,
        inheriting browser/credential context from the agent.
        """
        ctx = agent_context or self._parent_context

        try:
            # Load template definition
            definition = await self._load_template(ctx)
            if not definition:
                return {"ok": False, "error": f"Template not found: {self._template_id}"}

            # Execute via WorkflowEngine
            result = await self._execute_template(definition, arguments, ctx)
            return result

        except asyncio.TimeoutError:
            return {"ok": False, "error": f"Template execution timed out ({self._timeout_seconds}s)"}
        except Exception as e:
            logger.error(f"Template tool error ({self._template_id}): {e}")
            return {"ok": False, "error": str(e)}

    async def _load_template(self, ctx: Dict) -> Optional[Dict]:
        """Load template definition from context or registry."""
        # 1. From pre-loaded template_definitions (set by engine)
        definitions = ctx.get("template_definitions", {})
        if self._template_id in definitions:
            return definitions[self._template_id]

        # 2. From template_loader callback (set by cloud backend)
        loader = ctx.get("_template_loader")
        if loader:
            return await loader(self._template_id)

        # 3. Not found
        logger.warning(f"Template {self._template_id} not found in context")
        return None

    async def _execute_template(
        self,
        definition: Dict,
        arguments: Dict[str, Any],
        ctx: Dict,
    ) -> Dict[str, Any]:
        """Execute template via WorkflowEngine."""
        from ...engine.workflow.engine import WorkflowEngine

        # Build workflow definition from template
        workflow = {
            "nodes": definition.get("nodes", []),
            "edges": definition.get("edges", []),
        }

        # Build initial context — inherit from agent
        initial_context = {
            "execution_id": ctx.get("execution_id"),
            "_agent_depth": ctx.get("_agent_depth", 0),
        }

        # Pass through browser/page context
        for key in ("browser", "page", "browser_context"):
            if key in ctx:
                initial_context[key] = ctx[key]

        # Template input = agent's tool arguments
        params = {
            "input": arguments,
            **(definition.get("default_params", {})),
        }

        engine = WorkflowEngine(
            workflow=workflow,
            params=params,
            initial_context=initial_context,
        )

        # Execute with timeout
        raw_result = await asyncio.wait_for(
            engine.execute(),
            timeout=self._timeout_seconds,
        )

        # Extract meaningful output
        if isinstance(raw_result, dict):
            # Engine returns full execution result
            if raw_result.get("__event__") == "error":
                return {"ok": False, "error": raw_result.get("error", "Template execution failed")}

            # Return the last node's output or the full result
            outputs = raw_result.get("outputs", {})
            if outputs:
                # Get the last output
                last_output = list(outputs.values())[-1] if outputs else raw_result
                return {"ok": True, "data": last_output}

            return {"ok": True, "data": raw_result}

        return {"ok": True, "data": raw_result}
