# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Redis Caching Modules

Provides Redis key-value store operations.

HOW FAR THESE TWO MODULES FOLLOW REALITY, and why they do not agree

They sit next to each other and land on different rungs, which is the point:
the rung follows the evidence, not the file.

`db.redis.get` -- OBSERVED on a hit, ACCEPTED on a miss.
    `value` is the server's reply to GET, decoded by the client. A string is
    state read out of the database and held in our hand: OBSERVED.

    A nil reply is not. It is tempting to call it one -- GET names a single key
    and cannot write, so RESP nil looks like the server positively stating that
    the key does not exist -- and that reading was written here first and then
    withdrawn, because it does not survive being applied to the module next
    door. `db.mongodb.find` on a collection that does not exist returns an empty
    cursor rather than an error; `db.redis.get` against the wrong `db` index, or
    a replica that has not caught up, returns nil for a key that exists. In both
    cases the empty answer is consistent with the world containing the thing we
    were looking for.

    So the rule this group follows is one rule, not a per-module argument:
    OBSERVED requires holding state the peer sent. An answer containing none of
    it says the peer answered, which is ACCEPTED. That is the same reading
    `database.query` gives an empty result set, and a `db.redis.get` that
    claimed a rung its sibling connectors refuse for the same evidence would
    mean the field encodes which file you happened to call.

    `exists` still carries the fact. The rung carries how far we followed it.

`db.redis.set` -- ACCEPTED, and no further.
    A `+OK` from SET is the server reporting on its own work. Taking a peer's
    word for its own work is exactly what ACCEPTED means, and OBSERVED would
    need a GET afterwards -- a second round trip this module does not make, and
    one that a TTL or a concurrent writer can make disagree without anything
    being wrong. The write is not read back and the rung says so.

    A falsy reply with no exception is a third answer: the server answered and
    its answer is that the value was not stored. That is not ACCEPTED (the peer
    did not acknowledge taking it) and not FAILED (nobody declared a
    postcondition, so no predicate was broken) -- it is INDETERMINATE with the
    claim attributed to this module, per `outcome.py`'s split on who claimed.

VERIFIED is unreachable for both and neither declares a postcondition:
`ceiling_for(None)` caps them at OBSERVED, which is where they belong.
"""
from typing import Any, Dict
from ...base import BaseModule
from ....utils import enforce_outbound_host
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets


def _get_outcome(exists: bool) -> Dict[str, Any]:
    """OBSERVED for a value we hold; ACCEPTED for a reply that carried none."""
    if exists:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'key_present',
                'backend': 'redis',
                'measured_by': "the server's reply to GET, decoded by the client",
                'detail': (
                    'A value came back off the wire. That is state read out of '
                    'the database, not an inference about it.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'key_absent',
            'backend': 'redis',
            'measured_by': None,
            'detail': (
                'The server replied nil and we hold no value. That is not an '
                'observation that the key does not exist: the wrong db index, '
                'or a replica that has not caught up, answers nil for a key '
                'that does. The `exists` field carries the reply; the rung '
                'carries how far it was followed.'
            ),
        }],
    )


def _set_outcome(stored: bool) -> Dict[str, Any]:
    """ACCEPTED on the server's OK; INDETERMINATE when it declines to store."""
    if stored:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'write_acknowledged',
                'backend': 'redis',
                'measured_by': "the server's OK reply to SET/SETEX",
                'detail': (
                    'The server reported storing the value. That is the peer '
                    'reporting on its own work -- the key is not read back, so '
                    'nothing here observed the stored value.'
                ),
            }],
        )
    return envelope(
        Outcome.INDETERMINATE,
        # INFERRED: reading a falsy reply as "not stored" is this module's
        # inference. No caller declared what the reply had to be, so a broken
        # contract is not what happened.
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'write_not_acknowledged',
            'backend': 'redis',
            'measured_by': "the server's reply to SET/SETEX",
            'detail': (
                'The server answered without an error and without an OK. We '
                'cannot say whether the value was stored, so this is '
                'indeterminate rather than accepted or failed.'
            ),
        }],
    )


@register_module(
    module_id='db.redis.get',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='database',
    subcategory='cache',
    tags=['ssrf_protected', 'database', 'redis', 'cache', 'get'],
    label='Redis Get',
    label_key='modules.db.redis.get.label',
    description='Get a value from Redis cache',
    description_key='modules.db.redis.get.description',
    icon='Database',
    color='#DC2626',

    # Connection types
    input_types=['string'],
    output_types=['string', 'json'],

    # Phase 2: Execution settings
    timeout_ms=5000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['REDIS_URL'],
    handles_sensitive_data=True,  # Cache may contain sensitive data
    required_permissions=['database.query'],

    params_schema=compose(
        presets.REDIS_KEY(),
        presets.REDIS_HOST(),
        presets.REDIS_PORT(),
        presets.REDIS_DB(),
    ),
    output_schema={
        'value': {'type': 'any', 'description': 'The returned value',
                'description_key': 'modules.db.redis.get.output.value.description'},
        'exists': {'type': 'boolean',
                'description': 'Whether the server returned a value for this key',
                'description_key': 'modules.db.redis.get.output.exists.description'},
        'key': {'type': 'string', 'description': 'Key identifier',
                'description_key': 'modules.db.redis.get.output.key.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far the effect was followed: observed when a value came '
                    'back off the wire, accepted when the server replied nil and '
                    'nothing was held. Never higher -- nothing here evaluates a '
                    'postcondition'
                ),
                'description_key': 'modules.db.redis.get.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Get cached value',
            'params': {
                'key': 'user:123:profile',
                'host': '${env.REDIS_HOST}'
            }
        },
        {
            'title': 'Get from remote Redis',
            'params': {
                'key': 'session:abc',
                'host': 'redis.example.com',
                'port': 6379,
                'db': 1
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class RedisGetModule(BaseModule):
    """Redis Get Module"""

    def validate_params(self) -> None:
        import os
        self.key = self.params.get('key')
        # NO hardcoded defaults - require explicit configuration
        # SECURITY: caller-controlled host, raw TCP connection — SSRF without
        # a URL. Loopback stays allowed for the normal self-hosted case.
        self.host = enforce_outbound_host(
            self.params.get('host') or os.getenv('REDIS_HOST') or 'localhost',
            purpose='Redis',
        )
        self.port = self.params.get('port', 6379)
        self.db = self.params.get('db', 0)

        if not self.key:
            raise ValueError("key is required")

        if not self.host:
            raise ValueError(
                "Redis host not configured. "
                "Set 'host' parameter or REDIS_HOST environment variable."
            )

    async def execute(self) -> Any:
        try:
            # Import redis
            try:
                import redis.asyncio as redis
            except ImportError:
                raise ImportError(
                    "Redis library not installed. "
                    "Install with: pip install redis"
                )

            # Connect to Redis
            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True
            )

            try:
                # Get value
                value = await client.get(self.key)
            finally:
                # RELIABILITY: the close used to sit on the success path only,
                # so every raising GET leaked a connection -- and this module is
                # retryable with max_retries=2, so an unreachable Redis leaked
                # three per step.
                await client.close()

            exists = value is not None

            return {
                "value": value,
                "exists": exists,
                "key": self.key,
                "outcome": _get_outcome(exists),
            }
        except Exception as e:
            raise RuntimeError(f"Redis error: {str(e)}")


@register_module(
    module_id='db.redis.set',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='database',
    subcategory='cache',
    tags=['ssrf_protected', 'database', 'redis', 'cache', 'set'],
    label='Redis Set',
    label_key='modules.db.redis.set.label',
    description='Set a value in Redis cache',
    description_key='modules.db.redis.set.description',
    icon='Database',
    color='#DC2626',

    # Connection types
    input_types=['string', 'json'],
    output_types=['boolean'],

    # Phase 2: Execution settings
    timeout_ms=5000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['REDIS_URL'],
    handles_sensitive_data=True,
    required_permissions=['database.query'],

    params_schema=compose(
        presets.REDIS_KEY(),
        presets.REDIS_VALUE(),
        presets.REDIS_TTL(),
        presets.REDIS_HOST(),
        presets.REDIS_PORT(),
        presets.REDIS_DB(),
    ),
    output_schema={
        'success': {
            'type': 'boolean',
            'description': (
                'Whether the server replied OK to the SET. The value is not '
                'read back, so this is the server\'s report of its own work'
            )
        },
        'key': {'type': 'string', 'description': 'Key identifier'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed: accepted on the server\'s OK, '
                'indeterminate when it answered without one. Never observed -- '
                'the key is not read back'
            )
        }
    },
    examples=[
        {
            'title': 'Cache user profile',
            'params': {
                'key': 'user:123:profile',
                'value': '{"name": "John", "email": "dev@flyto2.com"}',
                'ttl': 3600
            }
        },
        {
            'title': 'Set session data',
            'params': {
                'key': 'session:abc',
                'value': 'active',
                'ttl': 1800,
                'host': 'redis.example.com'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class RedisSetModule(BaseModule):
    """Redis Set Module"""

    def validate_params(self) -> None:
        import os
        self.key = self.params.get('key')
        self.value = self.params.get('value')
        self.ttl = self.params.get('ttl')
        # NO hardcoded defaults - require explicit configuration
        # SECURITY: caller-controlled host, raw TCP connection — SSRF without
        # a URL. Loopback stays allowed for the normal self-hosted case.
        self.host = enforce_outbound_host(
            self.params.get('host') or os.getenv('REDIS_HOST') or 'localhost',
            purpose='Redis',
        )
        self.port = self.params.get('port', 6379)
        self.db = self.params.get('db', 0)

        if not self.key or self.value is None:
            raise ValueError("key and value are required")

        if not self.host:
            raise ValueError(
                "Redis host not configured. "
                "Set 'host' parameter or REDIS_HOST environment variable."
            )

    async def execute(self) -> Any:
        try:
            # Import redis
            try:
                import redis.asyncio as redis
            except ImportError:
                raise ImportError(
                    "Redis library not installed. "
                    "Install with: pip install redis"
                )

            # Connect to Redis
            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True
            )

            try:
                # Set value
                if self.ttl:
                    success = await client.setex(self.key, self.ttl, str(self.value))
                else:
                    success = await client.set(self.key, str(self.value))
            finally:
                # RELIABILITY: see db.redis.get -- the close was on the success
                # path only and leaked a connection per raising SET.
                await client.close()

            return {
                "success": bool(success),
                "key": self.key,
                "outcome": _set_outcome(bool(success)),
            }
        except Exception as e:
            raise RuntimeError(f"Redis error: {str(e)}")
