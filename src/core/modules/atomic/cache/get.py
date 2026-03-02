# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Get Module
Get a value from an in-memory or Redis cache.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Module-level in-memory cache storage
# Structure: {key: {'value': any, 'expires_at': float or None}}
_memory_cache: Dict[str, Dict[str, Any]] = {}


def _cache_get(key: str) -> Optional[Any]:
    """Get a value from the memory cache, respecting TTL."""
    entry = _memory_cache.get(key)
    if entry is None:
        return None

    expires_at = entry.get('expires_at')
    if expires_at is not None and time.time() > expires_at:
        # Expired — remove and return None
        del _memory_cache[key]
        return None

    return entry.get('value')


def _cache_has(key: str) -> bool:
    """Check if a key exists in memory cache (respecting TTL)."""
    return _cache_get(key) is not None


@register_module(
    module_id='cache.get',
    version='1.0.0',
    category='cache',
    tags=['cache', 'get', 'read', 'lookup', 'key-value'],
    label='Cache Get',
    label_key='modules.cache.get.label',
    description='Get a value from cache by key',
    description_key='modules.cache.get.description',
    icon='Database',
    color='#F59E0B',
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
            'key',
            type='string',
            label='Cache Key',
            label_key='modules.cache.get.params.key.label',
            description='The cache key to look up',
            description_key='modules.cache.get.params.key.description',
            placeholder='my-cache-key',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.cache.get.params.backend.label',
            description='Cache backend to use',
            description_key='modules.cache.get.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.cache.get.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.cache.get.params.redis_url.description',
            default='redis://localhost:6379',
            placeholder='redis://localhost:6379',
            showIf={'backend': {'$in': ['redis']}},
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'key': {
            'type': 'string',
            'description': 'The cache key',
            'description_key': 'modules.cache.get.output.key.description',
        },
        'value': {
            'type': 'any',
            'description': 'The cached value (null if not found)',
            'description_key': 'modules.cache.get.output.value.description',
        },
        'hit': {
            'type': 'boolean',
            'description': 'Whether the key was found in cache',
            'description_key': 'modules.cache.get.output.hit.description',
        },
        'backend': {
            'type': 'string',
            'description': 'The backend used',
            'description_key': 'modules.cache.get.output.backend.description',
        },
    },
    timeout_ms=10000,
)
async def cache_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get a value from cache by key."""
    params = context['params']
    key = params.get('key')
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')

    if not key:
        raise ValidationError("Missing required parameter: key", field="key")

    if backend == 'memory':
        value = _cache_get(key)
        hit = value is not None

        return {
            'ok': True,
            'data': {
                'key': key,
                'value': value,
                'hit': hit,
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
                raw = await client.get(key)

                if raw is None:
                    return {
                        'ok': True,
                        'data': {
                            'key': key,
                            'value': None,
                            'hit': False,
                            'backend': 'redis',
                        }
                    }

                # Deserialize JSON
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8')
                    value = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    value = raw

                return {
                    'ok': True,
                    'data': {
                        'key': key,
                        'value': value,
                        'hit': True,
                        'backend': 'redis',
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis cache get failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
