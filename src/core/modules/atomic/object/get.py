"""
Object Get Module
Get value from object by path.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='object.get',
    version='1.0.0',
    category='object',
    tags=['object', 'get', 'path', 'access', 'advanced'],
    label='Get Value',
    label_key='modules.object.get.label',
    description='Get value from object by path',
    description_key='modules.object.get.description',
    icon='Search',
    color='#14B8A6',
    input_types=['object'],
    output_types=['any'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'flow.*'],

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
            label_key='modules.object.get.params.object.label',
            description='Object to get value from',
            description_key='modules.object.get.params.object.description',
            required=True,
            placeholder='{"a": {"b": {"c": 123}}}',
            group=FieldGroup.BASIC,
        ),
        field(
            'path',
            type='string',
            label='Path',
            label_key='modules.object.get.params.path.label',
            description='Dot notation path',
            description_key='modules.object.get.params.path.description',
            required=True,
            placeholder='a.b.c',
            group=FieldGroup.BASIC,
        ),
        field(
            'default',
            type='any',
            label='Default',
            label_key='modules.object.get.params.default.label',
            description='Default value if path not found',
            description_key='modules.object.get.params.default.description',
            default=None,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'value': {
            'type': 'any',
            'description': 'Retrieved value',
            'description_key': 'modules.object.get.output.value.description'
        },
        'found': {
            'type': 'boolean',
            'description': 'Whether path was found',
            'description_key': 'modules.object.get.output.found.description'
        }
    },
    timeout_ms=5000,
)
async def object_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Get value from object by path."""
    params = context['params']
    obj = params.get('object')
    path = params.get('path')
    default = params.get('default')

    if obj is None:
        raise ValidationError("Missing required parameter: object", field="object")

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    if not isinstance(obj, dict):
        raise ValidationError("Parameter must be an object", field="object")

    parts = str(path).split('.')
    current = obj
    found = True

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    current = default
                    found = False
                    break
            except ValueError:
                current = default
                found = False
                break
        else:
            current = default
            found = False
            break

    return {
        'ok': True,
        'data': {
            'value': current,
            'found': found
        }
    }
