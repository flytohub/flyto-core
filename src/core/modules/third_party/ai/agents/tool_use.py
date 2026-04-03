# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Agent Tool Use Module
AI Agent that can call tools/functions via LLM function calling.

The module returns __tool_calls__ which the workflow engine interprets
to run other modules, enabling autonomous tool-using agents.
"""

import json
import logging
import os
from typing import Any, Dict, List

import aiohttp

from ....atomic.llm._tools import execute_tool, build_tool_definitions
from ....registry import register_module
from ....schema import compose, field
from ....errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='agent.tool_use',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='agent',
    tags=['ai', 'agent', 'tools', 'function_calling', 'autonomous'],
    label='Tool Use Agent',
    label_key='modules.agent.tool_use.label',
    description='AI Agent that can call tools/functions',
    description_key='modules.agent.tool_use.description',
    icon='Wrench',
    color='#F59E0B',

    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=180000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY', 'ANTHROPIC_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['ai.api'],

    params_schema=compose(
        field(
            'prompt',
            type='string',
            format='multiline',
            label='Prompt',
            label_key='modules.agent.tool_use.params.prompt',
            description='The goal or task for the agent',
            description_key='modules.agent.tool_use.params.prompt.description',
            required=True,
            placeholder='Describe the task for the agent...',
        ),
        field(
            'tools',
            type='array',
            label='Tools',
            label_key='modules.agent.tool_use.params.tools',
            description='List of tool definitions [{name, description, parameters}]',
            description_key='modules.agent.tool_use.params.tools.description',
            required=True,
        ),
        field(
            'provider',
            type='select',
            label='Provider',
            label_key='modules.agent.tool_use.params.provider',
            description='LLM provider for the agent',
            description_key='modules.agent.tool_use.params.provider.description',
            required=False,
            default='openai',
            options=[
                {'value': 'openai', 'label': 'OpenAI'},
                {'value': 'anthropic', 'label': 'Anthropic'},
            ],
        ),
        field(
            'model',
            type='string',
            label='Model',
            label_key='modules.agent.tool_use.params.model',
            description='Model to use',
            description_key='modules.agent.tool_use.params.model.description',
            required=False,
            default='gpt-4o',
            placeholder='gpt-4o',
        ),
        field(
            'api_key',
            type='string',
            format='password',
            label='API Key',
            label_key='modules.agent.tool_use.params.api_key',
            description='API key (falls back to environment variable)',
            description_key='modules.agent.tool_use.params.api_key.description',
            required=False,
        ),
        field(
            'max_iterations',
            type='number',
            label='Max Iterations',
            label_key='modules.agent.tool_use.params.max_iterations',
            description='Maximum number of tool call rounds',
            description_key='modules.agent.tool_use.params.max_iterations.description',
            required=False,
            default=10,
            min=1,
            max=50,
        ),
        field(
            'system_prompt',
            type='string',
            format='multiline',
            label='System Prompt',
            label_key='modules.agent.tool_use.params.system_prompt',
            description='Optional system prompt to guide the agent',
            description_key='modules.agent.tool_use.params.system_prompt.description',
            required=False,
            placeholder='You are a helpful assistant that uses tools to accomplish tasks.',
        ),
    ),

    output_schema={
        'result': {
            'type': 'string',
            'description': 'The agent final response',
            'description_key': 'modules.agent.tool_use.output.result.description',
        },
        'tool_calls': {
            'type': 'array',
            'description': 'All tool calls made during execution',
            'description_key': 'modules.agent.tool_use.output.tool_calls.description',
        },
        'iterations': {
            'type': 'number',
            'description': 'Number of iterations completed',
            'description_key': 'modules.agent.tool_use.output.iterations.description',
        },
        'model': {
            'type': 'string',
            'description': 'Model used',
            'description_key': 'modules.agent.tool_use.output.model.description',
        },
    },

    examples=[
        {
            'title': 'File Processing Agent',
            'title_key': 'modules.agent.tool_use.examples.file.title',
            'params': {
                'prompt': 'Read the config file and update the version number',
                'tools': [
                    {
                        'name': 'read_file',
                        'description': 'Read contents of a file',
                        'parameters': {
                            'type': 'object',
                            'properties': {
                                'path': {'type': 'string', 'description': 'File path'},
                            },
                            'required': ['path'],
                        },
                    },
                    {
                        'name': 'write_file',
                        'description': 'Write contents to a file',
                        'parameters': {
                            'type': 'object',
                            'properties': {
                                'path': {'type': 'string', 'description': 'File path'},
                                'content': {'type': 'string', 'description': 'File content'},
                            },
                            'required': ['path', 'content'],
                        },
                    },
                ],
                'provider': 'openai',
                'model': 'gpt-4o',
                'max_iterations': 5,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def agent_tool_use(context: Dict[str, Any]) -> Dict[str, Any]:
    """AI Agent that can call tools/functions."""
    params = context['params']
    prompt = params['prompt']
    tools = params['tools']
    provider = params.get('provider', 'openai')
    model = params.get('model', 'gpt-4o')
    api_key = params.get('api_key')
    max_iterations = params.get('max_iterations', 10)
    system_prompt = params.get('system_prompt', '')

    if not prompt:
        raise ValidationError("Prompt is required", field="prompt")

    if not tools:
        raise ValidationError("At least one tool definition is required", field="tools")

    # Resolve API key from environment if not provided
    if not api_key:
        env_vars = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
        }
        api_key = os.getenv(env_vars.get(provider, ''))

    if not api_key:
        raise ValidationError(
            f"API key not provided for {provider}",
            field="api_key",
            hint=f"Set {provider.upper()}_API_KEY environment variable or provide api_key parameter",
        )

    try:
        if provider == 'openai':
            return await _run_openai_agent(
                api_key, model, prompt, tools, max_iterations, system_prompt, context,
            )
        elif provider == 'anthropic':
            return await _run_anthropic_agent(
                api_key, model, prompt, tools, max_iterations, system_prompt, context,
            )
        else:
            raise ValidationError(
                f"Unsupported provider: {provider}",
                field="provider",
            )
    except aiohttp.ClientError as e:
        raise ModuleError(f"API request failed: {e}")


def _format_openai_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format tool definitions for OpenAI function calling."""
    formatted = []
    for tool in tools:
        formatted.append({
            "type": "function",
            "function": {
                "name": tool['name'],
                "description": tool.get('description', ''),
                "parameters": tool.get('parameters', {"type": "object", "properties": {}}),
            },
        })
    return formatted


def _format_anthropic_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format tool definitions for Anthropic tool use."""
    formatted = []
    for tool in tools:
        formatted.append({
            "name": tool['name'],
            "description": tool.get('description', ''),
            "input_schema": tool.get('parameters', {"type": "object", "properties": {}}),
        })
    return formatted


async def _run_openai_agent(
    api_key: str,
    model: str,
    prompt: str,
    tools: List[Dict[str, Any]],
    max_iterations: int,
    system_prompt: str,
    context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Run the tool-use loop with OpenAI."""
    openai_tools = _format_openai_tools(tools)
    all_tool_calls: List[Dict[str, Any]] = []

    messages: List[Dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    iteration = 0

    async with aiohttp.ClientSession() as session:
        while iteration < max_iterations:
            iteration += 1

            payload: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "tools": openai_tools,
            }

            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()

                if resp.status != 200:
                    error_msg = data.get('error', {}).get('message', str(data))
                    raise ModuleError(f"OpenAI API error: {error_msg}")

            choice = data['choices'][0]
            message = choice['message']
            finish_reason = choice.get('finish_reason', '')

            # Append assistant message to conversation
            messages.append(message)

            # If the model wants to call tools
            tool_calls_in_response = message.get('tool_calls', [])

            if not tool_calls_in_response or finish_reason == 'stop':
                # No more tool calls, return final result
                final_text = message.get('content', '')
                return {
                    'ok': True,
                    'data': {
                        'result': final_text,
                        'tool_calls': all_tool_calls,
                        'iterations': iteration,
                        'model': data.get('model', model),
                        '__tool_calls__': all_tool_calls,
                    },
                }

            # Process tool calls
            for tc in tool_calls_in_response:
                func = tc.get('function', {})
                tool_name = func.get('name', '')
                try:
                    tool_args = json.loads(func.get('arguments', '{}'))
                except json.JSONDecodeError:
                    tool_args = {}

                tool_call_record = {
                    'id': tc.get('id', ''),
                    'name': tool_name,
                    'arguments': tool_args,
                    'iteration': iteration,
                }
                all_tool_calls.append(tool_call_record)

                # Execute the tool (module) directly
                try:
                    tool_exec_result = await execute_tool(
                        tool_name, tool_args, context or {},
                    )
                    tool_result = json.dumps(tool_exec_result, default=str)
                except Exception as e:
                    logger.error(f"Tool execution error for {tool_name}: {e}")
                    tool_result = json.dumps({"error": str(e)})

                tool_call_record['result'] = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get('id', ''),
                    "content": tool_result,
                })

    # Reached max iterations
    last_content = ''
    for msg in reversed(messages):
        if msg.get('role') == 'assistant' and msg.get('content'):
            last_content = msg['content']
            break

    return {
        'ok': True,
        'data': {
            'result': last_content or f"Agent reached maximum iterations ({max_iterations})",
            'tool_calls': all_tool_calls,
            'iterations': max_iterations,
            'model': model,
            '__tool_calls__': all_tool_calls,
        },
    }


async def _run_anthropic_agent(
    api_key: str,
    model: str,
    prompt: str,
    tools: List[Dict[str, Any]],
    max_iterations: int,
    system_prompt: str,
    context: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Run the tool-use loop with Anthropic."""
    anthropic_tools = _format_anthropic_tools(tools)
    all_tool_calls: List[Dict[str, Any]] = []

    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": prompt},
    ]

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    iteration = 0

    async with aiohttp.ClientSession() as session:
        while iteration < max_iterations:
            iteration += 1

            payload: Dict[str, Any] = {
                "model": model,
                "max_tokens": 4096,
                "messages": messages,
                "tools": anthropic_tools,
            }
            if system_prompt:
                payload["system"] = system_prompt

            async with session.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()

                if resp.status != 200:
                    error_msg = data.get('error', {}).get('message', str(data))
                    raise ModuleError(f"Anthropic API error: {error_msg}")

            stop_reason = data.get('stop_reason', '')
            content_blocks = data.get('content', [])

            # Append full assistant response
            messages.append({"role": "assistant", "content": content_blocks})

            # Check for tool use blocks
            tool_use_blocks = [b for b in content_blocks if b.get('type') == 'tool_use']

            if not tool_use_blocks or stop_reason == 'end_turn':
                # No more tool calls, extract final text
                final_text = ''
                for block in content_blocks:
                    if block.get('type') == 'text':
                        final_text += block.get('text', '')

                return {
                    'ok': True,
                    'data': {
                        'result': final_text,
                        'tool_calls': all_tool_calls,
                        'iterations': iteration,
                        'model': data.get('model', model),
                        '__tool_calls__': all_tool_calls,
                    },
                }

            # Process tool use blocks
            tool_results = []
            for block in tool_use_blocks:
                tool_name = block.get('name', '')
                tool_input = block.get('input', {})
                tool_use_id = block.get('id', '')

                tool_call_record = {
                    'id': tool_use_id,
                    'name': tool_name,
                    'arguments': tool_input,
                    'iteration': iteration,
                }
                all_tool_calls.append(tool_call_record)

                # Execute the tool (module) directly
                try:
                    tool_exec_result = await execute_tool(
                        tool_name, tool_input, context or {},
                    )
                    tool_content = json.dumps(tool_exec_result, default=str)
                except Exception as e:
                    logger.error(f"Tool execution error for {tool_name}: {e}")
                    tool_content = json.dumps({"error": str(e)})

                tool_call_record['result'] = tool_content

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_content,
                })

            messages.append({"role": "user", "content": tool_results})

    # Reached max iterations
    return {
        'ok': True,
        'data': {
            'result': f"Agent reached maximum iterations ({max_iterations})",
            'tool_calls': all_tool_calls,
            'iterations': max_iterations,
            'model': model,
            '__tool_calls__': all_tool_calls,
        },
    }
