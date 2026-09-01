# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cache Set Module
Set a value in an in-memory or Redis cache with optional TTL.

HOW FAR THIS MODULE FOLLOWS REALITY

`stored: True` was, and still is, a literal written in this file. It is the
`file.write` mistake exactly: it reads `True` whether the value went into the
store or the assignment never ran, so it cannot be what any rung rests on. The
two backends therefore earn different rungs, from different evidence.

  memory, and the key reads back as ours                 OBSERVED
      After the assignment the module calls `_cache_get(key)` -- the same
      TTL-respecting path `cache.get` uses -- and checks that what comes back
      is the object it stored. If the assignment had not happened, that read
      returns `None` or somebody else's value, so the reading is not a
      restatement of the input. What it establishes is the thing a caller
      actually wants: a subsequent `cache.get` for this key would hit.

  memory, and it does not read back as ours              INDETERMINATE
      Not FAILED. Nobody declared a read-back contract; the predicate is this
      module's own, and a concurrent writer replacing the key between the
      store and the read is an ordinary correct race, not a broken promise.
      `outcome.py` splits on exactly this -- a caller's broken contract is
      FAILED, an inference of ours that may be wrong is INDETERMINATE.

  redis, and the client returned an OK                   ACCEPTED
      The SET reply is the peer reporting on its own work, which is taking its
      word -- the same standing as a 2xx. No value is read back, so nothing
      here measures the store. Deliberately not raised by adding a GET: a
      second round trip would change what this module costs and still could
      not attribute what it read to this write.

  redis, and the client returned no OK                   INDETERMINATE
      redis-py answers `True` for a plain SET. Anything else means we cannot
      say whether the value landed.

WHAT IS NOT OBSERVED, on either backend: expiry. The TTL is passed to the store
and never watched, so "this value will still be here in `ttl` seconds" and
"this value will be gone after `ttl` seconds" are both unproven. And the
`memory` backend is a module-level dict, so a value stored here is invisible to
every other worker process -- durable only in the sense that it outlives the
step, not the process.
"""
import json
import logging
import time
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
from .get import _memory_cache, _cache_get


#: The claim `stored: True` makes on its own, recorded beside every rung so the
#: gap between the flag and the evidence stays visible rather than implied.
_STORED_FLAG_EFFECT = {
    'kind': 'store_call_returned',
    'measured_by': None,
    'detail': (
        "The `stored` output is a literal True written in this module, not a "
        "reading of the store. It is identical whether the value landed or "
        "not; see the sibling effect for what was actually measured."
    ),
}


def _memory_store_outcome(*, ttl: int, readback_is_ours: bool, readback_present: bool) -> Dict[str, Any]:
    """The rung a memory-backend store earned, from the read-back that follows it.

    Pure, and free of module state, so the decision is testable without
    touching `_memory_cache` -- the separation `file.write._write_outcome`
    keeps for the same reason.
    """
    if readback_is_ours:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: a predicate was evaluated and it was ours. No caller
            # asked for a read-back; recording who did keeps the matching and
            # the mismatching case attributable to the same author.
            claim_by=ClaimBy.INFERRED,
            effects=[
                _STORED_FLAG_EFFECT,
                {
                    'kind': 'cache_key_read_back',
                    'backend': 'memory',
                    'ttl_seconds': ttl,
                    'measured_by': (
                        '_cache_get(key) after the assignment -- the same '
                        'TTL-respecting path cache.get uses -- compared by '
                        'identity with the value handed in'
                    ),
                    'detail': (
                        'The key resolves to the object stored, so a later '
                        'cache.get would hit. Expiry is not observed: the TTL '
                        'was handed to the store and never watched.'
                    ),
                },
            ],
        )
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            _STORED_FLAG_EFFECT,
            {
                'kind': 'cache_key_read_back_disagrees',
                'backend': 'memory',
                'ttl_seconds': ttl,
                'predicate': '_cache_get(key) is the value handed to this module',
                'key_present_after': readback_present,
                'detail': (
                    'The key did not read back as the value stored. A '
                    'concurrent writer replacing the key is an ordinary race '
                    'and this module cannot tell that apart from a store that '
                    'dropped the write, so this is indeterminate rather than '
                    'failed.'
                ),
            },
        ],
    )


def _redis_store_outcome(*, ttl: int, reply: Any) -> Dict[str, Any]:
    """The rung a Redis-backend store earned, from the SET reply alone."""
    if reply:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                _STORED_FLAG_EFFECT,
                {
                    'kind': 'redis_set_acknowledged',
                    'backend': 'redis',
                    'ttl_seconds': ttl,
                    'measured_by': 'the reply redis-py returned for SET',
                    'detail': (
                        'The server acknowledged taking the write. Nothing was '
                        'read back, so no line here measures the store: this is '
                        'the peer reporting on its own work.'
                    ),
                },
            ],
        )
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            _STORED_FLAG_EFFECT,
            {
                'kind': 'redis_set_not_acknowledged',
                'backend': 'redis',
                'ttl_seconds': ttl,
                'reply': repr(reply),
                'detail': (
                    'A plain SET answers True. Without that acknowledgement we '
                    'cannot say whether the value was stored.'
                ),
            },
        ],
    )


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
            showIf={'backend': {'$in': ['redis']}},
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
            'description': (
                'A literal True written by this module when the store call '
                'returned without raising. Not a reading of the store -- see '
                'outcome for what was measured'
            ),
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
        'read_back': {
            'type': 'boolean',
            'description': (
                'memory backend only: whether the key read back as the value '
                'stored. null on the redis backend, which reads nothing back'
            ),
            'description_key': 'modules.cache.set.output.read_back.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the write was followed: "observed" when the key read '
                'back as ours, "accepted" when Redis acknowledged and nothing '
                'was read back, "indeterminate" when neither held. Expiry is '
                'never observed'
            ),
            'description_key': 'modules.cache.set.output.outcome.description',
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
    # SECURITY: redis_url is caller-controlled and aioredis will dial
    # whatever host it names. Unguarded that is an internal port prober and a
    # route to the cloud metadata service — the non-HTTP twin of the SSRF
    # advisories. Loopback (the normal self-hosted case) stays allowed.
    enforce_outbound_service_url(redis_url, purpose='Redis')

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

        # The only line in this branch that measures the store rather than
        # restating the input. Identity, not equality: the memory backend keeps
        # the object handed in, so `is` is the strongest available check and it
        # catches a racing writer that stored an equal-but-different value.
        read_back_value = _cache_get(key)
        read_back_is_ours = read_back_value is value

        return {
            'ok': True,
            'data': {
                'key': key,
                'stored': True,
                'ttl': ttl,
                'backend': 'memory',
                'read_back': read_back_is_ours,
                'outcome': _memory_store_outcome(
                    ttl=ttl,
                    readback_is_ours=read_back_is_ours,
                    readback_present=read_back_value is not None,
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
                serialized = json.dumps(value)
                if ttl > 0:
                    reply = await client.set(key, serialized, ex=ttl)
                else:
                    reply = await client.set(key, serialized)

                return {
                    'ok': True,
                    'data': {
                        'key': key,
                        'stored': True,
                        'ttl': ttl,
                        'backend': 'redis',
                        'read_back': None,
                        'outcome': _redis_store_outcome(ttl=ttl, reply=reply),
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
