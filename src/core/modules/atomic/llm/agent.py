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
from ._resilience import (
    truncate_tool_result, SnapshotGuard, CircuitBreaker,
    is_transient_error, is_session_dead,
    scan_for_injection, BROWSER_POLICIES,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 30
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
        field('agent_type', type='select', label='Agent Type',
              label_key='modules.llm.agent.params.agent_type',
              description='Reasoning strategy for the agent',
              description_key='modules.llm.agent.params.agent_type.description',
              options=[
                  {'label': 'Tools Agent (Function Calling)', 'value': 'tools'},
                  {'label': 'ReAct (Chain of Thought)', 'value': 'react'},
              ],
              default='tools', required=False),
        field('system_prompt', type='string', label='System Prompt',
              label_key='modules.llm.agent.params.system_prompt',
              description='Instructions for the agent behavior',
              description_key='modules.llm.agent.params.system_prompt.description',
              required=False, format='multiline',
              default='You are a helpful AI agent. Use the available tools to complete the task. Think step by step.',
              placeholder='You are a helpful assistant.'),
        field('response_format', type='select', label='Output Format',
              label_key='modules.llm.agent.params.response_format',
              description='Expected format of the final answer',
              description_key='modules.llm.agent.params.response_format.description',
              options=[
                  {'label': 'Plain Text', 'value': 'text'},
                  {'label': 'JSON', 'value': 'json'},
                  {'label': 'JSON Schema (strict)', 'value': 'json_schema'},
              ],
              default='text', required=False),
        field('output_schema', type='object', label='Output JSON Schema',
              label_key='modules.llm.agent.params.output_schema',
              description='JSON Schema the final answer must match (for json_schema format)',
              description_key='modules.llm.agent.params.output_schema.description',
              required=False, default={},
              showIf={'response_format': {'$in': ['json_schema']}},
              ui={'component': 'json_editor'}),
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
        presets.LLM_API_KEY(),
        presets.TEMPERATURE(default=0.7),
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
            'description': 'Connect http.request and data.json_parse as tools',
            'params': {
                'task': 'Search for the latest news about AI and summarize the top 3 stories',
                'provider': 'openai',
                'model': 'gpt-4o'
            }
        },
        {
            'title': 'Data Processing Agent',
            'title_key': 'modules.llm.agent.examples.data.title',
            'description': 'Connect file.read, data.csv_parse, array.filter as tools',
            'params': {
                'task': 'Read the CSV file, filter rows where status is "active", and count them',
                'provider': 'openai',
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
    agent_type = params.get('agent_type', 'tools')
    system_prompt = params.get('system_prompt', 'You are a helpful AI agent.')
    user_context = params.get('context', {}) or {}
    max_iterations = min(params.get('max_iterations', MAX_ITERATIONS), MAX_ITERATIONS)
    response_format = params.get('response_format', 'text')
    output_schema = params.get('output_schema', {}) if response_format == 'json_schema' else None
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
    tools = _resolve_tools(context)

    # Fallback: if no tools from sub-nodes, try params.tools (list of module IDs)
    if not tools:
        params_tools = params.get('tools', [])
        if params_tools and isinstance(params_tools, list):
            for module_id in params_tools:
                if isinstance(module_id, str) and module_id.strip():
                    tools.append(ModuleAgentTool(
                        module_id=module_id.strip(),
                        description='',
                        parent_context=context,
                    ))

    # Build tool definitions and lookup map
    tool_defs = [t.to_tool_call_request() for t in tools] if tools else []
    tool_map = {t.name: t for t in tools}

    if not tools:
        logger.warning("No tools available for agent, running in chat-only mode")

    # Build system prompt with tool descriptions + output format instructions
    openai_tools = [{"type": "function", "function": {"name": td.name, "description": td.description, "parameters": td.parameters}} for td in tool_defs]
    full_system = build_agent_system_prompt(system_prompt, openai_tools)
    full_system += _build_output_format_instructions(response_format, output_schema)

    # Inject browser policies if any browser tools are connected
    has_browser_tools = any(t.module_id.startswith("browser.") for t in tools if hasattr(t, 'module_id'))
    if has_browser_tools:
        full_system += "\n\n" + BROWSER_POLICIES
        # Detect if browser is already running
        if context.get('browser'):
            full_system += "\n\nRUNTIME: Browser is ALREADY RUNNING. Do NOT call browser.launch — use browser.goto directly."

    if agent_type == 'react':
        full_system += _build_react_instructions()

    messages = [{"role": "system", "content": full_system}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": build_task_prompt(task, user_context)})

    # ── Dispatch to agent strategy ─────────────────────────────
    if agent_type == 'react':
        return await _run_react_loop(
            chat_model, messages, tools, tool_defs, tool_map,
            max_iterations, steps=[], notify=notify, context=context,
            response_format=response_format, output_schema=output_schema,
        )

    return await _run_tools_loop(
        chat_model, messages, tools, tool_defs, tool_map,
        max_iterations, steps=[], notify=notify, context=context,
        response_format=response_format, output_schema=output_schema,
    )


# ── Agent Loops ─────────────────────────────────────────────────


async def _run_tools_loop(chat_model, messages, tools, tool_defs, tool_map,
                          max_iterations, steps, notify, context,
                          response_format='text', output_schema=None):
    """Standard Tools Agent loop (function calling) with resilience protections."""
    import asyncio
    total_tokens = 0
    tool_call_count = 0

    # Resilience guards (ported from flyto-ai)
    snapshot_guard = SnapshotGuard()
    circuit = CircuitBreaker()

    for iteration in range(max_iterations):
        logger.info(f"Agent iteration {iteration + 1}/{max_iterations}")

        if notify:
            await notify('agent:iteration', {'iteration': iteration + 1, 'max_iterations': max_iterations, 'tool_calls': tool_call_count})

        # LLM call with timeout (prevent infinite hang)
        try:
            response = await asyncio.wait_for(
                chat_model.chat(messages, tools=tool_defs if tool_defs else None, tool_choice="auto" if tool_defs else None),
                timeout=120,
            )
        except asyncio.TimeoutError:
            return {'ok': False, 'error': 'LLM call timed out after 120s', 'error_code': 'LLM_TIMEOUT'}
        except Exception as e:
            error_msg = str(e)
            # Retry once on transient LLM errors (rate limit, network)
            if is_transient_error(error_msg):
                logger.warning(f"Transient LLM error, retrying: {error_msg[:100]}")
                try:
                    await asyncio.sleep(2)
                    response = await asyncio.wait_for(
                        chat_model.chat(messages, tools=tool_defs if tool_defs else None, tool_choice="auto" if tool_defs else None),
                        timeout=120,
                    )
                except Exception as e2:
                    return {'ok': False, 'error': f'LLM call failed after retry: {e2}', 'error_code': 'LLM_ERROR'}
            else:
                return {'ok': False, 'error': f'LLM call failed: {e}', 'error_code': 'LLM_ERROR'}

        total_tokens += response.tokens_used

        if response.tool_calls:
            for tc in response.tool_calls:
                tool_args = json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                tool_module_id = tc.name.replace("--", ".")
                steps.append({'type': 'tool_call', 'tool': tc.name, 'arguments': tool_args, 'iteration': iteration + 1})
                logger.info(f"Agent calling tool: {tc.name}")
                tool_call_count += 1

                if notify:
                    await notify('agent:tool_call', {'tool': tc.name, 'arguments': tool_args, 'iteration': iteration + 1, 'tool_call_index': tool_call_count})

                # Circuit breaker check
                blocked = circuit.check(tool_module_id)
                if blocked:
                    tool_result = {'ok': False, 'error': blocked}
                else:
                    # SnapshotGuard: auto-inject snapshot if needed
                    if snapshot_guard.needs_snapshot(tool_module_id):
                        snapshot_tool = tool_map.get("browser--snapshot")
                        if snapshot_tool:
                            logger.info("SnapshotGuard: auto-injecting browser.snapshot before %s", tool_module_id)
                            try:
                                snap_result = await asyncio.wait_for(
                                    snapshot_tool.invoke({"format": "text"}, agent_context=context),
                                    timeout=30,
                                )
                                snapshot_guard.on_tool_call("browser.snapshot")
                                # Inject snapshot result as context for the LLM
                                snap_content = truncate_tool_result(snap_result)
                                messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"auto_snap_{iteration}", "type": "function", "function": {"name": "browser--snapshot", "arguments": "{\"format\":\"text\"}"}}]})
                                messages.append({"role": "tool", "tool_call_id": f"auto_snap_{iteration}", "content": snap_content})
                            except Exception as snap_err:
                                logger.warning(f"SnapshotGuard auto-snapshot failed: {snap_err}")

                    # Execute tool with timeout
                    tool = tool_map.get(tc.name)
                    if tool:
                        try:
                            tool_result = await asyncio.wait_for(
                                tool.invoke(tool_args, agent_context=context),
                                timeout=60,
                            )
                        except asyncio.TimeoutError:
                            tool_result = {'ok': False, 'error': f'Tool {tc.name} timed out after 60s'}
                        except Exception as e:
                            error_msg = str(e)
                            # Retry once on transient tool errors
                            if is_transient_error(error_msg):
                                logger.warning(f"Transient tool error on {tc.name}, retrying: {error_msg[:100]}")
                                try:
                                    tool_result = await asyncio.wait_for(
                                        tool.invoke(tool_args, agent_context=context),
                                        timeout=60,
                                    )
                                except Exception as e2:
                                    tool_result = {'ok': False, 'error': str(e2)}
                            else:
                                tool_result = {'ok': False, 'error': error_msg}
                    else:
                        tool_result = {'ok': False, 'error': f'Tool not found: {tc.name}'}

                # Update guards
                tool_ok = isinstance(tool_result, dict) and tool_result.get('ok', True) and 'error' not in tool_result
                snapshot_guard.on_tool_call(tool_module_id)
                circuit.record_result(tool_module_id, tool_ok, str(tool_result.get('error', '')) if isinstance(tool_result, dict) else '')

                steps.append({'type': 'tool_result', 'tool': tc.name, 'result': _summarize_tool_result(tool_result), 'iteration': iteration + 1})

                if notify:
                    await notify('agent:tool_result', {'tool': tc.name, 'iteration': iteration + 1, 'ok': tool_ok})

                # Truncate + injection scan before adding to messages
                tool_content = truncate_tool_result(tool_result)
                injection_warning = scan_for_injection(tool_content)
                if injection_warning:
                    tool_content = injection_warning + "\n\n" + tool_content

                messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments if isinstance(tc.arguments, str) else json.dumps(tc.arguments, ensure_ascii=False)}}]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_content})
        else:
            final_response = _parse_output(response.content, response_format, output_schema)
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


async def _run_react_loop(chat_model, messages, tools, tool_defs, tool_map,
                          max_iterations, steps, notify, context,
                          response_format='text', output_schema=None):
    """ReAct Agent loop — Thought → Action → Observation chain.

    Instead of function calling, the LLM outputs structured text:
    Thought: reasoning about what to do
    Action: tool_name({"arg": "value"})
    or
    Final Answer: the result

    The loop parses the text, executes tools, and feeds observations back.
    """
    import re, asyncio
    total_tokens = 0
    tool_call_count = 0
    snapshot_guard = SnapshotGuard()
    circuit = CircuitBreaker()

    for iteration in range(max_iterations):
        logger.info(f"ReAct iteration {iteration + 1}/{max_iterations}")

        if notify:
            await notify('agent:iteration', {'iteration': iteration + 1, 'max_iterations': max_iterations, 'tool_calls': tool_call_count})

        try:
            response = await asyncio.wait_for(chat_model.chat(messages), timeout=120)
        except asyncio.TimeoutError:
            return {'ok': False, 'error': 'LLM call timed out after 120s', 'error_code': 'LLM_TIMEOUT'}
        except Exception as e:
            return {'ok': False, 'error': f'LLM call failed: {e}', 'error_code': 'LLM_ERROR'}

        total_tokens += response.tokens_used
        content = response.content.strip()

        thought, action, final_answer = _parse_react_response(content)

        if thought:
            steps.append({'type': 'thought', 'content': thought, 'iteration': iteration + 1})

        if final_answer is not None:
            parsed = _parse_output(final_answer, response_format, output_schema)
            steps.append({'type': 'final_answer', 'content': parsed, 'iteration': iteration + 1})
            logger.info(f"ReAct completed in {iteration + 1} iterations, {tool_call_count} tool calls")
            return {
                'ok': True,
                'data': {
                    'result': parsed, 'steps': steps,
                    'tool_calls': tool_call_count, 'tokens_used': total_tokens,
                    'iterations': iteration + 1,
                },
            }

        if action:
            tool_name, tool_args = action
            tool_module_id = tool_name.replace("--", ".")
            steps.append({'type': 'tool_call', 'tool': tool_name, 'arguments': tool_args, 'iteration': iteration + 1})
            tool_call_count += 1

            if notify:
                await notify('agent:tool_call', {'tool': tool_name, 'arguments': tool_args, 'iteration': iteration + 1, 'tool_call_index': tool_call_count})

            blocked = circuit.check(tool_module_id)
            if blocked:
                tool_result = {'ok': False, 'error': blocked}
            else:
                tool = tool_map.get(tool_name)
                if tool:
                    try:
                        tool_result = await asyncio.wait_for(
                            tool.invoke(tool_args, agent_context=context), timeout=60)
                    except asyncio.TimeoutError:
                        tool_result = {'ok': False, 'error': f'Tool {tool_name} timed out after 60s'}
                    except Exception as e:
                        tool_result = {'ok': False, 'error': str(e)}
                else:
                    tool_result = {'ok': False, 'error': f'Tool not found: {tool_name}'}

            tool_ok = isinstance(tool_result, dict) and tool_result.get('ok', True) and 'error' not in tool_result
            snapshot_guard.on_tool_call(tool_module_id)
            circuit.record_result(tool_module_id, tool_ok, str(tool_result.get('error', '')) if isinstance(tool_result, dict) else '')

            steps.append({'type': 'tool_result', 'tool': tool_name, 'result': _summarize_tool_result(tool_result), 'iteration': iteration + 1})

            if notify:
                await notify('agent:tool_result', {'tool': tool_name, 'iteration': iteration + 1, 'ok': tool_ok})

            observation = truncate_tool_result(tool_result)
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"Observation: {observation}"})
        else:
            # No action and no final answer — treat content as final answer
            parsed = _parse_output(content, response_format, output_schema)
            steps.append({'type': 'final_answer', 'content': parsed, 'iteration': iteration + 1})
            return {
                'ok': True,
                'data': {
                    'result': parsed,
                    'steps': steps,
                    'tool_calls': tool_call_count,
                    'tokens_used': total_tokens,
                    'iterations': iteration + 1,
                },
            }

    logger.warning(f"ReAct agent reached max iterations ({max_iterations})")
    return {
        'ok': True,
        'data': {
            'result': 'Agent reached maximum iterations without completing the task.',
            'steps': steps, 'tool_calls': tool_call_count,
            'tokens_used': total_tokens, 'iterations': max_iterations,
            'warning': 'max_iterations_reached',
        },
    }


# ── ReAct Parsing ───────────────────────────────────────────────


def _parse_react_response(content: str):
    """Parse ReAct-style response into (thought, action, final_answer).

    Expected format:
        Thought: ...reasoning...
        Action: tool_name({"arg": "value"})
    or:
        Thought: ...reasoning...
        Final Answer: ...result...
    """
    import re

    thought = None
    action = None
    final_answer = None

    # Extract Thought
    thought_match = re.search(r'Thought:\s*(.+?)(?=\n(?:Action|Final Answer):|\Z)', content, re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()

    # Check for Final Answer
    fa_match = re.search(r'Final Answer:\s*(.+)', content, re.DOTALL)
    if fa_match:
        final_answer = fa_match.group(1).strip()
        return thought, None, final_answer

    # Check for Action
    action_match = re.search(r'Action:\s*(\S+?)(?:\((.+)\))?$', content, re.MULTILINE)
    if action_match:
        tool_name = action_match.group(1).strip()
        args_str = action_match.group(2) or '{}'
        try:
            tool_args = json.loads(args_str)
        except (json.JSONDecodeError, TypeError):
            tool_args = {"input": args_str}
        action = (tool_name, tool_args)

    return thought, action, final_answer


def _build_react_instructions() -> str:
    """Build ReAct-specific system prompt addition."""
    return """

## Reasoning Format (ReAct)

You must respond using this exact format:

Thought: <your reasoning about what to do next>
Action: tool_name({"param": "value"})

After receiving an Observation, continue with another Thought/Action cycle.
When you have the final answer:

Thought: <your reasoning about why you're done>
Final Answer: <your final response>

Always start with "Thought:" and always use the exact tool names provided."""


# ── Output Format ───────────────────────────────────────────────


def _build_output_format_instructions(response_format: str, output_schema: Optional[Dict]) -> str:
    """Build output format instructions for the system prompt."""
    if response_format == 'text':
        return ''
    if response_format == 'json':
        return '\n\nIMPORTANT: Your final answer MUST be valid JSON. Do not wrap it in markdown code blocks.'
    if response_format == 'json_schema' and output_schema:
        schema_str = json.dumps(output_schema, indent=2, ensure_ascii=False)
        return f'\n\nIMPORTANT: Your final answer MUST be valid JSON matching this exact schema:\n```json\n{schema_str}\n```\nDo not wrap the output in markdown code blocks. Output only the JSON object.'
    return ''


def _parse_output(content: str, response_format: str, output_schema: Optional[Dict]):
    """Parse and validate the final output according to response_format."""
    # Always strip markdown code blocks — LLMs frequently wrap JSON in ```
    cleaned = content.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        cleaned = '\n'.join(lines).strip()

    # Try JSON parse regardless of format — if it's valid JSON, return parsed
    if cleaned.startswith('{') or cleaned.startswith('['):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    if response_format == 'text':
        return content

    if response_format in ('json', 'json_schema'):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON output, returning as string")
            return content

    return content


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


def _resolve_tools(context: Dict) -> List[AgentTool]:
    """Get AgentTool instances from connected ai.tool sub-nodes."""
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
