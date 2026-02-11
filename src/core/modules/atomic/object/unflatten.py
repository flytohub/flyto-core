"""
Object Unflatten Module
Unflatten object with dot notation keys to nested object.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='object.unflatten',
    version='1.0.0',
    category='object',
    tags=['object', 'unflatten', 'nested', 'transform', 'advanced'],
    label='Unflatten Object',
    label_key='modules.object.unflatten.label',
    description='Unflatten object with dot notation to nested',
    description_key='modules.object.unflatten.description',
    icon='Maximize2',
    color='#14B8A6',
    input_types=['object'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'object.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'object',
            type='object',
            label='Object',
            label_key='modules.object.unflatten.params.object.label',
            description='Flat object to unflatten',
            description_key='modules.object.unflatten.params.object.description',
            required=True,
            placeholder='{"a.b.c": 1, "a.b.d": 2}',
            group=FieldGroup.BASIC,
        ),
        field(
            'separator',
            type='string',
            label='Separator',
            label_key='modules.object.unflatten.params.separator.label',
            description='Key separator',
            description_key='modules.object.unflatten.params.separator.description',
            default='.',
            group=FieldGroup.OPTIONS,
            placeholder=',',
        ),
    ),
    output_schema={
        'result': {
            'type': 'object',
            'description': 'Nested object',
            'description_key': 'modules.object.unflatten.output.result.description'
        }
    },
    timeout_ms=5000,
)
async def object_unflatten(context: Dict[str, Any]) -> Dict[str, Any]:
    """Unflatten object with dot notation to nested."""
    params = context['params']
    obj = params.get('object')
    separator = params.get('separator', '.')

    if obj is None:
        raise ValidationError("Missing required parameter: object", field="object")

    if not isinstance(obj, dict):
        raise ValidationError("Parameter must be an object", field="object")

    result = {}

    for key, value in obj.items():
        parts = key.split(separator)
        current = result

        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

    return {
        'ok': True,
        'data': {
            'result': result
        }
    }
