"""
Object Operations Modules

Provides object/dictionary manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='object.merge',
    version='1.0.0',
    category='data',
    subcategory='object',
    tags=['object', 'merge', 'combine'],
    label='Object Merge',
    label_key='modules.object.merge.label',
    description='Merge multiple objects into one',
    description_key='modules.object.merge.description',
    icon='Merge',
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
        'objects': {
            'type': 'array',
            'label': 'Objects',
            'label_key': 'modules.object.merge.params.objects.label',
            'description': 'Array of objects to merge',
            'description_key': 'modules.object.merge.params.objects.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'json'}
    },
    examples=[
        {
            'title': 'Merge user data',
            'params': {
                'objects': [
                    {'name': 'John', 'age': 30},
                    {'city': 'NYC', 'country': 'USA'},
                    {'job': 'Engineer'}
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class ObjectMergeModule(BaseModule):
    """Object Merge Module"""

    def validate_params(self):
        self.objects = self.params.get('objects', [])

        if not isinstance(self.objects, list):
            raise ValueError("objects must be an array")

    async def execute(self) -> Any:
        result = {}

        for obj in self.objects:
            if isinstance(obj, dict):
                result.update(obj)

        return {
            "result": result
        }


