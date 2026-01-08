"""
Object Merge Module
Merge multiple objects into one
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets
from ...errors import InvalidTypeError


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
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.INPUT_OBJECTS(required=True),
    ),
    output_schema={
        'result': {
            'type': 'json',
            'description': 'Merged object'
        ,
                'description_key': 'modules.object.merge.output.result.description'}
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
async def object_merge(context: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple objects into one."""
    params = context['params']
    objects = params.get('objects', [])

    if not isinstance(objects, list):
        raise InvalidTypeError(
            "objects must be an array",
            field="objects",
            expected_type="list",
            actual_type=type(objects).__name__
        )

    result = {}

    for obj in objects:
        if isinstance(obj, dict):
            result.update(obj)

    return {
        'ok': True,
        'data': {
            'result': result
        }
    }
