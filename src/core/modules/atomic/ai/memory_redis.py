# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Redis Memory Sub-Node
Persistent memory storage using Redis for AI Agent

Provides persistent conversation memory across sessions
using Redis as the backend storage.

HOW FAR THIS MODULE FOLLOWS REALITY

This is the only module in the ai/llm group that touches durable external state,
and it has no single rung. Four answers, decided per run from what actually
happened:

  connected, and messages came back                     OBSERVED
      `messages` are entries an earlier run wrote, sent back by the server and
      deserialised here. Rows off the wire are an observation of those rows --
      the same reasoning `database.query` uses, and the same limit: it observes
      the history, not that anything was stored this time.

  connected, and the list came back empty               ACCEPTED
      `len(messages) == 0` reads identically whether the session is new, the key
      expired under its TTL, or somebody flushed the database. A value that
      would be unchanged if the effect had not happened is not evidence of it.
      The PING round trip is what is left, and a PONG is the peer acknowledging.

  connected, load_on_start=False                        ACCEPTED
      Nothing was read because nothing was asked for. The PING still answered.

  redis unreachable, or the read failed                 INDETERMINATE
      Not FAILED. `outcome.py` names a severed observation channel as the
      textbook indeterminate, and that is exactly the state: `messages` is
      handed to the agent as `[]`, and there may be fifty messages in that key
      that we could not read. The agent will proceed as though the conversation
      is new. Nothing here can say whether it is.

A DEFECT THIS EXPOSES RATHER THAN FIXES. Both `except` clauses below swallow the
failure and return `ok: True` with `connected: False`, so a workflow that asked
for persistent memory silently gets a non-persistent one -- and the fallback is
worse than it looks, because `redis_client` is left bound whenever `from_url`
succeeded and only `ping()` failed, so `_redis_add_message` keeps trying to write
through a client we already know does not work. The reason is now captured
instead of discarded, and it travels in the envelope; changing `ok` is a
behaviour change and not an outcome declaration.
"""

from contextlib import suppress
from typing import Any, Dict, List, Optional

from ....engine.outcome import Outcome, envelope
from ....utils import enforce_outbound_service_url
from ...registry import register_module
from ...schema import compose, field
from ...types import DataType, EdgeType, NodeType


def _memory_outcome(
    *,
    connected: bool,
    loaded: bool,
    message_count: int,
    load_on_start: bool,
    failure: Optional[str],
) -> Dict[str, Any]:
    """The rung this session load earned, decided from what answered."""
    if failure is not None:
        return envelope(
            Outcome.INDETERMINATE,
            effects=[{
                'kind': 'memory_not_read',
                'connected': connected,
                'reason': failure,
                'measured_by': None,
                'detail': (
                    'The stored history could not be read. `messages` is empty '
                    'because we could not look, not because the session is new, '
                    'and this module cannot tell those apart. Anything downstream '
                    'that treats an empty history as "first turn" is guessing.'
                ),
            }],
        )

    if not load_on_start:
        return envelope(
            Outcome.ACCEPTED,
            effects=[{
                'kind': 'connection_acknowledged',
                'measured_by': 'a PING that the server answered',
                'detail': (
                    'The server acknowledged the connection. load_on_start is '
                    'off, so nothing was read and nothing about the stored '
                    'history is claimed.'
                ),
            }],
        )

    if loaded and message_count > 0:
        return envelope(
            Outcome.OBSERVED,
            effects=[{
                'kind': 'messages_read',
                'count': message_count,
                'measured_by': 'len() over the entries LRANGE returned from the server',
                'detail': (
                    'These entries were stored by an earlier run and came back off '
                    'the wire. That observes the history that exists; it does not '
                    'observe anything this step wrote, because this step writes '
                    'nothing.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        effects=[{
            'kind': 'no_messages_read',
            'count': 0,
            'measured_by': None,
            'detail': (
                'LRANGE answered with an empty list. That reads the same whether '
                'the session is new, the key expired under its TTL, or the '
                'database was flushed, so it is not an observation of the stored '
                'history. What is left is that the server answered.'
            ),
        }],
    )


@register_module(
    module_id='ai.memory.redis',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='memory',
    tags=[
        'ai', 'memory', 'redis', 'persistent', 'cache', 'database',
        'sub-node', 'ssrf_protected',
    ],
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
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.ai.memory.redis.params.redis_url',
            description='Redis connection URL',
            format="url",
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
        'memory_type': {'type': 'string', 'description': 'Type of memory (redis)',
                'description_key': 'modules.ai.memory.redis.output.memory_type.description'},
        'session_id': {'type': 'string', 'description': 'Session identifier',
                'description_key': 'modules.ai.memory.redis.output.session_id.description'},
        'messages': {'type': 'array', 'description': 'Loaded message history',
                'description_key': 'modules.ai.memory.redis.output.messages.description'},
        'connected': {'type': 'boolean', 'description': 'Redis connection status',
                'description_key': 'modules.ai.memory.redis.output.connected.description'},
        'config': {'type': 'object', 'description': 'Full memory configuration',
                'description_key': 'modules.ai.memory.redis.output.config.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far the stored history was followed: observed when '
                    'messages came back off the wire, accepted when the server '
                    'answered but nothing was read, indeterminate when redis '
                    'could not be reached and an empty history was handed over '
                    'in its place'
                ),
                'description_key': 'modules.ai.memory.redis.output.outcome.description'}
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
                'redis_url': 'redis://cache.flyto2.com:6379',
                'session_id': 'user-session',
                'ttl_seconds': 86400,
                'max_messages': 500
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
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
    redis_url = enforce_outbound_service_url(redis_url, purpose='Redis memory')
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
    # Why the store could not be read, or None when it was. Previously both
    # handlers were a bare `pass`: the failure was discarded, `connected: False`
    # was the only trace of it, and nothing downstream could tell "no history"
    # from "could not look". The envelope needs that distinction, so the reason
    # is kept rather than dropped.
    failure = None
    # Whether an LRANGE actually answered. Separate from `connected` because a
    # PING can succeed and the read still fail, and those are different claims.
    loaded = False

    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        connected = True

        # Load existing messages if configured
        if load_on_start:
            stored = await redis_client.lrange(memory_key, 0, -1)
            messages = [json.loads(m) for m in stored]
            loaded = True

    except ImportError:
        # redis package not installed, use in-memory fallback
        failure = 'the redis package is not installed'
    except Exception as e:
        # Connection failed, use in-memory fallback
        failure = f'{type(e).__name__}: {e}'

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
        # A flat result with no `data` key, so the envelope goes at the top
        # level: `wrap_legacy_result` sweeps these fields into data and
        # `_apply_outcome_contract` reads exactly this dict.
        'outcome': _memory_outcome(
            connected=connected,
            loaded=loaded,
            message_count=len(messages),
            load_on_start=load_on_start,
            failure=failure,
        ),
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
        with suppress(Exception):
            await client.delete(config['memory_key'])


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
