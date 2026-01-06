"""
AI Redis Memory Sub-Node
Persistent memory storage using Redis for AI Agent

Provides persistent conversation memory across sessions
using Redis as the backend storage.
"""

from typing import Any, Dict, List, Optional
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.memory.redis',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='memory',
    tags=['ai', 'memory', 'redis', 'persistent', 'cache', 'database', 'sub-node'],
    label='Redis Memory',
    label_key='modules.ai.memory.redis.label',
    description='Persistent conversation memory using Redis storage',
    description_key='modules.ai.memory.redis.description',
    icon='Database',
    color='#DC2626',

    node_type=NodeType.AI_SUB_NODE,
    input_types=[],
    output_types=['ai_memory'],
    can_receive_from=[],
    can_connect_to=['llm.agent'],
    input_ports=[],

    output_ports=[
        {
            'id': 'memory',
            'label': 'Memory',
            'label_key': 'modules.ai.memory.redis.ports.memory',
            'data_type': DataType.AI_MEMORY.value,
            'edge_type': EdgeType.RESOURCE.value,
            'color': '#DC2626'
        }
    ],

    retryable=True,
    concurrent_safe=True,
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['ai.memory', 'database.redis'],

    params_schema=compose(
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.ai.memory.redis.params.redis_url',
            description='Redis connection URL',
            required=True,
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379'
        ),
        field(
            'key_prefix',
            type='string',
            label='Key Prefix',
            label_key='modules.ai.memory.redis.params.key_prefix',
            description='Prefix for all Redis keys',
            required=False,
            default='flyto:memory:',
            placeholder='flyto:memory:'
        ),
        field(
            'session_id',
            type='string',
            label='Session ID',
            label_key='modules.ai.memory.redis.params.session_id',
            description='Unique identifier for this memory session',
            required=True,
            default='',
            placeholder='user-123-session-456'
        ),
        field(
            'ttl_seconds',
            type='number',
            label='TTL (seconds)',
            label_key='modules.ai.memory.redis.params.ttl_seconds',
            description='Time-to-live for memory entries (0 = no expiry)',
            required=False,
            default=86400,
            min=0,
            max=2592000
        ),
        field(
            'max_messages',
            type='number',
            label='Max Messages',
            label_key='modules.ai.memory.redis.params.max_messages',
            description='Maximum messages to store per session',
            required=False,
            default=100,
            min=10,
            max=10000
        ),
        field(
            'load_on_start',
            type='boolean',
            label='Load on Start',
            label_key='modules.ai.memory.redis.params.load_on_start',
            description='Load existing messages from Redis on initialization',
            required=False,
            default=True
        ),
    ),

    output_schema={
        'memory_type': {'type': 'string', 'description': 'Type of memory (redis)'},
        'session_id': {'type': 'string', 'description': 'Session identifier'},
        'messages': {'type': 'array', 'description': 'Loaded message history'},
        'connected': {'type': 'boolean', 'description': 'Redis connection status'},
        'config': {'type': 'object', 'description': 'Full memory configuration'}
    },

    examples=[
        {
            'title': 'Local Redis',
            'params': {
                'redis_url': 'redis://localhost:6379',
                'session_id': 'my-session',
                'ttl_seconds': 3600
            }
        },
        {
            'title': 'Cloud Redis with Auth',
            'params': {
                'redis_url': 'redis://:password@redis-cloud.example.com:6379',
                'session_id': 'user-session',
                'ttl_seconds': 86400,
                'max_messages': 500
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ai_memory_redis(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redis-backed persistent memory for AI Agent.

    Stores conversation history in Redis for persistence
    across sessions and restarts.
    """
    import json

    params = context['params']
    redis_url = params.get('redis_url', 'redis://localhost:6379')
    key_prefix = params.get('key_prefix', 'flyto:memory:')
    session_id = params.get('session_id', '')
    ttl_seconds = params.get('ttl_seconds', 86400)
    max_messages = params.get('max_messages', 100)
    load_on_start = params.get('load_on_start', True)

    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())

    # Build Redis key
    memory_key = f"{key_prefix}{session_id}"

    # Initialize Redis client (lazy loading)
    redis_client = None
    connected = False
    messages = []

    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        connected = True

        # Load existing messages if configured
        if load_on_start:
            stored = await redis_client.lrange(memory_key, 0, -1)
            messages = [json.loads(m) for m in stored]

    except ImportError:
        # redis package not installed, use in-memory fallback
        pass
    except Exception as e:
        # Connection failed, use in-memory fallback
        pass

    config = {
        'memory_type': 'redis',
        'session_id': session_id,
        'redis_url': redis_url,
        'key_prefix': key_prefix,
        'memory_key': memory_key,
        'ttl_seconds': ttl_seconds,
        'max_messages': max_messages
    }

    return {
        'ok': True,
        '__data_type__': 'ai_memory',
        'memory_type': 'redis',
        'session_id': session_id,
        'messages': messages,
        'connected': connected,
        '_redis_client': redis_client,
        'config': config,
        '__methods__': {
            'add_message': '_redis_add_message',
            'get_messages': '_redis_get_messages',
            'clear': '_redis_clear',
            'get_session_info': '_redis_get_session_info'
        }
    }


async def _redis_add_message(memory_state: Dict, role: str, content: str) -> None:
    """Add a message to Redis memory"""
    import json
    import time

    config = memory_state['config']
    client = memory_state.get('_redis_client')

    message = {
        'role': role,
        'content': content,
        'timestamp': time.time()
    }

    # Add to local cache
    memory_state['messages'].append(message)

    # Persist to Redis if connected
    if client:
        try:
            memory_key = config['memory_key']
            ttl = config['ttl_seconds']
            max_msgs = config['max_messages']

            # Push message
            await client.rpush(memory_key, json.dumps(message))

            # Trim to max messages
            await client.ltrim(memory_key, -max_msgs, -1)

            # Set TTL if configured
            if ttl > 0:
                await client.expire(memory_key, ttl)

        except Exception:
            # Redis operation failed, message still in local cache
            pass


async def _redis_get_messages(memory_state: Dict, limit: int = None) -> List[Dict]:
    """Get messages from Redis memory"""
    import json

    client = memory_state.get('_redis_client')
    config = memory_state['config']

    if client:
        try:
            memory_key = config['memory_key']
            if limit:
                stored = await client.lrange(memory_key, -limit, -1)
            else:
                stored = await client.lrange(memory_key, 0, -1)
            return [json.loads(m) for m in stored]
        except Exception:
            pass

    # Fallback to local cache
    if limit:
        return memory_state['messages'][-limit:]
    return memory_state['messages']


async def _redis_clear(memory_state: Dict) -> None:
    """Clear all messages from Redis memory"""
    client = memory_state.get('_redis_client')
    config = memory_state['config']

    memory_state['messages'] = []

    if client:
        try:
            await client.delete(config['memory_key'])
        except Exception:
            pass


async def _redis_get_session_info(memory_state: Dict) -> Dict:
    """Get session info from Redis"""
    client = memory_state.get('_redis_client')
    config = memory_state['config']

    info = {
        'session_id': config['session_id'],
        'connected': client is not None,
        'message_count': len(memory_state['messages'])
    }

    if client:
        try:
            memory_key = config['memory_key']
            info['message_count'] = await client.llen(memory_key)
            info['ttl'] = await client.ttl(memory_key)
        except Exception:
            pass

    return info
