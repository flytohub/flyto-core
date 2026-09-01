# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Get Module
Get a value from an in-memory or Redis cache.

HOW FAR THIS MODULE FOLLOWS REALITY

A lookup has two answers and they are not the same kind of answer, so they do
not get the same rung.

  a value came back                                   OBSERVED
      The value in `data['value']` is the one the store held. It was not
      computed here, not defaulted here, and there is no branch that invents
      it: it came out of `_memory_cache` through the TTL-respecting read path,
      or off the wire from Redis. That is a measurement of the store's
      contents, which is what OBSERVED means.

  nothing came back                                   ACCEPTED
      `hit=False` is the same reading whether the key was never written, was
      written and has expired, was written to a different process's copy of
      `_memory_cache`, or was written to a Redis at a different `redis_url`.
      A value that reads identically across "the data is not there" and "we
      are not looking where the data is" is not evidence about the data. What
      it does establish is that a store answered the lookup, and that is
      exactly ACCEPTED.

This is the same split `database.query._returned_rows` makes for a query that
returns no result set, and for the same reason.

WHAT `hit` DOES NOT DISTINGUISH, and why the rung cannot fix it: the `memory`
backend is a module-level dict, so it is per-process. Two workers do not share
it, and a `cache.set` on one is a permanent miss on the other. The rung reports
what this process's store said; it cannot report that the caller pointed at the
wrong store.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_service_url
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Module-level in-memory cache storage
# Structure: {key: {'value': any, 'expires_at': float or None}}
_memory_cache: Dict[str, Dict[str, Any]] = {}


def _lookup_outcome(backend: str, hit: bool) -> Dict[str, Any]:
    """The rung a single cache lookup earned, and the reading that earned it.

    Kept as a free function, and pure, so the decision can be tested without a
    Redis and without reaching into module state -- the same separation
    ``file.write._write_outcome`` keeps.
    """
    if hit:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'cached_value_returned',
                'backend': backend,
                'measured_by': (
                    'the value the store returned for this key -- from '
                    '_memory_cache through the TTL check, or from the Redis '
                    'GET reply'
                ),
                'detail': (
                    'A stored value crossed back to us. It says the key is '
                    'present in the store this module read; it says nothing '
                    'about how it got there or when it expires.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'cache_miss',
            'backend': backend,
            'measured_by': None,
            'detail': (
                'The store answered and returned nothing. A miss reads '
                'identically whether the key was never set, was set and has '
                'expired, or was set somewhere this module is not looking -- '
                'the memory backend is per-process. Nothing about the data '
                'was observed.'
            ),
        }],
    )


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
        'outcome': {
            'type': 'object',
            'description': (
                'How far the lookup was followed: "observed" when a stored '
                'value came back, "accepted" on a miss -- a miss does not '
                'distinguish absent data from the wrong store'
            ),
            'description_key': 'modules.cache.get.output.outcome.description',
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
    # SECURITY: redis_url is caller-controlled and aioredis will dial
    # whatever host it names. Unguarded that is an internal port prober and a
    # route to the cloud metadata service — the non-HTTP twin of the SSRF
    # advisories. Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')

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
                'outcome': _lookup_outcome('memory', hit),
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
                            'outcome': _lookup_outcome('redis', False),
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
                        'outcome': _lookup_outcome('redis', True),
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
