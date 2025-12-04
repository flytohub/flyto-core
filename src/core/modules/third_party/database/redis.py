"""
Redis Caching Modules

Provides Redis key-value store operations.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='db.redis.get',
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
    input_types=['text'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=5,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,  # Cache may contain sensitive data
    required_permissions=['database.read'],

    params_schema={
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.db.redis.get.params.key.label',
            'description': 'Redis key to retrieve',
            'description_key': 'modules.db.redis.get.params.key.description',
            'required': True
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.db.redis.get.params.host.label',
            'description': 'Redis host',
            'description_key': 'modules.db.redis.get.params.host.description',
            'default': 'localhost',
            'required': False
        },
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.db.redis.get.params.port.label',
            'description': 'Redis port',
            'description_key': 'modules.db.redis.get.params.port.description',
            'default': 6379,
            'required': False
        },
        'db': {
            'type': 'number',
            'label': 'Database',
            'label_key': 'modules.db.redis.get.params.db.label',
            'description': 'Redis database number',
            'description_key': 'modules.db.redis.get.params.db.description',
            'default': 0,
            'required': False
        }
    },
    output_schema={
        'value': {'type': 'any'},
        'exists': {'type': 'boolean'},
        'key': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Get cached value',
            'params': {
                'key': 'user:123:profile',
                'host': 'localhost'
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
        self.key = self.params.get('key')
        self.host = self.params.get('host', 'localhost')
        self.port = self.params.get('port', 6379)
        self.db = self.params.get('db', 0)

        if not self.key:
            raise ValueError("key is required")

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
    input_types=['any'],
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

    params_schema={
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.db.redis.set.params.key.label',
            'description': 'Redis key to set',
            'description_key': 'modules.db.redis.set.params.key.description',
            'required': True
        },
        'value': {
            'type': 'any',
            'label': 'Value',
            'label_key': 'modules.db.redis.set.params.value.label',
            'description': 'Value to store',
            'description_key': 'modules.db.redis.set.params.value.description',
            'required': True
        },
        'ttl': {
            'type': 'number',
            'label': 'TTL (seconds)',
            'label_key': 'modules.db.redis.set.params.ttl.label',
            'description': 'Time to live in seconds (optional)',
            'description_key': 'modules.db.redis.set.params.ttl.description',
            'required': False
        },
        'host': {
            'type': 'string',
            'label': 'Host',
            'label_key': 'modules.db.redis.set.params.host.label',
            'description': 'Redis host',
            'description_key': 'modules.db.redis.set.params.host.description',
            'default': 'localhost',
            'required': False
        },
        'port': {
            'type': 'number',
            'label': 'Port',
            'label_key': 'modules.db.redis.set.params.port.label',
            'description': 'Redis port',
            'description_key': 'modules.db.redis.set.params.port.description',
            'default': 6379,
            'required': False
        },
        'db': {
            'type': 'number',
            'label': 'Database',
            'label_key': 'modules.db.redis.set.params.db.label',
            'description': 'Redis database number',
            'description_key': 'modules.db.redis.set.params.db.description',
            'default': 0,
            'required': False
        }
    },
    output_schema={
        'success': {'type': 'boolean'},
        'key': {'type': 'string'}
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
        self.key = self.params.get('key')
        self.value = self.params.get('value')
        self.ttl = self.params.get('ttl')
        self.host = self.params.get('host', 'localhost')
        self.port = self.params.get('port', 6379)
        self.db = self.params.get('db', 0)

        if not self.key or self.value is None:
            raise ValueError("key and value are required")

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
