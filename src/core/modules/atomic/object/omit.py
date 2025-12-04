"""
Object Operations Modules

Provides object/dictionary manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='object.omit',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'omit', 'exclude'],
    label='Object Omit',
    label_key='modules.object.omit.label',
    description='Omit specific keys from an object',
    description_key='modules.object.omit.description',
    icon='X',
    color='#F59E0B',

    # Connection types
    input_types=['json'],
    output_types=['json'],

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
            'label_key': 'modules.object.omit.params.object.label',
            'description': 'Input object',
            'description_key': 'modules.object.omit.params.object.description',
            'required': True
        },
        'keys': {
            'type': 'array',
            'label': 'Keys',
            'label_key': 'modules.object.omit.params.keys.label',
            'description': 'Keys to omit',
            'description_key': 'modules.object.omit.params.keys.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'json'}
    },
    examples=[
        {
            'title': 'Omit sensitive fields',
            'params': {
                'object': {'name': 'John', 'age': 30, 'password': 'secret', 'ssn': '123-45-6789'},
                'keys': ['password', 'ssn']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ObjectOmitModule(BaseModule):
    """Object Omit Module"""

    def validate_params(self):
        self.obj = self.params.get('object')
        self.keys = self.params.get('keys', [])

        if not isinstance(self.obj, dict):
            raise ValueError("object must be a dictionary")

        if not isinstance(self.keys, list):
            raise ValueError("keys must be an array")

    async def execute(self) -> Any:
        result = {key: value for key, value in self.obj.items() if key not in self.keys}

        return {
            "result": result
        }
