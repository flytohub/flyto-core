"""
AI Agent Module
Autonomous agent that can use tools (other modules) to complete tasks.

n8n-style architecture:
- Model port: Connect ai.model for LLM configuration
- Memory port: Connect ai.memory for conversation history
- Tools port: Connect ai.tool nodes for available tools
- Main input: Control flow from previous node

Prompt source:
- manual: Define task in params
- auto: Take from previous node with path resolution
"""

import json
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, field, presets
from ...types import NodeType, EdgeType, DataType

from ._prompt import resolve_task_prompt, stringify_value
from ._tools import build_tool_definitions, execute_tool, build_agent_system_prompt, build_task_prompt
from ._providers import call_openai_with_tools, call_anthropic_with_tools

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10


@register_module(
    module_id='llm.agent',
    stability="beta",
    version='2.0.0',
    category='ai',
    subcategory='agent',
    tags=['llm', 'ai', 'agent', 'autonomous', 'tools', 'react', 'n8n-style'],
    label='AI Agent',
    label_key='modules.llm.agent.label',
    description='Autonomous AI agent with multi-port connections (model, memory, tools)',
    description_key='modules.llm.agent.description',
    icon='Bot',
    color='#8B5CF6',
    node_type=NodeType.AI_AGENT,
    input_types=['string', 'object', 'ai_model', 'ai_memory', 'ai_tool'],
    output_types=['string', 'object'],
    can_connect_to=['*'],
    can_receive_from=['*', 'ai.model', 'ai.memory'],
    can_be_start=True,
    input_ports=[
        {
            'id': 'input', 'label': 'Input',
            'label_key': 'modules.llm.agent.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1, 'required': False,
            'description': 'Main control flow input'
        },
        {
            'id': 'model', 'label': 'Model',
            'label_key': 'modules.llm.agent.ports.model',
            'data_type': DataType.AI_MODEL.value,
            'edge_type': EdgeType.RESOURCE.value,
            'max_connections': 1, 'required': False,
            'color': '#10B981',
            'description': 'Connect ai.model for LLM configuration'
        },
        {
            'id': 'memory', 'label': 'Memory',
            'label_key': 'modules.llm.agent.ports.memory',
            'data_type': DataType.AI_MEMORY.value,
            'edge_type': EdgeType.RESOURCE.value,
            'max_connections': 1, 'required': False,
            'color': '#8B5CF6',
            'description': 'Connect ai.memory for conversation history'
        },
        {
            'id': 'tools', 'label': 'Tools',
            'label_key': 'modules.llm.agent.ports.tools',
            'data_type': DataType.AI_TOOL.value,
            'edge_type': EdgeType.RESOURCE.value,
            'max_connections': -1, 'required': False,
            'color': '#F59E0B',
            'description': 'Connect tool modules for agent to use'
        }
    ],
    output_ports=[
        {
            'id': 'output', 'label': 'Output',
            'label_key': 'modules.llm.agent.ports.output',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'color': '#10B981'
        },
        {
            'id': 'error', 'label': 'Error',
            'label_key': 'common.ports.error',
            'data_type': DataType.OBJECT.value,
            'edge_type': EdgeType.CONTROL.value,
            'color': '#EF4444'
        }
    ],
    timeout_ms=300000,
    retryable=True,
    max_retries=1,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['shell.execute'],
    params_schema=compose(
        field('prompt_source', type='select', label='Prompt Source',
              label_key='modules.llm.agent.params.prompt_source',
              description='Where to get the task prompt from',
              description_key='modules.llm.agent.params.prompt_source.description',
              options=[
                  {'label': 'Define below', 'value': 'manual'},
                  {'label': 'From previous node', 'value': 'auto'},
              ],
              default='manual', required=False),
        field('task', type='string', label='Task',
              label_key='modules.llm.agent.params.task',
              description='The task for the agent to complete. Use {{input}} to reference upstream data.',
              description_key='modules.llm.agent.params.task.description',
              required=False, format='multiline',
              placeholder='Analyze the following data: {{input}}',
              ui={'depends_on': {'prompt_source': 'manual'}}),
        field('prompt_path', type='string', label='Prompt Path',
              label_key='modules.llm.agent.params.prompt_path',
              description='Path to extract prompt from input (e.g., {{input.message}})',
              description_key='modules.llm.agent.params.prompt_path.description',
              default='{{input}}', required=False,
              ui={'visibility': 'advanced', 'depends_on': {'prompt_source': 'auto'}}),
        field('join_strategy', type='select', label='Array Join Strategy',
              label_key='modules.llm.agent.params.join_strategy',
              description='How to handle array inputs',
              description_key='modules.llm.agent.params.join_strategy.description',
              options=[
                  {'label': 'First item only', 'value': 'first'},
                  {'label': 'Join with newlines', 'value': 'newline'},
                  {'label': 'Join with separator', 'value': 'separator'},
                  {'label': 'As JSON array', 'value': 'json'},
              ],
              default='first', required=False,
              ui={'visibility': 'advanced', 'depends_on': {'prompt_source': 'auto'}}),
        field('join_separator', type='string', label='Join Separator',
              label_key='modules.llm.agent.params.join_separator',
              description='Separator for joining array items',
              description_key='modules.llm.agent.params.join_separator.description',
              default='\n\n---\n\n', required=False,
              ui={'visibility': 'advanced', 'depends_on': {'join_strategy': 'separator'}}),
        field('max_input_size', type='number', label='Max Input Size',
              label_key='modules.llm.agent.params.max_input_size',
              description='Maximum characters for prompt (prevents overflow)',
              description_key='modules.llm.agent.params.max_input_size.description',
              required=False, default=10000, min=100, max=100000,
              ui={'visibility': 'advanced'}),
        field('system_prompt', type='string', label='System Prompt',
              label_key='modules.llm.agent.params.system_prompt',
              description='Instructions for the agent behavior',
              description_key='modules.llm.agent.params.system_prompt.description',
              required=False, format='multiline',
              default='You are a helpful AI agent. Use the available tools to complete the task. Think step by step.'),
        field('tools', type='array', label='Available Tools',
              label_key='modules.llm.agent.params.tools',
              description='List of module IDs (alternative to connecting tool nodes)',
              description_key='modules.llm.agent.params.tools.description',
              required=False, default=[],
              ui={'component': 'tool_selector'}),
        field('context', type='object', label='Context',
              label_key='modules.llm.agent.params.context',
              description='Additional context data for the agent',
              description_key='modules.llm.agent.params.context.description',
              required=False, default={}),
        field('max_iterations', type='number', label='Max Iterations',
              label_key='modules.llm.agent.params.max_iterations',
              description='Maximum number of tool calls',
              description_key='modules.llm.agent.params.max_iterations.description',
              required=False, default=10, min=1, max=50),
        presets.LLM_PROVIDER(default='openai'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.TEMPERATURE(default=0.3),
        presets.LLM_API_KEY(),
        presets.LLM_BASE_URL(),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the agent completed successfully',
               'description_key': 'modules.llm.agent.output.ok.description'},
        'result': {'type': 'string', 'description': 'The final result from the agent',
                   'description_key': 'modules.llm.agent.output.result.description'},
        'steps': {'type': 'array', 'description': 'List of steps the agent took',
                  'description_key': 'modules.llm.agent.output.steps.description'},
        'tool_calls': {'type': 'number', 'description': 'Number of tools called',
                       'description_key': 'modules.llm.agent.output.tool_calls.description'},
        'tokens_used': {'type': 'number', 'description': 'Total tokens consumed',
                        'description_key': 'modules.llm.agent.output.tokens_used.description'}
    },
    examples=[
        {
            'title': 'Web Research Agent',
            'title_key': 'modules.llm.agent.examples.research.title',
            'params': {
                'task': 'Search for the latest news about AI and summarize the top 3 stories',
                'tools': ['http.request', 'data.json_parse'],
                'model': 'gpt-4o'
            }
        },
        {
            'title': 'Data Processing Agent',
            'title_key': 'modules.llm.agent.examples.data.title',
            'params': {
                'task': 'Read the CSV file, filter rows where status is "active", and count them',
                'tools': ['file.read', 'data.csv_parse', 'array.filter'],
                'model': 'gpt-4o'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def llm_agent(context: Dict[str, Any]) -> Dict[str, Any]:
    """Run an autonomous AI agent with tool use."""
    params = context['params']
    system_prompt = params.get('system_prompt', 'You are a helpful AI agent.')
    tool_ids = list(params.get('tools', []))
    user_context = params.get('context', {}) or {}
    max_iterations = min(params.get('max_iterations', MAX_ITERATIONS), MAX_ITERATIONS)
    max_input_size = params.get('max_input_size', 10000)

    # Resolve task prompt
    task = resolve_task_prompt(
        context=context, params=params,
        prompt_source=params.get('prompt_source', 'manual'),
        prompt_path=params.get('prompt_path', '{{input}}'),
        join_strategy=params.get('join_strategy', 'first'),
        join_separator=params.get('join_separator', '\n\n---\n\n'),
        max_input_size=max_input_size,
    )

    if not task:
        return {
            'ok': False,
            'error': 'No task prompt provided. Either set prompt_source to "manual" and provide a task, or connect an input node.',
            'error_code': 'MISSING_TASK'
        }

    # Store resolved input in context
    main_input = context.get('inputs', {}).get('input')
    if main_input is not None:
        user_context['input'] = stringify_value(main_input, max_input_size)

    # Get model config from connected ai.model or params
    provider, model, temperature, api_key, base_url = _resolve_model_config(context, params)

    # Get memory from connected ai.memory
    conversation_history = _resolve_memory(context)

    # Get tools from connected tool nodes
    _collect_connected_tools(context, tool_ids)

    # Get API key from environment if not provided
    if not api_key:
        env_vars = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}
        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)

    if not api_key:
        return {'ok': False, 'error': f'API key not provided for {provider}', 'error_code': 'MISSING_API_KEY'}

    # Build tool definitions
    tools = await build_tool_definitions(tool_ids)
    if not tools:
        logger.warning("No tools available for agent, running in chat-only mode")

    # Build messages
    messages = [{"role": "system", "content": build_agent_system_prompt(system_prompt, tools)}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": build_task_prompt(task, user_context)})

    # Agent loop
    steps = []
    total_tokens = 0
    tool_call_count = 0

    for iteration in range(max_iterations):
        logger.info(f"Agent iteration {iteration + 1}/{max_iterations}")

        if provider == 'openai':
            result = await call_openai_with_tools(messages, tools, model, temperature, api_key, base_url)
        elif provider == 'anthropic':
            result = await call_anthropic_with_tools(messages, tools, model, temperature, api_key)
        else:
            return {'ok': False, 'error': f'Provider {provider} does not support tool use', 'error_code': 'UNSUPPORTED_PROVIDER'}

        if not result.get('ok'):
            return result

        total_tokens += result.get('tokens_used', 0)

        if result.get('tool_calls'):
            for tool_call in result['tool_calls']:
                tool_name = tool_call['name']
                tool_args = tool_call['arguments']

                steps.append({'type': 'tool_call', 'tool': tool_name, 'arguments': tool_args, 'iteration': iteration + 1})
                logger.info(f"Agent calling tool: {tool_name}")
                tool_call_count += 1

                tool_result = await execute_tool(tool_name, tool_args, context)
                steps.append({'type': 'tool_result', 'tool': tool_name, 'result': tool_result, 'iteration': iteration + 1})

                messages.append({"role": "assistant", "content": None, "tool_calls": [tool_call]})
                messages.append({"role": "tool", "tool_call_id": tool_call.get('id', tool_name), "content": json.dumps(tool_result, ensure_ascii=False)})
        else:
            final_response = result.get('response', '')
            steps.append({'type': 'final_answer', 'content': final_response, 'iteration': iteration + 1})
            logger.info(f"Agent completed in {iteration + 1} iterations, {tool_call_count} tool calls")

            return {
                'ok': True, 'result': final_response, 'steps': steps,
                'tool_calls': tool_call_count, 'tokens_used': total_tokens,
                'iterations': iteration + 1
            }

    logger.warning(f"Agent reached max iterations ({max_iterations})")
    return {
        'ok': True, 'result': 'Agent reached maximum iterations without completing the task.',
        'steps': steps, 'tool_calls': tool_call_count, 'tokens_used': total_tokens,
        'iterations': max_iterations, 'warning': 'max_iterations_reached'
    }


def _resolve_model_config(context: Dict, params: Dict):
    """Extract model configuration from connected ai.model or params."""
    model_input = context.get('inputs', {}).get('model')
    if model_input and model_input.get('__data_type__') == 'ai_model':
        config = model_input.get('config', {})
        logger.info(f"Using connected ai.model: {config.get('provider')}/{config.get('model')}")
        return (
            config.get('provider', 'openai'), config.get('model', 'gpt-4o'),
            config.get('temperature', 0.3), config.get('api_key'), config.get('base_url')
        )
    return (
        params.get('provider', 'openai'), params.get('model', 'gpt-4o'),
        params.get('temperature', 0.3), params.get('api_key'), params.get('base_url')
    )


def _resolve_memory(context: Dict):
    """Extract conversation history from connected ai.memory."""
    memory_input = context.get('inputs', {}).get('memory')
    if memory_input and memory_input.get('__data_type__') == 'ai_memory':
        messages = memory_input.get('messages', [])
        logger.info(f"Using connected ai.memory with {len(messages)} messages")
        return messages
    return []


def _collect_connected_tools(context: Dict, tool_ids: list):
    """Collect tool IDs from connected tool nodes."""
    tools_input = context.get('inputs', {}).get('tools')
    if tools_input:
        if isinstance(tools_input, list):
            for tool_data in tools_input:
                if tool_data.get('__data_type__') == 'ai_tool':
                    tool_ids.append(tool_data.get('module_id'))
        elif isinstance(tools_input, dict) and tools_input.get('__data_type__') == 'ai_tool':
            tool_ids.append(tools_input.get('module_id'))
