"""
Object Operations Modules

Provides object/dictionary manipulation capabilities.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


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


    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],    # Phase 2: Execution settings
    timeout=None,
    retryable=False,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_OBJECTS(required=True),
    ),
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


