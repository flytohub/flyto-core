# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Clear Module
Clear all cache entries, optionally filtered by a glob pattern.

HOW FAR THIS MODULE FOLLOWS REALITY

`cleared_count` on the memory backend is `len(_memory_cache)` or
`len(keys_to_delete)` -- both taken BEFORE anything is removed. They are
readings of what matched, not of what went away, and they are unchanged if the
`clear()` on the next line never runs. So the rung rests on a second reading of
`len(_memory_cache)`, taken after, and on the difference between the two.

  memory: matched N > 0, and the store shrank by N       OBSERVED
      A measured delta, attributable to this module: there is no await between
      the two readings, so nothing else on this event loop runs inside the
      window.

  memory: nothing matched                                ACCEPTED
      A count of 0 is what an untouched store reads as. Nothing was removed
      and nothing about the removal was observed; the store answered, which is
      ACCEPTED and no more.

  memory: the store did not shrink by what we removed    INDETERMINATE
      Concurrent writers make the delta disagree without anything being wrong.
      The predicate is this module's own inference, so a disagreement is
      indeterminate rather than failed.

  redis: DEL replies totalled N > 0                      OBSERVED
      Each reply counts keys the server removed IN RESPONSE TO THAT DEL --
      attributable to us, unlike a bare key count.

  redis: DEL replies totalled 0                          ACCEPTED
      Identical to what a pattern matching nothing reads as.

WHAT IS NEVER OBSERVED, on either backend: that the cache is now empty.
`SCAN` is not a snapshot -- keys written during the sweep can survive it -- and
the memory branch reports a delta rather than a final size for the pattern
case. "N entries went away" is the claim; "nothing matching the pattern
remains" is not.

HAZARD worth knowing before reading `cleared_count` on the redis backend: this
module namespaces nothing. The default pattern `*` matches every key in the
selected Redis database, including keys no cache module ever wrote. On a shared
Redis, "clear the cache" empties the database. Using `SCAN` instead of
`FLUSHDB` makes that slower and non-atomic; it does not make it narrower.
"""
import fnmatch
import logging
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import enforce_outbound_service_url
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)

# Import shared memory cache storage
from .get import _memory_cache


def _memory_clear_outcome(
    *,
    pattern: str,
    cleared_count: int,
    size_before: int,
    size_after: int,
) -> Dict[str, Any]:
    """The rung a memory-backend clear earned, from the pair of size readings.

    Pure and free of module state, so every branch -- including the
    disagreement -- is reachable in a test without racing the module.
    """
    matched_effect = {
        'kind': 'cache_keys_matched',
        'backend': 'memory',
        'pattern': pattern,
        'count': cleared_count,
        'measured_by': (
            'the number of keys matching the pattern, counted before removal'
        ),
        'detail': (
            'What matched, not what went away. This count is unchanged if the '
            'removal never runs.'
        ),
    }

    if cleared_count == 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                matched_effect,
                {
                    'kind': 'cache_unchanged',
                    'backend': 'memory',
                    'measured_by': None,
                    'detail': (
                        'Nothing matched, so nothing was removed. An unchanged '
                        'store is the same reading we would have got without '
                        'running at all.'
                    ),
                },
            ],
        )

    if size_before - size_after == cleared_count:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[
                matched_effect,
                {
                    'kind': 'cache_size_shrank',
                    'backend': 'memory',
                    'entries_before': size_before,
                    'entries_after': size_after,
                    'entries_removed': size_before - size_after,
                    'measured_by': 'len(_memory_cache) read before and after the removal',
                    'detail': (
                        'The store shrank by exactly the number of keys that '
                        'matched. It does not establish that nothing matching '
                        'the pattern remains.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            matched_effect,
            {
                'kind': 'cache_size_disagrees',
                'backend': 'memory',
                'predicate': 'len(_memory_cache) fell by the number of keys matched',
                'entries_before': size_before,
                'entries_after': size_after,
                'expected_removed': cleared_count,
                'actual_removed': size_before - size_after,
                'detail': (
                    'The store did not shrink by what was removed. A '
                    'concurrent writer explains this without anything being '
                    'wrong, so it is indeterminate rather than failed.'
                ),
            },
        ],
    )


def _redis_clear_outcome(*, pattern: str, cleared_count: Any) -> Dict[str, Any]:
    """The rung a Redis-backend clear earned, from the totalled DEL replies."""
    counted = isinstance(cleared_count, int) and not isinstance(cleared_count, bool)
    if counted and cleared_count > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'redis_keys_removed',
                'backend': 'redis',
                'pattern': pattern,
                'count': cleared_count,
                'measured_by': (
                    'the DEL replies, totalled -- keys the server removed for '
                    'these commands'
                ),
                'detail': (
                    'SCAN is not a snapshot: keys written during the sweep can '
                    'survive it, so this is a count of what went away and not '
                    'a claim that the pattern now matches nothing.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'redis_no_key_removed',
            'backend': 'redis',
            'pattern': pattern,
            'count': cleared_count if counted else None,
            'measured_by': None,
            'detail': (
                'The server removed nothing. That is identical to what a '
                'pattern matching nothing reads as, so it says the keys are '
                'absent, not that this command made them absent.'
            ),
        }],
    )


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
            showIf={'backend': {'$in': ['redis']}},
            group=FieldGroup.CONNECTION,
        ),
    ),
    output_schema={
        'cleared_count': {
            'type': 'number',
            'description': (
                'memory: the number of keys that matched, counted before '
                'removal. redis: the DEL replies totalled, which is what the '
                'server removed'
            ),
            'description_key': 'modules.cache.clear.output.cleared_count.description',
        },
        'backend': {
            'type': 'string',
            'description': 'The backend used',
            'description_key': 'modules.cache.clear.output.backend.description',
        },
        'entries_before': {
            'type': 'number',
            'description': (
                'memory backend only: entries in the store before the removal. '
                'null on the redis backend, which is never counted whole'
            ),
            'description_key': 'modules.cache.clear.output.entries_before.description',
        },
        'entries_after': {
            'type': 'number',
            'description': (
                'memory backend only: entries in the store after the removal. '
                'null on the redis backend'
            ),
            'description_key': 'modules.cache.clear.output.entries_after.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the clear was followed: "observed" when the store '
                'shrank by what was removed, "accepted" when nothing matched, '
                '"indeterminate" when the sizes disagreed. Never a claim that '
                'the cache is now empty'
            ),
            'description_key': 'modules.cache.clear.output.outcome.description',
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
    # SECURITY: redis_url is caller-controlled and aioredis will dial
    # whatever host it names. Unguarded that is an internal port prober and a
    # route to the cloud metadata service — the non-HTTP twin of the SSRF
    # advisories. Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')

    if backend == 'memory':
        # Read the store before touching it. Without this, `cleared_count` is
        # only a count of what matched -- see the module docstring.
        size_before = len(_memory_cache)

        if pattern == '*':
            cleared_count = size_before
            _memory_cache.clear()
        else:
            keys_to_delete = [
                k for k in list(_memory_cache.keys())
                if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_delete:
                del _memory_cache[k]
            cleared_count = len(keys_to_delete)

        size_after = len(_memory_cache)

        return {
            'ok': True,
            'data': {
                'cleared_count': cleared_count,
                'backend': 'memory',
                'entries_before': size_before,
                'entries_after': size_after,
                'outcome': _memory_clear_outcome(
                    pattern=pattern,
                    cleared_count=cleared_count,
                    size_before=size_before,
                    size_after=size_after,
                ),
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
                        'entries_before': None,
                        'entries_after': None,
                        'outcome': _redis_clear_outcome(
                            pattern=pattern,
                            cleared_count=cleared_count,
                        ),
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
