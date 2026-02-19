# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Delete Module
Delete a cache entry by key.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Import shared memory cache storage
from .get import _memory_cache


@register_module(
    module_id='cache.delete',
    version='1.0.0',
    category='cache',
    tags=['cache', 'delete', 'remove', 'invalidate', 'key-value'],
    label='Cache Delete',
    label_key='modules.cache.delete.label',
    description='Delete a cache entry by key',
    description_key='modules.cache.delete.description',
    icon='Database',
    color='#F59E0B',
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
            'key',
            type='string',
            label='Cache Key',
            label_key='modules.cache.delete.params.key.label',
            description='The cache key to delete',
            description_key='modules.cache.delete.params.key.description',
            placeholder='my-cache-key',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.cache.delete.params.backend.label',
            description='Cache backend to use',
            description_key='modules.cache.delete.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.cache.delete.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.cache.delete.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': 'redis'},
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'key': {
            'type': 'string',
            'description': 'The cache key',
            'description_key': 'modules.cache.delete.output.key.description',
        },
        'deleted': {
            'type': 'boolean',
            'description': 'Whether the key was found and deleted',
            'description_key': 'modules.cache.delete.output.deleted.description',
        },
        'backend': {
            'type': 'string',
            'description': 'The backend used',
            'description_key': 'modules.cache.delete.output.backend.description',
        },
    },
    timeout_ms=10000,
)
async def cache_delete(context: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a cache entry by key."""
    params = context['params']
    key = params.get('key')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')

    if not key:
        raise ValidationError("Missing required parameter: key", field="key")

    if backend == 'memory':
        deleted = key in _memory_cache
        if deleted:
            del _memory_cache[key]

        return {
            'ok': True,
            'data': {
                'key': key,
                'deleted': deleted,
                'backend': 'memory',
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
                result = await client.delete(key)
                deleted = result > 0

                return {
                    'ok': True,
                    'data': {
                        'key': key,
                        'deleted': deleted,
                        'backend': 'redis',
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis cache delete failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
