"""
AI Agent Module
Autonomous agent that can use tools (other modules) to complete tasks
Similar to n8n's AI Agent node with multiple input ports

n8n-style architecture:
- Model port: Connect ai.model for LLM configuration
- Memory port: Connect ai.memory for conversation history
- Tools port: Connect ai.tool nodes for available tools
- Main input: Control flow from previous node

Supports n8n-style prompt source:
- manual: Define task in params
- auto: Take from previous node with path resolution
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

from ...registry import register_module, get_registry
from ...schema import compose, field, presets
from ...types import NodeType, EdgeType, DataType


logger = logging.getLogger(__name__)


# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 10


# =============================================================================
# Prompt Resolution Helpers
# =============================================================================

def _resolve_task_prompt(
    context: Dict[str, Any],
    params: Dict[str, Any],
    prompt_source: str,
    prompt_path: str,
    join_strategy: str,
    join_separator: str,
    max_input_size: int,
) -> str:
    """
    Resolve the task prompt based on source configuration.

    Args:
        context: Execution context with inputs
        params: Module parameters
        prompt_source: 'manual' or 'auto'
        prompt_path: Path expression for auto mode (e.g., {{input.message}})
        join_strategy: How to handle arrays ('first', 'newline', 'separator', 'json')
        join_separator: Custom separator for 'separator' strategy
        max_input_size: Maximum characters for prompt

    Returns:
        Resolved task string
    """
    if prompt_source == 'manual':
        task = params.get('task', '')
        # Apply variable substitution for manual mode
        if task and '{{' in task:
            task = _substitute_variables(task, context, max_input_size)
        return task

    # Auto mode: resolve from input using prompt_path
    return _resolve_from_input(
        context=context,
        prompt_path=prompt_path,
        join_strategy=join_strategy,
        join_separator=join_separator,
        max_input_size=max_input_size,
    )


def _resolve_from_input(
    context: Dict[str, Any],
    prompt_path: str,
    join_strategy: str,
    join_separator: str,
    max_input_size: int,
) -> str:
    """
    Resolve prompt from input using path expression.

    Args:
        context: Execution context
        prompt_path: Path expression (e.g., {{input}}, {{input.message}})
        join_strategy: Array handling strategy
        join_separator: Custom separator
        max_input_size: Max characters

    Returns:
        Resolved prompt string
    """
    # Try to use VariableResolver from SDK
    try:
        from core.engine.sdk.resolver import VariableResolver, ResolutionMode
        resolver = VariableResolver(context=context)
        raw_value = resolver.resolve(prompt_path, mode=ResolutionMode.RAW)
    except ImportError:
        # Fallback to simple resolution
        raw_value = _simple_resolve(context, prompt_path)

    if raw_value is None:
        return ''

    # Handle arrays based on join_strategy
    if isinstance(raw_value, (list, tuple)):
        return _join_array(raw_value, join_strategy, join_separator, max_input_size)

    # Convert to string
    return _stringify_value(raw_value, max_input_size)


def _simple_resolve(context: Dict[str, Any], path: str) -> Any:
    """
    Simple variable resolution fallback.

    Supports basic paths: {{input}}, {{input.field}}
    """
    import re

    # Extract path from {{...}}
    match = re.match(r'\{\{(.+?)\}\}', path.strip())
    if not match:
        return None

    path_str = match.group(1).strip()
    parts = path_str.split('.')

    # Start resolution
    if parts[0] == 'input':
        current = context.get('inputs', {}).get('input')
        if current is None:
            current = context.get('inputs', {}).get('main')
        parts = parts[1:]
    elif parts[0] == 'inputs':
        current = context.get('inputs', {})
        parts = parts[1:]
    else:
        current = context.get(parts[0])
        parts = parts[1:]

    # Navigate path
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

    return current


def _substitute_variables(
    template: str,
    context: Dict[str, Any],
    max_input_size: int,
) -> str:
    """
    Substitute {{...}} variables in a template string.

    Args:
        template: Template with {{...}} placeholders
        context: Execution context
        max_input_size: Max chars per substitution

    Returns:
        Template with variables substituted
    """
    import re

    def replacer(match: re.Match) -> str:
        path = '{{' + match.group(1) + '}}'
        value = _simple_resolve(context, path)
        if value is None:
            return match.group(0)  # Keep original if not found
        return _stringify_value(value, max_input_size)

    return re.sub(r'\{\{(.+?)\}\}', replacer, template)


def _join_array(
    arr: Union[List, tuple],
    strategy: str,
    separator: str,
    max_size: int,
) -> str:
    """
    Join array elements based on strategy.

    Args:
        arr: Array to join
        strategy: 'first', 'newline', 'separator', 'json'
        separator: Custom separator for 'separator' strategy
        max_size: Maximum output size

    Returns:
        Joined string
    """
    if not arr:
        return ''

    if strategy == 'first':
        return _stringify_value(arr[0], max_size)

    elif strategy == 'newline':
        items = [_stringify_value(item, max_size // len(arr)) for item in arr]
        return '\n'.join(items)[:max_size]

    elif strategy == 'separator':
        items = [_stringify_value(item, max_size // len(arr)) for item in arr]
        return separator.join(items)[:max_size]

    elif strategy == 'json':
        result = json.dumps(arr, ensure_ascii=False, indent=2)
        if len(result) > max_size:
            result = result[:max_size] + '\n... [truncated]'
        return result

    # Default to first
    return _stringify_value(arr[0], max_size)


def _stringify_value(value: Any, max_size: int) -> str:
    """
    Convert value to string with size limit.

    Args:
        value: Any value
        max_size: Maximum characters

    Returns:
        String representation
    """
    if value is None:
        return ''

    if isinstance(value, str):
        result = value
    elif isinstance(value, bool):
        result = 'true' if value else 'false'
    elif isinstance(value, (dict, list)):
        result = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        result = str(value)

    if len(result) > max_size:
        truncated = len(result) - max_size
        result = result[:max_size] + f'\n... [truncated, {truncated} chars omitted]'
        logger.warning(f'Value truncated to {max_size} chars')

    return result


# =============================================================================
# Module Registration
# =============================================================================

@register_module(
    module_id='llm.agent',
    stability="beta",
    version='2.0.0',  # Major version for multi-port architecture
    category='ai',
    subcategory='agent',
    tags=['llm', 'ai', 'agent', 'autonomous', 'tools', 'react', 'n8n-style'],
    label='AI Agent',
    label_key='modules.llm.agent.label',
    description='Autonomous AI agent with multi-port connections (model, memory, tools)',
    description_key='modules.llm.agent.description',
    icon='Bot',
    color='#8B5CF6',

    # n8n-style AI Agent node type
    node_type=NodeType.AI_AGENT,

    # Connection types - accepts AI sub-nodes and regular data
    input_types=['string', 'object', 'ai_model', 'ai_memory', 'ai_tool'],
    output_types=['string', 'object'],
    can_connect_to=['*'],
    can_receive_from=['*', 'ai.model', 'ai.memory'],
    can_be_start=True,  # Can be start node - task param provides input

    # Multiple input ports (n8n-style)
    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.llm.agent.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': False,
            'description': 'Main control flow input'
        },
        {
            'id': 'model',
            'label': 'Model',
            'label_key': 'modules.llm.agent.ports.model',
            'data_type': DataType.AI_MODEL.value,
            'edge_type': EdgeType.RESOURCE.value,
            'max_connections': 1,
            'required': False,
            'color': '#10B981',
            'description': 'Connect ai.model for LLM configuration'
        },
        {
            'id': 'memory',
            'label': 'Memory',
            'label_key': 'modules.llm.agent.ports.memory',
            'data_type': DataType.AI_MEMORY.value,
            'edge_type': EdgeType.RESOURCE.value,
            'max_connections': 1,
            'required': False,
            'color': '#8B5CF6',
            'description': 'Connect ai.memory for conversation history'
        },
        {
            'id': 'tools',
            'label': 'Tools',
            'label_key': 'modules.llm.agent.ports.tools',
            'data_type': DataType.AI_TOOL.value,
            'edge_type': EdgeType.RESOURCE.value,
            'max_connections': -1,  # Unlimited
            'required': False,
            'color': '#F59E0B',
            'description': 'Connect tool modules for agent to use'
        }
    ],

    # Output ports
    output_ports=[
        {
            'id': 'output',
            'label': 'Output',
            'label_key': 'modules.llm.agent.ports.output',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'color': '#10B981'
        },
        {
            'id': 'error',
            'label': 'Error',
            'label_key': 'common.ports.error',
            'data_type': DataType.OBJECT.value,
            'edge_type': EdgeType.CONTROL.value,
            'color': '#EF4444'
        }
    ],

    # Execution settings
    timeout_ms=300000,  # 5 minutes for agent tasks
    retryable=True,
    max_retries=1,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['shell.execute'],

    # Schema-driven params (model config can be overridden or from connected ai.model)
    params_schema=compose(
        # Prompt source configuration (n8n-style)
        field(
            'prompt_source',
            type='select',
            label='Prompt Source',
            label_key='modules.llm.agent.params.prompt_source',
            description='Where to get the task prompt from',
            description_key='modules.llm.agent.params.prompt_source.description',
            options=[
                {'label': 'Define below', 'value': 'manual'},
                {'label': 'From previous node', 'value': 'auto'},
            ],
            default='manual',
            required=False,
        ),
        field(
            'task',
            type='string',
            label='Task',
            label_key='modules.llm.agent.params.task',
            description='The task for the agent to complete. Use {{input}} to reference upstream data.',
            description_key='modules.llm.agent.params.task.description',
            required=False,  # Not required when prompt_source=auto
            format='multiline',
            placeholder='Analyze the following data: {{input}}',
            ui={'depends_on': {'prompt_source': 'manual'}},
        ),
        field(
            'prompt_path',
            type='string',
            label='Prompt Path',
            label_key='modules.llm.agent.params.prompt_path',
            description='Path to extract prompt from input (e.g., {{input.message}})',
            description_key='modules.llm.agent.params.prompt_path.description',
            default='{{input}}',
            required=False,
            ui={'visibility': 'advanced', 'depends_on': {'prompt_source': 'auto'}},
        ),
        field(
            'join_strategy',
            type='select',
            label='Array Join Strategy',
            label_key='modules.llm.agent.params.join_strategy',
            description='How to handle array inputs',
            description_key='modules.llm.agent.params.join_strategy.description',
            options=[
                {'label': 'First item only', 'value': 'first'},
                {'label': 'Join with newlines', 'value': 'newline'},
                {'label': 'Join with separator', 'value': 'separator'},
                {'label': 'As JSON array', 'value': 'json'},
            ],
            default='first',
            required=False,
            ui={'visibility': 'advanced', 'depends_on': {'prompt_source': 'auto'}},
        ),
        field(
            'join_separator',
            type='string',
            label='Join Separator',
            label_key='modules.llm.agent.params.join_separator',
            description='Separator for joining array items',
            description_key='modules.llm.agent.params.join_separator.description',
            default='\n\n---\n\n',
            required=False,
            ui={'visibility': 'advanced', 'depends_on': {'join_strategy': 'separator'}},
        ),
        field(
            'max_input_size',
            type='number',
            label='Max Input Size',
            label_key='modules.llm.agent.params.max_input_size',
            description='Maximum characters for prompt (prevents overflow)',
            description_key='modules.llm.agent.params.max_input_size.description',
            required=False,
            default=10000,
            min=100,
            max=100000,
            ui={'visibility': 'advanced'},
        ),
        field(
            'system_prompt',
            type='string',
            label='System Prompt',
            label_key='modules.llm.agent.params.system_prompt',
            description='Instructions for the agent behavior',
            description_key='modules.llm.agent.params.system_prompt.description',
            required=False,
            format='multiline',
            default='You are a helpful AI agent. Use the available tools to complete the task. Think step by step.'
        ),
        field(
            'tools',
            type='array',
            label='Available Tools',
            label_key='modules.llm.agent.params.tools',
            description='List of module IDs (alternative to connecting tool nodes)',
            description_key='modules.llm.agent.params.tools.description',
            required=False,
            default=[],
            ui={'component': 'tool_selector'}
        ),
        field(
            'context',
            type='object',
            label='Context',
            label_key='modules.llm.agent.params.context',
            description='Additional context data for the agent',
            description_key='modules.llm.agent.params.context.description',
            required=False,
            default={}
        ),
        field(
            'max_iterations',
            type='number',
            label='Max Iterations',
            label_key='modules.llm.agent.params.max_iterations',
            description='Maximum number of tool calls',
            description_key='modules.llm.agent.params.max_iterations.description',
            required=False,
            default=10,
            min=1,
            max=50
        ),
        # Fallback model config (used if no ai.model connected)
        presets.LLM_PROVIDER(default='openai'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.TEMPERATURE(default=0.3),
        presets.LLM_API_KEY(),
        presets.LLM_BASE_URL(),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the agent completed successfully'
        ,
                'description_key': 'modules.llm.agent.output.ok.description'},
        'result': {
            'type': 'string',
            'description': 'The final result from the agent'
        ,
                'description_key': 'modules.llm.agent.output.result.description'},
        'steps': {
            'type': 'array',
            'description': 'List of steps the agent took'
        ,
                'description_key': 'modules.llm.agent.output.steps.description'},
        'tool_calls': {
            'type': 'number',
            'description': 'Number of tools called'
        ,
                'description_key': 'modules.llm.agent.output.tool_calls.description'},
        'tokens_used': {
            'type': 'number',
            'description': 'Total tokens consumed'
        ,
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
    """
    Run an autonomous AI agent with tool use.

    Supports n8n-style multi-port connections:
    - model port: ai.model node for LLM config
    - memory port: ai.memory node for conversation history
    - tools port: connected tool modules

    Supports n8n-style prompt source:
    - manual: Use task param directly
    - auto: Resolve from input using prompt_path
    """
    params = context['params']
    system_prompt = params.get('system_prompt', 'You are a helpful AI agent.')
    tool_ids = params.get('tools', [])
    user_context = params.get('context', {}) or {}
    max_iterations = min(params.get('max_iterations', MAX_ITERATIONS), MAX_ITERATIONS)
    max_input_size = params.get('max_input_size', 10000)

    # Prompt source handling (n8n-style)
    prompt_source = params.get('prompt_source', 'manual')
    prompt_path = params.get('prompt_path', '{{input}}')
    join_strategy = params.get('join_strategy', 'first')
    join_separator = params.get('join_separator', '\n\n---\n\n')

    # Resolve task prompt based on source
    task = _resolve_task_prompt(
        context=context,
        params=params,
        prompt_source=prompt_source,
        prompt_path=prompt_path,
        join_strategy=join_strategy,
        join_separator=join_separator,
        max_input_size=max_input_size,
    )

    if not task:
        return {
            'ok': False,
            'error': 'No task prompt provided. Either set prompt_source to "manual" and provide a task, or connect an input node.',
            'error_code': 'MISSING_TASK'
        }

    # Store resolved input in context for reference
    main_input = context.get('inputs', {}).get('input')
    if main_input is not None:
        user_context['input'] = _stringify_value(main_input, max_input_size)

    # Get model config from connected ai.model or params
    model_input = context.get('inputs', {}).get('model')
    if model_input and model_input.get('__data_type__') == 'ai_model':
        # Use connected model configuration
        model_config = model_input.get('config', {})
        provider = model_config.get('provider', 'openai')
        model = model_config.get('model', 'gpt-4o')
        temperature = model_config.get('temperature', 0.3)
        api_key = model_config.get('api_key')
        base_url = model_config.get('base_url')
        logger.info(f"Using connected ai.model: {provider}/{model}")
    else:
        # Use params as fallback
        provider = params.get('provider', 'openai')
        model = params.get('model', 'gpt-4o')
        temperature = params.get('temperature', 0.3)
        api_key = params.get('api_key')
        base_url = params.get('base_url')

    # Get memory from connected ai.memory
    memory_input = context.get('inputs', {}).get('memory')
    conversation_history = []
    if memory_input and memory_input.get('__data_type__') == 'ai_memory':
        conversation_history = memory_input.get('messages', [])
        logger.info(f"Using connected ai.memory with {len(conversation_history)} messages")

    # Get tools from connected tool nodes
    tools_input = context.get('inputs', {}).get('tools')
    if tools_input:
        if isinstance(tools_input, list):
            # Multiple tool nodes connected
            for tool_data in tools_input:
                if tool_data.get('__data_type__') == 'ai_tool':
                    tool_ids.append(tool_data.get('module_id'))
        elif isinstance(tools_input, dict) and tools_input.get('__data_type__') == 'ai_tool':
            tool_ids.append(tools_input.get('module_id'))

    # Get API key from environment if not provided
    if not api_key:
        env_vars = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY'
        }
        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)

    if not api_key:
        return {
            'ok': False,
            'error': f'API key not provided for {provider}',
            'error_code': 'MISSING_API_KEY'
        }

    # Build tool definitions
    tools = await _build_tool_definitions(tool_ids)

    if not tools:
        logger.warning("No tools available for agent, running in chat-only mode")

    # Build initial messages
    messages = [
        {"role": "system", "content": _build_agent_system_prompt(system_prompt, tools)},
    ]

    # Add conversation history from memory if available
    if conversation_history:
        messages.extend(conversation_history)

    # Add current task
    messages.append({"role": "user", "content": _build_task_prompt(task, user_context)})

    steps = []
    total_tokens = 0
    tool_call_count = 0

    # Agent loop
    for iteration in range(max_iterations):
        logger.info(f"Agent iteration {iteration + 1}/{max_iterations}")

        # Call LLM
        if provider == 'openai':
            result = await _call_openai_with_tools(
                messages, tools, model, temperature, api_key, base_url
            )
        elif provider == 'anthropic':
            result = await _call_anthropic_with_tools(
                messages, tools, model, temperature, api_key
            )
        else:
            return {
                'ok': False,
                'error': f'Provider {provider} does not support tool use',
                'error_code': 'UNSUPPORTED_PROVIDER'
            }

        if not result.get('ok'):
            return result

        total_tokens += result.get('tokens_used', 0)

        # Check if agent wants to use a tool
        if result.get('tool_calls'):
            for tool_call in result['tool_calls']:
                tool_name = tool_call['name']
                tool_args = tool_call['arguments']

                steps.append({
                    'type': 'tool_call',
                    'tool': tool_name,
                    'arguments': tool_args,
                    'iteration': iteration + 1
                })

                logger.info(f"Agent calling tool: {tool_name}")
                tool_call_count += 1

                # Execute the tool
                tool_result = await _execute_tool(tool_name, tool_args, context)

                steps.append({
                    'type': 'tool_result',
                    'tool': tool_name,
                    'result': tool_result,
                    'iteration': iteration + 1
                })

                # Add tool result to messages
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get('id', tool_name),
                    "content": json.dumps(tool_result, ensure_ascii=False)
                })

        else:
            # Agent is done, return final response
            final_response = result.get('response', '')
            steps.append({
                'type': 'final_answer',
                'content': final_response,
                'iteration': iteration + 1
            })

            logger.info(f"Agent completed in {iteration + 1} iterations, {tool_call_count} tool calls")

            return {
                'ok': True,
                'result': final_response,
                'steps': steps,
                'tool_calls': tool_call_count,
                'tokens_used': total_tokens,
                'iterations': iteration + 1
            }

    # Max iterations reached
    logger.warning(f"Agent reached max iterations ({max_iterations})")
    return {
        'ok': True,
        'result': 'Agent reached maximum iterations without completing the task.',
        'steps': steps,
        'tool_calls': tool_call_count,
        'tokens_used': total_tokens,
        'iterations': max_iterations,
        'warning': 'max_iterations_reached'
    }


def _build_agent_system_prompt(base_prompt: str, tools: List[Dict]) -> str:
    """Build the system prompt for the agent"""
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


def _build_task_prompt(task: str, context: Dict) -> str:
    """Build the task prompt with context"""
    prompt = f"Task: {task}"

    if context:
        prompt += "\n\nContext:\n"
        for key, value in context.items():
            prompt += f"- {key}: {value}\n"

    return prompt


async def _build_tool_definitions(tool_ids: List[str]) -> List[Dict]:
    """Build OpenAI-compatible tool definitions from module IDs"""
    tools = []
    registry = get_registry()

    for tool_id in tool_ids:
        try:
            module_info = registry.get_module(tool_id)
            if not module_info:
                logger.warning(f"Tool not found: {tool_id}")
                continue

            # Build function definition
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
    """Convert flyto params schema to JSON Schema for OpenAI"""
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
    """Map flyto types to JSON Schema types"""
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


async def _execute_tool(tool_name: str, arguments: Dict, parent_context: Dict) -> Dict:
    """Execute a tool (module) and return results"""
    # Convert tool name back to module ID
    module_id = tool_name.replace('_', '.')

    registry = get_registry()
    module_func = registry.get_module_function(module_id)

    if not module_func:
        return {
            'ok': False,
            'error': f'Tool not found: {module_id}'
        }

    try:
        # Build context for tool execution
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


async def _call_openai_with_tools(
    messages: List[Dict],
    tools: List[Dict],
    model: str,
    temperature: float,
    api_key: str,
    base_url: Optional[str]
) -> Dict[str, Any]:
    """Call OpenAI API with tool support"""
    try:
        import httpx
    except ImportError:
        import aiohttp
        return await _call_openai_with_tools_aiohttp(messages, tools, model, temperature, api_key, base_url)

    url = base_url or "https://api.openai.com/v1"
    url = f"{url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

    choice = result['choices'][0]
    message = choice['message']

    # Check for tool calls
    if message.get('tool_calls'):
        tool_calls = []
        for tc in message['tool_calls']:
            tool_calls.append({
                'id': tc['id'],
                'name': tc['function']['name'],
                'arguments': json.loads(tc['function']['arguments'])
            })
        return {
            'ok': True,
            'tool_calls': tool_calls,
            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
        }

    return {
        'ok': True,
        'response': message.get('content', ''),
        'tokens_used': result.get('usage', {}).get('total_tokens', 0),
        'finish_reason': choice.get('finish_reason', 'stop')
    }


async def _call_openai_with_tools_aiohttp(
    messages: List[Dict],
    tools: List[Dict],
    model: str,
    temperature: float,
    api_key: str,
    base_url: Optional[str]
) -> Dict[str, Any]:
    """Call OpenAI API with tool support using aiohttp"""
    import aiohttp

    url = base_url or "https://api.openai.com/v1"
    url = f"{url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

    choice = result['choices'][0]
    message = choice['message']

    if message.get('tool_calls'):
        tool_calls = []
        for tc in message['tool_calls']:
            tool_calls.append({
                'id': tc['id'],
                'name': tc['function']['name'],
                'arguments': json.loads(tc['function']['arguments'])
            })
        return {
            'ok': True,
            'tool_calls': tool_calls,
            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
        }

    return {
        'ok': True,
        'response': message.get('content', ''),
        'tokens_used': result.get('usage', {}).get('total_tokens', 0),
        'finish_reason': choice.get('finish_reason', 'stop')
    }


async def _call_anthropic_with_tools(
    messages: List[Dict],
    tools: List[Dict],
    model: str,
    temperature: float,
    api_key: str
) -> Dict[str, Any]:
    """Call Anthropic API with tool support"""
    try:
        import httpx
        use_httpx = True
    except ImportError:
        import aiohttp
        use_httpx = False

    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    # Convert messages for Anthropic
    system = None
    anthropic_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            system = msg['content']
        elif msg['role'] == 'tool':
            # Convert tool result to Anthropic format
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get('tool_call_id', 'unknown'),
                    "content": msg['content']
                }]
            })
        elif msg.get('tool_calls'):
            # Convert assistant tool calls to Anthropic format
            content = []
            for tc in msg['tool_calls']:
                content.append({
                    "type": "tool_use",
                    "id": tc.get('id', tc['name']),
                    "name": tc['name'],
                    "input": tc['arguments']
                })
            anthropic_messages.append({"role": "assistant", "content": content})
        else:
            anthropic_messages.append(msg)

    # Convert tools to Anthropic format
    anthropic_tools = []
    for tool in tools:
        func = tool['function']
        anthropic_tools.append({
            "name": func['name'],
            "description": func['description'],
            "input_schema": func['parameters']
        })

    payload = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": 4096,
        "temperature": temperature
    }

    if system:
        payload["system"] = system
    if anthropic_tools:
        payload["tools"] = anthropic_tools

    if use_httpx:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            result = response.json()
    else:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                result = await response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

    # Check for tool use
    tool_calls = []
    text_content = ""

    for block in result.get('content', []):
        if block['type'] == 'tool_use':
            tool_calls.append({
                'id': block['id'],
                'name': block['name'],
                'arguments': block['input']
            })
        elif block['type'] == 'text':
            text_content += block['text']

    if tool_calls:
        return {
            'ok': True,
            'tool_calls': tool_calls,
            'tokens_used': result.get('usage', {}).get('input_tokens', 0) + result.get('usage', {}).get('output_tokens', 0)
        }

    return {
        'ok': True,
        'response': text_content,
        'tokens_used': result.get('usage', {}).get('input_tokens', 0) + result.get('usage', {}).get('output_tokens', 0),
        'finish_reason': result.get('stop_reason', 'end_turn')
    }
