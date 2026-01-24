"""
Object Set Module
Set value in object by path.
"""
from typing import Any, Dict
from copy import deepcopy

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='object.set',
    version='1.0.0',
    category='object',
    tags=['object', 'set', 'path', 'modify', 'advanced'],
    label='Set Value',
    label_key='modules.object.set.label',
    description='Set value in object by path',
    description_key='modules.object.set.description',
    icon='Edit',
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
            label_key='modules.object.set.params.object.label',
            description='Object to modify',
            description_key='modules.object.set.params.object.description',
            required=True,
            placeholder='{"a": {"b": 1}}',
            group=FieldGroup.BASIC,
        ),
        field(
            'path',
            type='string',
            label='Path',
            label_key='modules.object.set.params.path.label',
            description='Dot notation path',
            description_key='modules.object.set.params.path.description',
            required=True,
            placeholder='a.b.c',
            group=FieldGroup.BASIC,
        ),
        field(
            'value',
            type='any',
            label='Value',
            label_key='modules.object.set.params.value.label',
            description='Value to set',
            description_key='modules.object.set.params.value.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'result': {
            'type': 'object',
            'description': 'Modified object',
            'description_key': 'modules.object.set.output.result.description'
        }
    },
    timeout_ms=5000,
)
async def object_set(context: Dict[str, Any]) -> Dict[str, Any]:
    """Set value in object by path."""
    params = context['params']
    obj = params.get('object')
    path = params.get('path')
    value = params.get('value')

    if obj is None:
        raise ValidationError("Missing required parameter: object", field="object")

    if path is None:
        raise ValidationError("Missing required parameter: path", field="path")

    if not isinstance(obj, dict):
        raise ValidationError("Parameter must be an object", field="object")

    result = deepcopy(obj)
    parts = str(path).split('.')
    current = result

    for part in parts[:-1]:
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
