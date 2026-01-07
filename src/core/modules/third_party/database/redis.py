"""
Redis Caching Modules

Provides Redis key-value store operations.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='db.redis.get',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'api.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='database',
    subcategory='cache',
    tags=['database', 'redis', 'cache', 'get'],
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
    timeout=5,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,  # Cache may contain sensitive data
    required_permissions=['database.read'],

    params_schema=compose(
        presets.REDIS_KEY(),
        presets.REDIS_HOST(),
        presets.REDIS_PORT(),
        presets.REDIS_DB(),
    ),
    output_schema={
        'value': {'type': 'any', 'description': 'The returned value',
                'description_key': 'modules.db.redis.get.output.value.description'},
        'exists': {'type': 'boolean', 'description': 'The exists',
                'description_key': 'modules.db.redis.get.output.exists.description'},
        'key': {'type': 'string', 'description': 'Key identifier',
                'description_key': 'modules.db.redis.get.output.key.description'}
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

    def validate_params(self):
        import os
        self.key = self.params.get('key')
        # NO hardcoded defaults - require explicit configuration
        self.host = self.params.get('host') or os.getenv('REDIS_HOST')
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

            # Get value
            value = await client.get(self.key)
            exists = value is not None

            await client.close()

            return {
                "value": value,
                "exists": exists,
                "key": self.key
            }
        except Exception as e:
            raise RuntimeError(f"Redis error: {str(e)}")


@register_module(
    module_id='db.redis.set',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'api.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='database',
    subcategory='cache',
    tags=['database', 'redis', 'cache', 'set'],
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
    timeout=5,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['database.write'],

    params_schema=compose(
        presets.REDIS_KEY(),
        presets.REDIS_VALUE(),
        presets.REDIS_TTL(),
        presets.REDIS_HOST(),
        presets.REDIS_PORT(),
        presets.REDIS_DB(),
    ),
    output_schema={
        'success': {'type': 'boolean', 'description': 'Whether the operation completed successfully'},
        'key': {'type': 'string', 'description': 'Key identifier'}
    },
    examples=[
        {
            'title': 'Cache user profile',
            'params': {
                'key': 'user:123:profile',
                'value': '{"name": "John", "email": "john@example.com"}',
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

    def validate_params(self):
        import os
        self.key = self.params.get('key')
        self.value = self.params.get('value')
        self.ttl = self.params.get('ttl')
        # NO hardcoded defaults - require explicit configuration
        self.host = self.params.get('host') or os.getenv('REDIS_HOST')
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

            # Set value
            if self.ttl:
                success = await client.setex(self.key, self.ttl, str(self.value))
            else:
                success = await client.set(self.key, str(self.value))

            await client.close()

            return {
                "success": bool(success),
                "key": self.key
            }
        except Exception as e:
            raise RuntimeError(f"Redis error: {str(e)}")
