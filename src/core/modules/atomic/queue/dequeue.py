"""
Queue Dequeue Module
Remove and return an item from an in-memory or Redis queue.
"""
import asyncio
import json
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Import shared memory queue storage
from .enqueue import _memory_queues, _get_memory_queue


@register_module(
    module_id='queue.dequeue',
    version='1.0.0',
    category='queue',
    tags=['queue', 'dequeue', 'pop', 'consume', 'message'],
    label='Dequeue Item',
    label_key='modules.queue.dequeue.label',
    description='Remove and return an item from a queue',
    description_key='modules.queue.dequeue.description',
    icon='Layers',
    color='#EC4899',
    input_types=['string'],
    output_types=['any', 'json'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'queue_name',
            type='string',
            label='Queue Name',
            label_key='modules.queue.dequeue.params.queue_name.label',
            description='Name of the queue to dequeue from',
            description_key='modules.queue.dequeue.params.queue_name.description',
            placeholder='my-queue',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.queue.dequeue.params.backend.label',
            description='Queue backend to use',
            description_key='modules.queue.dequeue.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.queue.dequeue.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.queue.dequeue.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': 'redis'},
            group=FieldGroup.CONNECTION,
        ),
        field(
            'timeout',
            type='number',
            label='Timeout',
            label_key='modules.queue.dequeue.params.timeout.label',
            description='Timeout in seconds (0 = non-blocking)',
            description_key='modules.queue.dequeue.params.timeout.description',
            default=0,
            min=0,
            max=300,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'data': {
            'type': 'any',
            'description': 'The dequeued item (null if queue is empty)',
            'description_key': 'modules.queue.dequeue.output.data.description',
        },
        'queue_name': {
            'type': 'string',
            'description': 'Name of the queue',
            'description_key': 'modules.queue.dequeue.output.queue_name.description',
        },
        'remaining': {
            'type': 'number',
            'description': 'Remaining items in the queue',
            'description_key': 'modules.queue.dequeue.output.remaining.description',
        },
        'empty': {
            'type': 'boolean',
            'description': 'Whether the queue was empty',
            'description_key': 'modules.queue.dequeue.output.empty.description',
        },
    },
    timeout_ms=310000,  # slightly more than max timeout (300s + 10s buffer)
)
async def queue_dequeue(context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove and return an item from a queue."""
    params = context['params']
    queue_name = params.get('queue_name')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')
    timeout = int(params.get('timeout', 0) or 0)

    if not queue_name:
        raise ValidationError("Missing required parameter: queue_name", field="queue_name")

    if backend == 'memory':
        q = _get_memory_queue(queue_name)

        if timeout == 0:
            # Non-blocking
            try:
                item = q.get_nowait()
            except asyncio.QueueEmpty:
                return {
                    'ok': True,
                    'data': {
                        'data': None,
                        'queue_name': queue_name,
                        'remaining': 0,
                        'empty': True,
                    }
                }
        else:
            # Blocking with timeout
            try:
                item = await asyncio.wait_for(q.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return {
                    'ok': True,
                    'data': {
                        'data': None,
                        'queue_name': queue_name,
                        'remaining': q.qsize(),
                        'empty': True,
                    }
                }

        return {
            'ok': True,
            'data': {
                'data': item,
                'queue_name': queue_name,
                'remaining': q.qsize(),
                'empty': False,
            }
        }

    elif backend == 'redis':
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ModuleError(
                "Redis backend requires the 'redis' package. Install with: pip install redis",
                hint="pip install redis"
            )

        try:
            client = aioredis.from_url(redis_url)
            try:
                if timeout == 0:
                    # Non-blocking: LPOP
                    raw = await client.lpop(queue_name)
                else:
                    # Blocking: BLPOP with timeout
                    result = await client.blpop(queue_name, timeout=timeout)
                    raw = result[1] if result else None

                if raw is None:
                    remaining = await client.llen(queue_name)
                    return {
                        'ok': True,
                        'data': {
                            'data': None,
                            'queue_name': queue_name,
                            'remaining': remaining,
                            'empty': True,
                        }
                    }

                # Deserialize JSON
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8')
                    item = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    item = raw

                remaining = await client.llen(queue_name)

                return {
                    'ok': True,
                    'data': {
                        'data': item,
                        'queue_name': queue_name,
                        'remaining': remaining,
                        'empty': False,
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis dequeue failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
