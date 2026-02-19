# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Clear Module
Clear all cache entries, optionally filtered by a glob pattern.
"""
import fnmatch
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
    module_id='cache.clear',
    version='1.0.0',
    category='cache',
    tags=['cache', 'clear', 'flush', 'purge', 'invalidate'],
    label='Cache Clear',
    label_key='modules.cache.clear.label',
    description='Clear all cache entries or filter by pattern',
    description_key='modules.cache.clear.description',
    icon='Database',
    color='#F59E0B',
    input_types=['string'],
    output_types=['json'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    retryable=True,
    concurrent_safe=False,  # clearing is not safe to run concurrently

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'pattern',
            type='string',
            label='Pattern',
            label_key='modules.cache.clear.params.pattern.label',
            description='Glob pattern to match keys (e.g. "user:*", default "*" clears all)',
            description_key='modules.cache.clear.params.pattern.description',
            default='*',
            placeholder='*',
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.cache.clear.params.backend.label',
            description='Cache backend to use',
            description_key='modules.cache.clear.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.cache.clear.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.cache.clear.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': 'redis'},
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'cleared_count': {
            'type': 'number',
            'description': 'Number of cache entries cleared',
            'description_key': 'modules.cache.clear.output.cleared_count.description',
        },
        'backend': {
            'type': 'string',
            'description': 'The backend used',
            'description_key': 'modules.cache.clear.output.backend.description',
        },
    },
    timeout_ms=30000,
)
async def cache_clear(context: Dict[str, Any]) -> Dict[str, Any]:
    """Clear all cache entries or filter by pattern."""
    params = context['params']
    pattern = params.get('pattern', '*')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')

    if backend == 'memory':
        if pattern == '*':
            cleared_count = len(_memory_cache)
            _memory_cache.clear()
        else:
            keys_to_delete = [
                k for k in list(_memory_cache.keys())
                if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_delete:
                del _memory_cache[k]
            cleared_count = len(keys_to_delete)

        return {
            'ok': True,
            'data': {
                'cleared_count': cleared_count,
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
                cleared_count = 0

                if pattern == '*':
                    # FLUSHDB is too destructive; use SCAN instead
                    cursor = 0
                    while True:
                        cursor, keys = await client.scan(cursor=cursor, match='*', count=100)
                        if keys:
                            cleared_count += await client.delete(*keys)
                        if cursor == 0:
                            break
                else:
                    # Use SCAN with pattern to find matching keys
                    cursor = 0
                    while True:
                        cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
                        if keys:
                            cleared_count += await client.delete(*keys)
                        if cursor == 0:
                            break

                return {
                    'ok': True,
                    'data': {
                        'cleared_count': cleared_count,
                        'backend': 'redis',
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis cache clear failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
