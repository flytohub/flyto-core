"""
AI Memory Sub-Node
Conversation memory for AI Agent (n8n-style)

This is a "sub-node" that connects to AI Agent via RESOURCE edge.
It provides conversation history/memory without affecting control flow.
"""

from typing import Any, Dict, List, Optional
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.memory',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='sub_node',
    tags=['ai', 'memory', 'conversation', 'history', 'context', 'sub-node'],
    label='AI Memory',
    label_key='modules.ai.memory.label',
    description='Conversation memory for AI Agent',
    description_key='modules.ai.memory.description',
    icon='Brain',
    color='#8B5CF6',

    # This is a sub-node type
    node_type=NodeType.AI_SUB_NODE,

    # No control flow input - this is a resource provider
    input_types=[],
    output_types=['ai_memory'],

    # Can only connect to AI Agent's memory port
    can_receive_from=[],
    can_connect_to=['llm.agent'],

    # No input ports (standalone configuration node)
    input_ports=[],

    # Single output port for memory
    output_ports=[
        {
            'id': 'memory',
            'label': 'Memory',
            'label_key': 'modules.ai.memory.ports.memory',
            'data_type': DataType.AI_MEMORY.value,
            'edge_type': EdgeType.RESOURCE.value,
            'color': '#8B5CF6'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read'],

    params_schema=compose(
        field(
            'memory_type',
            type='select',
            label='Memory Type',
            label_key='modules.ai.memory.params.memory_type',
            description='Type of memory storage',
            description_key='modules.ai.memory.params.memory_type.description',
            required=True,
            default='buffer',
            options=[
                {'value': 'buffer', 'label': 'Buffer Memory', 'label_key': 'modules.ai.memory.options.buffer'},
                {'value': 'window', 'label': 'Window Memory', 'label_key': 'modules.ai.memory.options.window'},
                {'value': 'summary', 'label': 'Summary Memory', 'label_key': 'modules.ai.memory.options.summary'},
            ]
        ),
        field(
            'window_size',
            type='number',
            label='Window Size',
            label_key='modules.ai.memory.params.window_size',
            description='Number of recent messages to keep (for window memory)',
            description_key='modules.ai.memory.params.window_size.description',
            required=False,
            default=10,
            min=1,
            max=100,
            condition={'memory_type': 'window'}
        ),
        field(
            'session_id',
            type='string',
            label='Session ID',
            label_key='modules.ai.memory.params.session_id',
            description='Unique identifier for this conversation session',
            description_key='modules.ai.memory.params.session_id.description',
            required=False,
            default='',
            placeholder='Leave empty to auto-generate'
        ),
        field(
            'initial_messages',
            type='array',
            label='Initial Messages',
            label_key='modules.ai.memory.params.initial_messages',
            description='Pre-loaded conversation history',
            description_key='modules.ai.memory.params.initial_messages.description',
            required=False,
            default=[]
        ),
    ),

    output_schema={
        'memory_type': {'type': 'string', 'description': 'Type of memory',
                'description_key': 'modules.ai.memory.output.memory_type.description'},
        'session_id': {'type': 'string', 'description': 'Session identifier',
                'description_key': 'modules.ai.memory.output.session_id.description'},
        'messages': {'type': 'array', 'description': 'Current message history',
                'description_key': 'modules.ai.memory.output.messages.description'},
        'config': {'type': 'object', 'description': 'Full memory configuration',
                'description_key': 'modules.ai.memory.output.config.description'}
    },

    examples=[
        {
            'title': 'Simple Buffer Memory',
            'title_key': 'modules.ai.memory.examples.buffer.title',
            'params': {
                'memory_type': 'buffer'
            }
        },
        {
            'title': 'Window Memory (last 5 messages)',
            'title_key': 'modules.ai.memory.examples.window.title',
            'params': {
                'memory_type': 'window',
                'window_size': 5
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
)
async def ai_memory(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide conversation memory for AI Agent.

    This module manages conversation history and provides it to
    connected AI Agent nodes via RESOURCE edge.
    """
    import uuid

    params = context['params']
    memory_type = params.get('memory_type', 'buffer')
    window_size = params.get('window_size', 10)
    session_id = params.get('session_id') or str(uuid.uuid4())
    initial_messages = params.get('initial_messages', [])

    # Get existing messages from context (if any)
    existing_messages = context.get('memory_messages', [])

    # Combine initial and existing messages
    messages = initial_messages + existing_messages

    # Apply window if needed
    if memory_type == 'window' and len(messages) > window_size:
        messages = messages[-window_size:]

    # Build memory configuration
    config = {
        'memory_type': memory_type,
        'session_id': session_id,
        'window_size': window_size if memory_type == 'window' else None,
    }

    return {
        'ok': True,
        '__data_type__': 'ai_memory',
        'memory_type': memory_type,
        'session_id': session_id,
        'messages': messages,
        'config': config,
        # Methods for AI Agent to use
        '__methods__': {
            'add_message': '_memory_add_message',
            'get_messages': '_memory_get_messages',
            'clear': '_memory_clear'
        }
    }


def _memory_add_message(memory_state: Dict, role: str, content: str) -> None:
    """Add a message to memory"""
    memory_state['messages'].append({
        'role': role,
        'content': content
    })

    # Apply window limit
    if memory_state['config']['memory_type'] == 'window':
        window_size = memory_state['config']['window_size']
        if len(memory_state['messages']) > window_size:
            memory_state['messages'] = memory_state['messages'][-window_size:]


def _memory_get_messages(memory_state: Dict) -> List[Dict]:
    """Get all messages from memory"""
    return memory_state.get('messages', [])


def _memory_clear(memory_state: Dict) -> None:
    """Clear all messages from memory"""
    memory_state['messages'] = []
