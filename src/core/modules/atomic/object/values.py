"""
Object Operations Modules

Provides object/dictionary manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='object.values',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'values', 'dictionary'],
    label='Object Values',
    label_key='modules.object.values.label',
    description='Get all values from an object',
    description_key='modules.object.values.description',
    icon='List',
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
            'label_key': 'modules.object.values.params.object.label',
            'description': 'Input object/dictionary',
            'description_key': 'modules.object.values.params.object.description',
            'required': True
        }
    },
    output_schema={
        'values': {'type': 'array'},
        'count': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Get object values',
            'params': {
                'object': {'name': 'John', 'age': 30, 'city': 'NYC'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ObjectValuesModule(BaseModule):
    """Object Values Module"""

    def validate_params(self):
        self.obj = self.params.get('object')

        if not isinstance(self.obj, dict):
            raise ValueError("object must be a dictionary")

    async def execute(self) -> Any:
        values = list(self.obj.values())

        return {
            "values": values,
            "count": len(values)
        }


