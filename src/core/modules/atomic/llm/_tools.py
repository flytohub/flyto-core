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
            module_info = registry.get_module(tool_id)
            if not module_info:
                logger.warning(f"Tool not found: {tool_id}")
                continue

            function_def = {
                "name": tool_id.replace('.', '_'),
                "description": module_info.get('description', f'Execute {tool_id}'),
                "parameters": _schema_to_json_schema(module_info.get('params_schema', []))
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
    module_func = registry.get_module_function(module_id)

    if not module_func:
        return {
            'ok': False,
            'error': f'Tool not found: {module_id}'
        }

    try:
        tool_context = {
            'params': arguments,
            'variables': parent_context.get('variables', {}),
            'execution_id': parent_context.get('execution_id'),
            'step_id': f"agent_tool_{tool_name}"
        }

        result = await module_func(tool_context)
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
