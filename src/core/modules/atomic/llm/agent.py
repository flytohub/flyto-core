# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
from ...schema.constants import Visibility
from ...types import NodeType, EdgeType, DataType

from typing import List, Optional

from ._prompt import resolve_task_prompt, stringify_value
from ._tools import build_agent_system_prompt, build_task_prompt
from ._interfaces import ChatModel, AgentTool, ChatResponse, ToolCallRequest
from ._chat_models import create_chat_model
from ._agent_tool import ModuleAgentTool

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10
MAX_AGENT_DEPTH = 3


@register_module(
    module_id='llm.agent',
    stability="stable",
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
    input_types=['any'],
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
              showIf={'prompt_source': {'$in': ['manual']}}),
        field('prompt_path', type='string', label='Prompt Path',
              label_key='modules.llm.agent.params.prompt_path',
              description='Path to extract prompt from input (e.g., {{input.message}})',
              placeholder='Enter your prompt...',
              description_key='modules.llm.agent.params.prompt_path.description',
              default='{{input}}', required=False,
              showIf={'prompt_source': {'$in': ['auto']}}, visibility=Visibility.EXPERT),
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
              showIf={'prompt_source': {'$in': ['auto']}}, visibility=Visibility.EXPERT),
        field('join_separator', type='string', label='Join Separator',
              label_key='modules.llm.agent.params.join_separator',
              description='Separator for joining array items',
              description_key='modules.llm.agent.params.join_separator.description',
              default='\n\n---\n\n', required=False,
              showIf={'join_strategy': {'$in': ['separator']}}, visibility=Visibility.EXPERT,
              placeholder=','),
        field('max_input_size', type='number', label='Max Input Size',
              label_key='modules.llm.agent.params.max_input_size',
              description='Maximum characters for prompt (prevents overflow)',
              description_key='modules.llm.agent.params.max_input_size.description',
              required=False, default=10000, min=100, max=100000,
              visibility=Visibility.EXPERT),
        field('system_prompt', type='string', label='System Prompt',
              label_key='modules.llm.agent.params.system_prompt',
              description='Instructions for the agent behavior',
              description_key='modules.llm.agent.params.system_prompt.description',
              required=False, format='multiline',
              default='You are a helpful AI agent. Use the available tools to complete the task. Think step by step.',
              placeholder='You are a helpful assistant.'),
        field('tools', type='array', label='Available Tools',
              label_key='modules.llm.agent.params.tools',
              description='List of module IDs (alternative to connecting tool nodes)',
              description_key='modules.llm.agent.params.tools.description',
              required=False, default=[],
              items={'type': 'string'},
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
        # Inline model config — used when no ai.model sub-node is connected.
        # When ai.model IS connected, these fields are ignored (sub-node overrides).
        presets.LLM_PROVIDER(default='openai'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.TEMPERATURE(default=0.7),
        presets.LLM_API_KEY(),
        presets.LLM_BASE_URL(),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the agent completed successfully',
               'description_key': 'modules.llm.agent.output.ok.description'},
        'result': {'type': 'string', 'description': 'The final result from the agent',
                   'description_key': 'modules.llm.agent.output.result.description'},
        'steps': {'type': 'array', 'description': 'List of steps the agent took',
                  'description_key': 'modules.llm.agent.output.steps.description',
                  'items': {'type': 'object', 'properties': {
                      'type': {'type': 'string'}, 'tool': {'type': 'string'},
                      'iteration': {'type': 'integer'}
                  }}},
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
    author='Flyto Team',
    license='MIT'
)
async def llm_agent(context: Dict[str, Any]) -> Dict[str, Any]:
    """Run an autonomous AI agent with tool use.

    Sub-nodes provide executable objects:
    - ai.model → ChatModel instance (handles provider-specific API calls)
    - ai.tool → AgentTool instance (handles schema + execution)
    - ai.memory → conversation history messages

    The agent loop only calls interfaces — no provider dispatch.
    """
    # Recursion guard
    agent_depth = context.get('_agent_depth', 0)
    if agent_depth >= MAX_AGENT_DEPTH:
        return {
            'ok': False,
            'error': f'Agent recursion depth exceeded (max {MAX_AGENT_DEPTH} levels).',
            'error_code': 'RECURSION_LIMIT'
        }
    context['_agent_depth'] = agent_depth + 1

    notify = context.get('_agent_notify')
    params = context['params']
    system_prompt = params.get('system_prompt', 'You are a helpful AI agent.')
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
        return {'ok': False, 'error': 'No task prompt provided.', 'error_code': 'MISSING_TASK'}

    main_input = context.get('inputs', {}).get('input')
    if main_input is not None:
        user_context['input'] = stringify_value(main_input, max_input_size)

    # ── Resolve sub-node objects ────────────────────────────────
    chat_model = _resolve_chat_model(context)
    if not chat_model:
        return {'ok': False, 'error': 'No AI Model configured. Set provider/model/api_key in params, or connect an ai.model sub-node.', 'error_code': 'MISSING_MODEL'}

    conversation_history = _resolve_memory(context)
    tools = _resolve_tools(context, list(params.get('tools', [])))

    # Build tool definitions and lookup map
    tool_defs = [t.to_tool_call_request() for t in tools] if tools else []
    tool_map = {t.name: t for t in tools}

    if not tools:
        logger.warning("No tools available for agent, running in chat-only mode")

    # Build system prompt with tool descriptions
    openai_tools = [{"type": "function", "function": {"name": td.name, "description": td.description, "parameters": td.parameters}} for td in tool_defs]
    messages = [{"role": "system", "content": build_agent_system_prompt(system_prompt, openai_tools)}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": build_task_prompt(task, user_context)})

    # ── Agent loop ──────────────────────────────────────────────
    steps = []
    total_tokens = 0
    tool_call_count = 0

    for iteration in range(max_iterations):
        logger.info(f"Agent iteration {iteration + 1}/{max_iterations}")

        if notify:
            await notify('agent:iteration', {'iteration': iteration + 1, 'max_iterations': max_iterations, 'tool_calls': tool_call_count})

        try:
            response = await chat_model.chat(messages, tools=tool_defs if tool_defs else None, tool_choice="auto" if tool_defs else None)
        except Exception as e:
            return {'ok': False, 'error': f'LLM call failed: {e}', 'error_code': 'LLM_ERROR'}

        total_tokens += response.tokens_used

        if response.tool_calls:
            for tc in response.tool_calls:
                tool_args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                steps.append({'type': 'tool_call', 'tool': tc.name, 'arguments': tool_args, 'iteration': iteration + 1})
                logger.info(f"Agent calling tool: {tc.name}")
                tool_call_count += 1

                if notify:
                    await notify('agent:tool_call', {'tool': tc.name, 'arguments': tool_args, 'iteration': iteration + 1, 'tool_call_index': tool_call_count})

                tool = tool_map.get(tc.name)
                if tool:
                    tool_result = await tool.invoke(tool_args, agent_context=context)
                else:
                    tool_result = {'ok': False, 'error': f'Tool not found: {tc.name}'}

                steps.append({'type': 'tool_result', 'tool': tc.name, 'result': _summarize_tool_result(tool_result), 'iteration': iteration + 1})

                if notify:
                    await notify('agent:tool_result', {'tool': tc.name, 'iteration': iteration + 1, 'ok': isinstance(tool_result, dict) and tool_result.get('ok', True)})

                # Append to messages in OpenAI format (ChatModel handles conversion internally)
                messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments, ensure_ascii=False)}}]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(tool_result, ensure_ascii=False)})
        else:
            final_response = response.content
            steps.append({'type': 'final_answer', 'content': final_response, 'iteration': iteration + 1})
            logger.info(f"Agent completed in {iteration + 1} iterations, {tool_call_count} tool calls")
            return {
                'ok': True,
                'data': {
                    'result': final_response,
                    'steps': steps,
                    'tool_calls': tool_call_count,
                    'tokens_used': total_tokens,
                    'iterations': iteration + 1,
                },
            }

    logger.warning(f"Agent reached max iterations ({max_iterations})")
    return {
        'ok': True,
        'data': {
            'result': 'Agent reached maximum iterations without completing the task.',
            'steps': steps, 'tool_calls': tool_call_count,
            'tokens_used': total_tokens, 'iterations': max_iterations,
            'warning': 'max_iterations_reached',
        },
    }


# ── Sub-node resolution ──────────────────────────────────────────


def _resolve_chat_model(context: Dict) -> Optional[ChatModel]:
    """Get ChatModel from connected ai.model sub-node, or build from inline params.

    Priority:
    1. Sub-node ChatModel instance (context['inputs']['model']['chat_model'])
    2. Sub-node config dict (backward compat)
    3. Inline params (provider/model/api_key in agent's own params)
    """
    # 1. From connected ai.model sub-node
    model_input = context.get('inputs', {}).get('model')
    if model_input and model_input.get('__data_type__') == 'ai_model':
        chat_model = model_input.get('chat_model')
        if chat_model is not None:
            logger.info(f"Using sub-node ChatModel: {chat_model.provider}/{chat_model.model_name}")
            return chat_model
        # Backward compat: build from config dict
        config = model_input.get('config', {})
        if config.get('api_key'):
            logger.info(f"Using sub-node config: {config.get('provider')}/{config.get('model')}")
            return create_chat_model(**config)

    # 2. From inline params (no sub-node connected)
    params = context.get('params', {})
    provider = params.get('provider')
    model = params.get('model')
    api_key = params.get('api_key')
    base_url = params.get('base_url')

    if not api_key and provider:
        env_vars = {
            'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY',
            'google': 'GOOGLE_API_KEY', 'groq': 'GROQ_API_KEY',
            'deepseek': 'DEEPSEEK_API_KEY', 'custom': None,
        }
        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)

    # Ollama doesn't need a key
    if provider == 'ollama':
        api_key = api_key or 'ollama'
        base_url = base_url or 'http://localhost:11434/v1'

    if provider and api_key:
        # Map known providers to their default base_url
        if not base_url:
            provider_urls = {
                'groq': 'https://api.groq.com/openai/v1',
                'deepseek': 'https://api.deepseek.com/v1',
            }
            base_url = provider_urls.get(provider)

        logger.info(f"Using inline model config: {provider}/{model}")
        return create_chat_model(
            provider=provider, api_key=api_key, model=model or 'gpt-4o',
            temperature=params.get('temperature', 0.7),
            base_url=base_url,
        )

    return None


def _resolve_memory(context: Dict) -> list:
    """Get conversation history from connected ai.memory."""
    memory_input = context.get('inputs', {}).get('memory')
    if memory_input and memory_input.get('__data_type__') == 'ai_memory':
        messages = memory_input.get('messages', [])
        logger.info(f"Using ai.memory with {len(messages)} messages")
        return messages
    return []


def _resolve_tools(context: Dict, param_tool_ids: list) -> List[AgentTool]:
    """Get AgentTool instances from connected ai.tool sub-nodes + param tool IDs."""
    tools: List[AgentTool] = []

    tools_input = context.get('inputs', {}).get('tools')
    if tools_input:
        items = tools_input if isinstance(tools_input, list) else [tools_input]
        for tool_data in items:
            if not isinstance(tool_data, dict) or tool_data.get('__data_type__') != 'ai_tool':
                continue
            # New protocol: AgentTool instance
            tool_obj = tool_data.get('tool')
            if tool_obj is not None:
                tools.append(tool_obj)
            else:
                # Backward compat: build from module_id
                mid = tool_data.get('module_id')
                if mid:
                    tools.append(ModuleAgentTool(module_id=mid, description=tool_data.get('description', ''), parent_context=context))

    # Also include tools from params (manual tool IDs)
    for tid in param_tool_ids:
        if tid and not any(t.module_id == tid for t in tools if hasattr(t, 'module_id')):
            tools.append(ModuleAgentTool(module_id=tid, description='', parent_context=context))

    return tools


def _summarize_tool_result(result: Any, max_len: int = 500) -> Any:
    """Summarize tool result for steps log."""
    if isinstance(result, str):
        return result[:max_len] + '...' if len(result) > max_len else result
    if isinstance(result, dict):
        summary = {'_summary': True}
        for k, v in result.items():
            if isinstance(v, str) and len(v) > max_len:
                summary[k] = v[:max_len] + f'... [{len(v)} chars]'
            elif isinstance(v, (list, dict)):
                s = json.dumps(v, default=str)
                if len(s) > max_len:
                    summary[k] = f'[{type(v).__name__}, {len(s)} bytes]'
                else:
                    summary[k] = v
            else:
                summary[k] = v
        return summary
    return result
