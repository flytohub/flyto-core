# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Tool building and execution helpers for LLM Agent module.

Handles:
- Building OpenAI-compatible tool definitions from module IDs
- Schema conversion (flyto → JSON Schema)
- Tool (module) execution
"""

import json
import logging
from typing import Any, Dict, List

from ...registry import get_registry

logger = logging.getLogger(__name__)


async def build_tool_definitions(tool_ids: List[str]) -> List[Dict]:
    """Build OpenAI-compatible tool definitions from module IDs."""
    tools = []
    registry = get_registry()

    for tool_id in tool_ids:
        try:
            metadata = registry.get_metadata(tool_id)
            if not metadata:
                logger.warning(f"Tool not found: {tool_id}")
                continue

            # params_schema can be dict (keyed by param name) or list
            raw_schema = metadata.get('params_schema', {})
            if isinstance(raw_schema, dict):
                params_list = [
                    {**v, 'name': k}
                    for k, v in raw_schema.items()
                    if isinstance(v, dict)
                ]
            else:
                params_list = raw_schema

            function_def = {
                "name": tool_id.replace('.', '_'),
                "description": metadata.get('ui_description') or metadata.get('description', f'Execute {tool_id}'),
                "parameters": _schema_to_json_schema(params_list)
            }

            tools.append({
                "type": "function",
                "function": function_def
            })

        except Exception as e:
            logger.error(f"Error building tool definition for {tool_id}: {e}")

    return tools


def _schema_to_json_schema(params_schema: List[Dict]) -> Dict:
    """Convert flyto params schema to JSON Schema for OpenAI."""
    properties = {}
    required = []

    for param in params_schema:
        name = param.get('name')
        if not name:
            continue

        prop = {
            "type": _map_type(param.get('type', 'string')),
            "description": param.get('description', '')
        }

        if 'enum' in param:
            prop['enum'] = param['enum']
        if 'default' in param:
            prop['default'] = param['default']

        properties[name] = prop

        if param.get('required'):
            required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }


def _map_type(flyto_type: str) -> str:
    """Map flyto types to JSON Schema types."""
    type_map = {
        'string': 'string',
        'text': 'string',
        'number': 'number',
        'integer': 'integer',
        'boolean': 'boolean',
        'array': 'array',
        'object': 'object'
    }
    return type_map.get(flyto_type, 'string')


async def execute_tool(tool_name: str, arguments: Dict, parent_context: Dict) -> Dict:
    """Execute a tool (module) and return results."""
    module_id = tool_name.replace('_', '.')

    registry = get_registry()

    if not registry.has(module_id):
        return {
            'ok': False,
            'error': f'Tool not found: {module_id}'
        }

    try:
        module_class = registry.get(module_id)
        tool_context = {
            'params': arguments,
            'variables': parent_context.get('variables', {}),
            'execution_id': parent_context.get('execution_id'),
            'step_id': f"agent_tool_{tool_name}",
        }

        # Pass through browser/page context if available
        for ctx_key in ('browser', 'page', 'browser_context'):
            if ctx_key in parent_context:
                tool_context[ctx_key] = parent_context[ctx_key]

        module_instance = module_class(arguments, tool_context)
        result = await module_instance.run()
        return result

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return {
            'ok': False,
            'error': str(e)
        }


def build_agent_system_prompt(base_prompt: str, tools: List[Dict]) -> str:
    """Build the system prompt for the agent."""
    prompt = base_prompt + "\n\n"

    if tools:
        prompt += "You have access to the following tools:\n\n"
        for tool in tools:
            prompt += f"- **{tool['function']['name']}**: {tool['function']['description']}\n"
        prompt += "\nUse tools when needed to complete the task. "
        prompt += "When you have gathered enough information, provide a final answer."
    else:
        prompt += "Complete the task based on your knowledge."

    return prompt


def build_task_prompt(task: str, context: Dict) -> str:
    """Build the task prompt with context."""
    prompt = f"Task: {task}"

    if context:
        prompt += "\n\nContext:\n"
        for key, value in context.items():
            prompt += f"- {key}: {value}\n"

    return prompt
