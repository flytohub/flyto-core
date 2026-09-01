# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Delete Module
Delete a cache entry by key.

HOW FAR THIS MODULE FOLLOWS REALITY

The trap here is that `deleted` is measured BEFORE the deletion. `deleted =
key in _memory_cache` is a reading of the store as it was; it says `True`
whether or not the `del` on the next line ran. Apply the test the ladder turns
on -- would this value be the same if the effect had not happened? -- and the
answer is yes, so no rung may rest on it. What the rung rests on instead is a
second reading, taken after.

  memory: present before, absent after                   OBSERVED
      Two readings of the store with the deletion between them. The pair is
      evidence of a change, and of THIS module's change: there is no await
      between the readings, so nothing else on this event loop runs inside the
      window.

  memory: absent before, absent after                    ACCEPTED
      Nothing was removed. `absent` afterwards is the same reading we would
      have got without issuing the delete at all, so it is not evidence about
      our delete -- only that the store answered. The key being gone is the
      state a caller wanted; wanting it and having caused it are different
      claims, and only the second is an observation.

  memory: still present after                            INDETERMINATE
      A concurrent writer re-adding the key is an ordinary race, and this
      module cannot tell it apart from a delete that did not take. Nobody
      declared a contract, so this is our own inference failing --
      indeterminate, not failed.

  redis: DEL reported 1 or more removed                  OBSERVED
      The reply counts the keys the server removed IN RESPONSE TO THIS
      COMMAND. That is attributable to us in a way a bare length is not, which
      is why this earns a rung a `SET` acknowledgement does not.

  redis: DEL reported 0                                  ACCEPTED
      Identical to the reply for a key that was never there -- the same shape
      as the memory case above.

KNOWN INCONSISTENCY, left as it is: `key in _memory_cache` does not apply the
TTL, while `cache.get` reads through `_cache_get`, which does. An entry whose
TTL has passed but which nothing has swept yet is a miss to `cache.get` and a
`deleted: True` here. The entry really was removed, so the report is not false;
it answers a slightly different question than `cache.get` does.
"""
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


def _memory_delete_outcome(*, present_before: bool, present_after: bool) -> Dict[str, Any]:
    """The rung a memory-backend delete earned, from the pair of readings.

    Pure and free of module state, so every branch is reachable in a test
    without having to win a race against the module -- the separation
    `file.write._write_outcome` keeps for the same reason.
    """
    before_effect = {
        'kind': 'cache_key_present_before',
        'backend': 'memory',
        'present': present_before,
        'measured_by': 'key in _memory_cache, before the del',
        'detail': (
            'The reading the `deleted` output is built from. On its own it is '
            'not evidence of a deletion: it is taken before one could have '
            'happened.'
        ),
    }

    if present_after:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[
                before_effect,
                {
                    'kind': 'cache_key_still_present',
                    'backend': 'memory',
                    'predicate': 'key not in _memory_cache, after the del',
                    'detail': (
                        'The key is still in the store. A concurrent writer '
                        're-adding it and a delete that did not take read the '
                        'same here, so this is indeterminate rather than '
                        'failed.'
                    ),
                },
            ],
        )

    if present_before:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[
                before_effect,
                {
                    'kind': 'cache_key_removed',
                    'backend': 'memory',
                    'measured_by': (
                        'key in _memory_cache read before and after the del: '
                        'True then False'
                    ),
                    'detail': (
                        'The store changed, and the change is attributable to '
                        'this module -- there is no await between the two '
                        'readings.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            before_effect,
            {
                'kind': 'cache_key_absent',
                'backend': 'memory',
                'measured_by': None,
                'detail': (
                    'The key was not there, so nothing was removed. Absent '
                    'afterwards is the same reading we would have got without '
                    'issuing the delete, so it is not evidence about this '
                    'delete.'
                ),
            },
        ],
    )


def _redis_delete_outcome(removed: Any) -> Dict[str, Any]:
    """The rung a Redis-backend delete earned, from the DEL reply.

    `removed` is a count of the keys the server removed in response to this
    command -- attributable, unlike a length -- which is why a positive count
    earns OBSERVED where a `SET` acknowledgement earns only ACCEPTED. Anything
    that is not a whole number is no count at all.
    """
    counted = isinstance(removed, int) and not isinstance(removed, bool)
    if counted and removed > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'redis_keys_removed',
                'backend': 'redis',
                'count': removed,
                'measured_by': 'the DEL reply -- keys the server removed for this command',
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'redis_no_key_removed',
            'backend': 'redis',
            'count': removed if counted else None,
            'measured_by': None,
            'detail': (
                'The server removed nothing. A DEL reply of 0 is identical to '
                'the reply for a key that was never there, so it says the key '
                'is absent, not that this command made it absent.'
            ),
        }],
    )


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
            showIf={'backend': {'$in': ['redis']}},
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
            'description': (
                'Whether the key was present BEFORE the delete. A reading of '
                'the store as it was, not of the removal -- see outcome'
            ),
            'description_key': 'modules.cache.delete.output.deleted.description',
        },
        'backend': {
            'type': 'string',
            'description': 'The backend used',
            'description_key': 'modules.cache.delete.output.backend.description',
        },
        'present_after': {
            'type': 'boolean',
            'description': (
                'memory backend only: whether the key was still in the store '
                'after the delete. null on the redis backend, which reads a '
                'removal count instead'
            ),
            'description_key': 'modules.cache.delete.output.present_after.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the delete was followed: "observed" when a key that '
                'was there is gone, "accepted" when there was nothing to '
                'remove, "indeterminate" when the key survived'
            ),
            'description_key': 'modules.cache.delete.output.outcome.description',
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
    # SECURITY: redis_url is caller-controlled and aioredis will dial
    # whatever host it names. Unguarded that is an internal port prober and a
    # route to the cloud metadata service — the non-HTTP twin of the SSRF
    # advisories. Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')

    if not key:
        raise ValidationError("Missing required parameter: key", field="key")

    if backend == 'memory':
        deleted = key in _memory_cache
        if deleted:
            del _memory_cache[key]
        # The second reading, and the only one that can be evidence of a
        # removal. No await separates it from the first, so nothing else on
        # this event loop can have moved the store in between.
        present_after = key in _memory_cache

        return {
            'ok': True,
            'data': {
                'key': key,
                'deleted': deleted,
                'backend': 'memory',
                'present_after': present_after,
                'outcome': _memory_delete_outcome(
                    present_before=deleted,
                    present_after=present_after,
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
                result = await client.delete(key)
                deleted = result > 0

                return {
                    'ok': True,
                    'data': {
                        'key': key,
                        'deleted': deleted,
                        'backend': 'redis',
                        'present_after': None,
                        'outcome': _redis_delete_outcome(result),
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
