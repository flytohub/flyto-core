# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Set Module
Set a value in an in-memory or Redis cache with optional TTL.
"""
import json
import logging
import time
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
    module_id='cache.set',
    version='1.0.0',
    category='cache',
    tags=['cache', 'set', 'write', 'store', 'key-value', 'ttl'],
    label='Cache Set',
    label_key='modules.cache.set.label',
    description='Set a value in cache with optional TTL',
    description_key='modules.cache.set.description',
    icon='Database',
    color='#F59E0B',
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
            'key',
            type='string',
            label='Cache Key',
            label_key='modules.cache.set.params.key.label',
            description='The cache key to store the value under',
            description_key='modules.cache.set.params.key.description',
            placeholder='my-cache-key',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'value',
            type='string',
            label='Value',
            label_key='modules.cache.set.params.value.label',
            description='The value to cache (any JSON-serializable value)',
            description_key='modules.cache.set.params.value.description',
            required=True,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'ttl',
            type='number',
            label='TTL (seconds)',
            label_key='modules.cache.set.params.ttl.label',
            description='Time-to-live in seconds (0 = no expiry)',
            description_key='modules.cache.set.params.ttl.description',
            default=0,
            min=0,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'backend',
            type='string',
            label='Backend',
            label_key='modules.cache.set.params.backend.label',
            description='Cache backend to use',
            description_key='modules.cache.set.params.backend.description',
            default='memory',
            enum=['memory', 'redis'],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'redis_url',
            type='string',
            label='Redis URL',
            label_key='modules.cache.set.params.redis_url.label',
            description='Redis connection URL',
            description_key='modules.cache.set.params.redis_url.description',
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
            'description_key': 'modules.cache.set.output.key.description',
        },
        'stored': {
            'type': 'boolean',
            'description': 'Whether the value was stored successfully',
            'description_key': 'modules.cache.set.output.stored.description',
        },
        'ttl': {
            'type': 'number',
            'description': 'The TTL in seconds (0 = no expiry)',
            'description_key': 'modules.cache.set.output.ttl.description',
        },
        'backend': {
            'type': 'string',
            'description': 'The backend used',
            'description_key': 'modules.cache.set.output.backend.description',
        },
    },
    timeout_ms=10000,
)
async def cache_set(context: Dict[str, Any]) -> Dict[str, Any]:
    """Set a value in cache with optional TTL."""
    params = context['params']
    key = params.get('key')
    value = params.get('value')
    ttl = int(params.get('ttl', 0) or 0)
    backend = params.get('backend', 'memory')
    redis_url = params.get('redis_url', 'redis://localhost:6379')

    if not key:
        raise ValidationError("Missing required parameter: key", field="key")
    if value is None:
        raise ValidationError("Missing required parameter: value", field="value")

    if backend == 'memory':
        expires_at = None
        if ttl > 0:
            expires_at = time.time() + ttl

        _memory_cache[key] = {
            'value': value,
            'expires_at': expires_at,
        }

        return {
            'ok': True,
            'data': {
                'key': key,
                'stored': True,
                'ttl': ttl,
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
                serialized = json.dumps(value)
                if ttl > 0:
                    await client.set(key, serialized, ex=ttl)
                else:
                    await client.set(key, serialized)

                return {
                    'ok': True,
                    'data': {
                        'key': key,
                        'stored': True,
                        'ttl': ttl,
                        'backend': 'redis',
                    }
                }
            finally:
                await client.aclose()
        except ModuleError:
            raise
        except Exception as e:
            raise ModuleError("Redis cache set failed: {}".format(str(e)))

    else:
        raise ValidationError(
            "Invalid backend '{}'. Must be 'memory' or 'redis'".format(backend),
            field='backend'
        )
