"""
Object Flatten Module
Flatten nested object to single level.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='object.flatten',
    version='1.0.0',
    category='object',
    tags=['object', 'flatten', 'nested', 'transform', 'advanced'],
    label='Flatten Object',
    label_key='modules.object.flatten.label',
    description='Flatten nested object to single level',
    description_key='modules.object.flatten.description',
    icon='Minimize2',
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
            label_key='modules.object.flatten.params.object.label',
            description='Nested object to flatten',
            description_key='modules.object.flatten.params.object.description',
            required=True,
            placeholder='{"a": {"b": {"c": 1}}}',
            group=FieldGroup.BASIC,
        ),
        field(
            'separator',
            type='string',
            label='Separator',
            label_key='modules.object.flatten.params.separator.label',
            description='Key separator',
            description_key='modules.object.flatten.params.separator.description',
            default='.',
            group=FieldGroup.OPTIONS,
            placeholder=',',
        ),
        field(
            'max_depth',
            type='number',
            label='Max Depth',
            label_key='modules.object.flatten.params.max_depth.label',
            description='Maximum depth to flatten (0 = unlimited)',
            description_key='modules.object.flatten.params.max_depth.description',
            default=0,
            min=0,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'object',
            'description': 'Flattened object',
            'description_key': 'modules.object.flatten.output.result.description'
        },
        'keys': {
            'type': 'array',
            'description': 'Flattened keys',
            'description_key': 'modules.object.flatten.output.keys.description'
        }
    },
    timeout_ms=5000,
)
async def object_flatten(context: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested object to single level."""
    params = context['params']
    obj = params.get('object')
    separator = params.get('separator', '.')
    max_depth = params.get('max_depth', 0)

    if obj is None:
        raise ValidationError("Missing required parameter: object", field="object")

    if not isinstance(obj, dict):
        raise ValidationError("Parameter must be an object", field="object")

    def flatten(d, parent_key='', depth=0):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{separator}{k}" if parent_key else k

            if isinstance(v, dict) and len(v) > 0:
                if max_depth == 0 or depth < max_depth:
                    items.update(flatten(v, new_key, depth + 1))
                else:
                    items[new_key] = v
            else:
                items[new_key] = v

        return items

    result = flatten(obj)

    return {
        'ok': True,
        'data': {
            'result': result,
            'keys': list(result.keys())
        }
    }
