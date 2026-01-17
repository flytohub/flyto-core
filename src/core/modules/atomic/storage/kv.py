"""
Key-Value Storage Module
Simple persistent key-value storage for workflow state.
Uses file-based JSON storage for portability and simplicity.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ...registry import register_module

logger = logging.getLogger(__name__)

# Default storage directory
DEFAULT_STORAGE_DIR = os.path.expanduser("~/.flyto/storage")


def _get_storage_path(namespace: str) -> Path:
    """Get storage file path for namespace"""
    storage_dir = Path(os.environ.get("FLYTO_STORAGE_DIR", DEFAULT_STORAGE_DIR))
    storage_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize namespace for filename
    safe_namespace = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)
    return storage_dir / f"{safe_namespace}.json"


def _load_storage(namespace: str) -> Dict[str, Any]:
    """Load storage data from file"""
    path = _get_storage_path(namespace)
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load storage {namespace}: {e}")
            return {}
    return {}


def _save_storage(namespace: str, data: Dict[str, Any]) -> None:
    """Save storage data to file"""
    path = _get_storage_path(namespace)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _is_expired(entry: Dict[str, Any]) -> bool:
    """Check if entry has expired"""
    expires_at = entry.get("_expires_at")
    if expires_at is None:
        return False
    return time.time() > expires_at


@register_module(
    module_id='storage.get',
    stability='stable',
    version='1.0.0',
    category='storage',
    subcategory='kv',
    tags=['storage', 'cache', 'state', 'kv', 'memory', 'persist'],
    label='Get Stored Value',
    label_key='modules.storage.get.label',
    description='Retrieve a value from persistent key-value storage',
    description_key='modules.storage.get.description',
    icon='Database',
    color='#10B981',

    input_types=['text', 'object'],
    output_types=['object', 'text', 'number'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'namespace': {
            'type': 'string',
            'label': 'Namespace',
            'label_key': 'modules.storage.get.params.namespace.label',
            'description': 'Storage namespace (e.g., workflow name or project)',
            'description_key': 'modules.storage.get.params.namespace.description',
            'required': True,
            'placeholder': 'my-workflow',
            'default': 'default'
        },
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.storage.get.params.key.label',
            'description': 'Key to retrieve',
            'description_key': 'modules.storage.get.params.key.description',
            'required': True,
            'placeholder': 'last_price'
        },
        'default': {
            'type': 'any',
            'label': 'Default Value',
            'label_key': 'modules.storage.get.params.default.label',
            'description': 'Value to return if key does not exist',
            'description_key': 'modules.storage.get.params.default.description',
            'required': False,
            'placeholder': '0'
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.storage.get.output.ok.description'
        },
        'found': {
            'type': 'boolean',
            'description': 'Whether the key was found (not expired)',
            'description_key': 'modules.storage.get.output.found.description'
        },
        'value': {
            'type': 'any',
            'description': 'The stored value or default',
            'description_key': 'modules.storage.get.output.value.description'
        },
        'key': {
            'type': 'string',
            'description': 'The key that was queried',
            'description_key': 'modules.storage.get.output.key.description'
        }
    },
    examples=[
        {
            'title': 'Get last BTC price',
            'title_key': 'modules.storage.get.examples.btc.title',
            'params': {
                'namespace': 'crypto-alerts',
                'key': 'btc_last_price',
                'default': 0
            }
        },
        {
            'title': 'Get workflow state',
            'title_key': 'modules.storage.get.examples.state.title',
            'params': {
                'namespace': 'my-workflow',
                'key': 'last_run_status'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def storage_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get value from key-value storage"""
    params = context['params']
    namespace = params.get('namespace', 'default')
    key = params['key']
    default_value = params.get('default')

    try:
        storage = _load_storage(namespace)
        entry = storage.get(key)

        if entry is None:
            return {
                'ok': True,
                'found': False,
                'value': default_value,
                'key': key
            }

        # Check expiration
        if _is_expired(entry):
            # Clean up expired entry
            del storage[key]
            _save_storage(namespace, storage)
            return {
                'ok': True,
                'found': False,
                'value': default_value,
                'key': key,
                'expired': True
            }

        return {
            'ok': True,
            'found': True,
            'value': entry.get('value'),
            'key': key,
            'stored_at': entry.get('_stored_at')
        }

    except Exception as e:
        logger.error(f"Storage get error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'STORAGE_ERROR',
            'key': key
        }


@register_module(
    module_id='storage.set',
    stability='stable',
    version='1.0.0',
    category='storage',
    subcategory='kv',
    tags=['storage', 'cache', 'state', 'kv', 'memory', 'persist'],
    label='Store Value',
    label_key='modules.storage.set.label',
    description='Store a value in persistent key-value storage',
    description_key='modules.storage.set.description',
    icon='DatabaseBackup',
    color='#10B981',

    input_types=['object', 'text', 'number'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'namespace': {
            'type': 'string',
            'label': 'Namespace',
            'label_key': 'modules.storage.set.params.namespace.label',
            'description': 'Storage namespace (e.g., workflow name or project)',
            'description_key': 'modules.storage.set.params.namespace.description',
            'required': True,
            'placeholder': 'my-workflow',
            'default': 'default'
        },
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.storage.set.params.key.label',
            'description': 'Key to store value under',
            'description_key': 'modules.storage.set.params.key.description',
            'required': True,
            'placeholder': 'last_price'
        },
        'value': {
            'type': 'any',
            'label': 'Value',
            'label_key': 'modules.storage.set.params.value.label',
            'description': 'Value to store (string, number, or object)',
            'description_key': 'modules.storage.set.params.value.description',
            'required': True,
            'placeholder': '42350.50'
        },
        'ttl_seconds': {
            'type': 'number',
            'label': 'TTL (seconds)',
            'label_key': 'modules.storage.set.params.ttl.label',
            'description': 'Time to live in seconds (optional, 0 = no expiration)',
            'description_key': 'modules.storage.set.params.ttl.description',
            'required': False,
            'default': 0,
            'min': 0,
            'max': 31536000,
            'placeholder': '3600'
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.storage.set.output.ok.description'
        },
        'key': {
            'type': 'string',
            'description': 'The key that was stored',
            'description_key': 'modules.storage.set.output.key.description'
        },
        'stored_at': {
            'type': 'number',
            'description': 'Unix timestamp when value was stored',
            'description_key': 'modules.storage.set.output.stored_at.description'
        },
        'expires_at': {
            'type': 'number',
            'description': 'Unix timestamp when value expires (if TTL set)',
            'description_key': 'modules.storage.set.output.expires_at.description'
        }
    },
    examples=[
        {
            'title': 'Store BTC price',
            'title_key': 'modules.storage.set.examples.btc.title',
            'params': {
                'namespace': 'crypto-alerts',
                'key': 'btc_last_price',
                'value': 42350.50
            }
        },
        {
            'title': 'Store with expiration',
            'title_key': 'modules.storage.set.examples.ttl.title',
            'params': {
                'namespace': 'cache',
                'key': 'api_response',
                'value': {'data': 'cached'},
                'ttl_seconds': 3600
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def storage_set(context: Dict[str, Any]) -> Dict[str, Any]:
    """Store value in key-value storage"""
    params = context['params']
    namespace = params.get('namespace', 'default')
    key = params['key']
    value = params['value']
    ttl_seconds = params.get('ttl_seconds', 0)

    try:
        storage = _load_storage(namespace)

        now = time.time()
        entry = {
            'value': value,
            '_stored_at': now
        }

        if ttl_seconds and ttl_seconds > 0:
            entry['_expires_at'] = now + ttl_seconds

        storage[key] = entry
        _save_storage(namespace, storage)

        result = {
            'ok': True,
            'key': key,
            'stored_at': now
        }

        if ttl_seconds and ttl_seconds > 0:
            result['expires_at'] = entry['_expires_at']

        return result

    except Exception as e:
        logger.error(f"Storage set error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'STORAGE_ERROR',
            'key': key
        }


@register_module(
    module_id='storage.delete',
    stability='stable',
    version='1.0.0',
    category='storage',
    subcategory='kv',
    tags=['storage', 'cache', 'state', 'kv', 'memory', 'persist'],
    label='Delete Stored Value',
    label_key='modules.storage.delete.label',
    description='Delete a value from persistent key-value storage',
    description_key='modules.storage.delete.description',
    icon='Trash2',
    color='#EF4444',

    input_types=['text', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'namespace': {
            'type': 'string',
            'label': 'Namespace',
            'label_key': 'modules.storage.delete.params.namespace.label',
            'description': 'Storage namespace',
            'description_key': 'modules.storage.delete.params.namespace.description',
            'required': True,
            'placeholder': 'my-workflow',
            'default': 'default'
        },
        'key': {
            'type': 'string',
            'label': 'Key',
            'label_key': 'modules.storage.delete.params.key.label',
            'description': 'Key to delete',
            'description_key': 'modules.storage.delete.params.key.description',
            'required': True,
            'placeholder': 'last_price'
        }
    },
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the operation succeeded',
            'description_key': 'modules.storage.delete.output.ok.description'
        },
        'deleted': {
            'type': 'boolean',
            'description': 'Whether the key existed and was deleted',
            'description_key': 'modules.storage.delete.output.deleted.description'
        },
        'key': {
            'type': 'string',
            'description': 'The key that was deleted',
            'description_key': 'modules.storage.delete.output.key.description'
        }
    },
    examples=[
        {
            'title': 'Delete cached value',
            'title_key': 'modules.storage.delete.examples.cache.title',
            'params': {
                'namespace': 'cache',
                'key': 'api_response'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def storage_delete(context: Dict[str, Any]) -> Dict[str, Any]:
    """Delete value from key-value storage"""
    params = context['params']
    namespace = params.get('namespace', 'default')
    key = params['key']

    try:
        storage = _load_storage(namespace)

        deleted = key in storage
        if deleted:
            del storage[key]
            _save_storage(namespace, storage)

        return {
            'ok': True,
            'deleted': deleted,
            'key': key
        }

    except Exception as e:
        logger.error(f"Storage delete error: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'STORAGE_ERROR',
            'key': key
        }
