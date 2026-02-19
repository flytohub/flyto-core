# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Queue Enqueue Module
Add an item to an in-memory or Redis queue.
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

# Module-level in-memory queue storage
_memory_queues: Dict[str, asyncio.Queue] = {}


def _get_memory_queue(name: str) -> asyncio.Queue:
    """Get or create an in-memory queue by name."""
    if name not in _memory_queues:
        _memory_queues[name] = asyncio.Queue()
    return _memory_queues[name]


@register_module(
    module_id='queue.enqueue',
    version='1.0.0',
    category='queue',
    tags=['queue', 'enqueue', 'push', 'message', 'buffer'],
    label='Enqueue Item',
    label_key='modules.queue.enqueue.label',
    description='Add an item to an in-memory or Redis queue',
    description_key='modules.queue.enqueue.description',
    icon='Layers',
    color='#EC4899',
    input_types=['any'],
    output_types=['json'],

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
            label_key='modules.queue.enqueue.params.queue_name.label',
            description='Name of the queue to add the item to',
            description_key='modules.queue.enqueue.params.queue_name.description',
            placeholder='my-queue',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'data',
            type='string',
            label='Data',
            label_key='modules.queue.enqueue.params.data.label',
            description='Data to enqueue (any JSON-serializable value)',
            description_key='modules.queue.enqueue.params.data.description',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.queue.enqueue.params.backend.label',
            description='Queue backend to use',
            description_key='modules.queue.enqueue.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.queue.enqueue.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.queue.enqueue.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': 'redis'},
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'queue_name': {
            'type': 'string',
            'description': 'Name of the queue',
            'description_key': 'modules.queue.enqueue.output.queue_name.description',
        },
        'position': {
            'type': 'number',
            'description': 'Position of the item in the queue',
            'description_key': 'modules.queue.enqueue.output.position.description',
        },
        'queue_size': {
            'type': 'number',
            'description': 'Current size of the queue after enqueue',
            'description_key': 'modules.queue.enqueue.output.queue_size.description',
        },
    },
    timeout_ms=30000,
)
async def queue_enqueue(context: Dict[str, Any]) -> Dict[str, Any]:
    """Add an item to a queue."""
    params = context['params']
    queue_name = params.get('queue_name')
    data = params.get('data')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')

    if not queue_name:
        raise ValidationError("Missing required parameter: queue_name", field="queue_name")
    if data is None:
        raise ValidationError("Missing required parameter: data", field="data")

    if backend == 'memory':
        q = _get_memory_queue(queue_name)
        await q.put(data)
        queue_size = q.qsize()
        position = queue_size  # position is at the end

        return {
            'ok': True,
            'data': {
                'queue_name': queue_name,
                'position': position,
                'queue_size': queue_size,
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
                serialized = json.dumps(data)
                queue_size = await client.rpush(queue_name, serialized)
                position = queue_size

                return {
                    'ok': True,
                    'data': {
                        'queue_name': queue_name,
                        'position': position,
                        'queue_size': queue_size,
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis enqueue failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
