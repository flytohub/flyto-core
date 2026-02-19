# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Queue Size Module
Get the current size of a queue.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Import shared memory queue storage
from .enqueue import _memory_queues


@register_module(
    module_id='queue.size',
    version='1.0.0',
    category='queue',
    tags=['queue', 'size', 'length', 'count', 'status'],
    label='Queue Size',
    label_key='modules.queue.size.label',
    description='Get the current size of a queue',
    description_key='modules.queue.size.description',
    icon='Layers',
    color='#EC4899',
    input_types=['string'],
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
            label_key='modules.queue.size.params.queue_name.label',
            description='Name of the queue to check',
            description_key='modules.queue.size.params.queue_name.description',
            placeholder='my-queue',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.queue.size.params.backend.label',
            description='Queue backend to use',
            description_key='modules.queue.size.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.queue.size.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.queue.size.params.redis_url.description',
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
            'description_key': 'modules.queue.size.output.queue_name.description',
        },
        'size': {
            'type': 'number',
            'description': 'Current number of items in the queue',
            'description_key': 'modules.queue.size.output.size.description',
        },
    },
    timeout_ms=10000,
)
async def queue_size(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get the current size of a queue."""
    params = context['params']
    queue_name = params.get('queue_name')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')

    if not queue_name:
        raise ValidationError("Missing required parameter: queue_name", field="queue_name")

    if backend == 'memory':
        if queue_name in _memory_queues:
            size = _memory_queues[queue_name].qsize()
        else:
            size = 0

        return {
            'ok': True,
            'data': {
                'queue_name': queue_name,
                'size': size,
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
                size = await client.llen(queue_name)
                return {
                    'ok': True,
                    'data': {
                        'queue_name': queue_name,
                        'size': size,
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis queue size check failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
