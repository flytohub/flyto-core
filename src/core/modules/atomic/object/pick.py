"""
Object Operations Modules

Provides object/dictionary manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='object.pick',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'pick', 'select'],
    label='Object Pick',
    label_key='modules.object.pick.label',
    description='Pick specific keys from an object',
    description_key='modules.object.pick.description',
    icon='Check',
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
            'label_key': 'modules.object.pick.params.object.label',
            'description': 'Input object',
            'description_key': 'modules.object.pick.params.object.description',
            'required': True
        },
        'keys': {
            'type': 'array',
            'label': 'Keys',
            'label_key': 'modules.object.pick.params.keys.label',
            'description': 'Keys to pick',
            'description_key': 'modules.object.pick.params.keys.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'json'}
    },
    examples=[
        {
            'title': 'Pick user fields',
            'params': {
                'object': {'name': 'John', 'age': 30, 'email': 'john@example.com', 'password': 'secret'},
                'keys': ['name', 'email']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ObjectPickModule(BaseModule):
    """Object Pick Module"""

    def validate_params(self):
        self.obj = self.params.get('object')
        self.keys = self.params.get('keys', [])

        if not isinstance(self.obj, dict):
            raise ValueError("object must be a dictionary")

        if not isinstance(self.keys, list):
            raise ValueError("keys must be an array")

    async def execute(self) -> Any:
        result = {key: self.obj[key] for key in self.keys if key in self.obj}

        return {
            "result": result
        }


