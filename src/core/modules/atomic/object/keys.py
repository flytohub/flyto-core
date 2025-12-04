"""
Object Operations Modules

Provides object/dictionary manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='object.keys',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'keys', 'dictionary'],
    label='Object Keys',
    label_key='modules.object.keys.label',
    description='Get all keys from an object',
    description_key='modules.object.keys.description',
    icon='Key',
    color='#F59E0B',

    # Connection types
    input_types=['json'],
    output_types=['array'],

    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'object': {
            'type': 'json',
            'label': 'Object',
            'label_key': 'modules.object.keys.params.object.label',
            'description': 'Input object/dictionary',
            'description_key': 'modules.object.keys.params.object.description',
            'required': True
        }
    },
    output_schema={
        'keys': {'type': 'array'},
        'count': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Get object keys',
            'params': {
                'object': {'name': 'John', 'age': 30, 'city': 'NYC'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ObjectKeysModule(BaseModule):
    """Object Keys Module"""

    def validate_params(self):
        self.obj = self.params.get('object')

        if not isinstance(self.obj, dict):
            raise ValueError("object must be a dictionary")

    async def execute(self) -> Any:
        keys = list(self.obj.keys())

        return {
            "keys": keys,
            "count": len(keys)
        }


