"""
Object Deep Merge Module
Deep merge multiple objects.
"""
from typing import Any, Dict, List
from copy import deepcopy

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='object.deep_merge',
    version='1.0.0',
    category='object',
    tags=['object', 'merge', 'deep', 'combine', 'advanced'],
    label='Deep Merge',
    label_key='modules.object.deep_merge.label',
    description='Deep merge multiple objects',
    description_key='modules.object.deep_merge.description',
    icon='GitMerge',
    color='#14B8A6',
    input_types=['object', 'array'],
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
            'objects',
            type='array',
            label='Objects',
            label_key='modules.object.deep_merge.params.objects.label',
            description='Array of objects to merge',
            description_key='modules.object.deep_merge.params.objects.description',
            required=True,
            placeholder='[{"a": 1}, {"b": 2}, {"a": 3}]',
            group=FieldGroup.BASIC,
        ),
        field(
            'array_merge',
            type='string',
            label='Array Merge',
            label_key='modules.object.deep_merge.params.array_merge.label',
            description='How to merge arrays',
            description_key='modules.object.deep_merge.params.array_merge.description',
            default='replace',
            options=[
                {'value': 'replace', 'label': 'Replace'},
                {'value': 'concat', 'label': 'Concatenate'},
                {'value': 'union', 'label': 'Union (unique)'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'object',
            'description': 'Merged object',
            'description_key': 'modules.object.deep_merge.output.result.description'
        }
    },
    timeout_ms=5000,
)
async def object_deep_merge(context: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge multiple objects."""
    params = context['params']
    objects = params.get('objects')
    array_merge = params.get('array_merge', 'replace')

    if objects is None:
        raise ValidationError("Missing required parameter: objects", field="objects")

    if not isinstance(objects, list):
        raise ValidationError("Parameter must be an array", field="objects")

    def deep_merge_two(base, override, arr_strategy):
        result = deepcopy(base)

        for key, value in override.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge_two(result[key], value, arr_strategy)
                elif isinstance(result[key], list) and isinstance(value, list):
                    if arr_strategy == 'concat':
                        result[key] = result[key] + value
                    elif arr_strategy == 'union':
                        # Try to create unique list
                        combined = result[key] + value
                        seen = []
                        for item in combined:
                            if item not in seen:
                                seen.append(item)
                        result[key] = seen
                    else:  # replace
                        result[key] = value
                else:
                    result[key] = deepcopy(value)
            else:
                result[key] = deepcopy(value)

        return result

    result = {}
    for obj in objects:
        if isinstance(obj, dict):
            result = deep_merge_two(result, obj, array_merge)

    return {
        'ok': True,
        'data': {
            'result': result
        }
    }
