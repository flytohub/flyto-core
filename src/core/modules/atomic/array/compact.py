"""
Array Compact Module
Remove null/empty values from array.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='array.compact',
    version='1.0.0',
    category='array',
    tags=['array', 'compact', 'clean', 'filter', 'advanced'],
    label='Compact',
    label_key='modules.array.compact.label',
    description='Remove null/empty values from array',
    description_key='modules.array.compact.description',
    icon='Filter',
    color='#8B5CF6',
    input_types=['array'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'array',
            type='array',
            label='Array',
            label_key='modules.array.compact.params.array.label',
            description='Array to compact',
            description_key='modules.array.compact.params.array.description',
            required=True,
            placeholder='[1, null, 2, "", 3, false, 0]',
            group=FieldGroup.BASIC,
        ),
        field(
            'remove_empty_strings',
            type='boolean',
            label='Remove Empty Strings',
            label_key='modules.array.compact.params.remove_empty_strings.label',
            description='Remove empty strings',
            description_key='modules.array.compact.params.remove_empty_strings.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'remove_zero',
            type='boolean',
            label='Remove Zero',
            label_key='modules.array.compact.params.remove_zero.label',
            description='Remove zero values',
            description_key='modules.array.compact.params.remove_zero.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'remove_false',
            type='boolean',
            label='Remove False',
            label_key='modules.array.compact.params.remove_false.label',
            description='Remove false values',
            description_key='modules.array.compact.params.remove_false.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Compacted array',
            'description_key': 'modules.array.compact.output.result.description'
        },
        'removed': {
            'type': 'number',
            'description': 'Number of items removed',
            'description_key': 'modules.array.compact.output.removed.description'
        }
    },
    timeout_ms=5000,
)
async def array_compact(context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove null/empty values from array."""
    params = context['params']
    array = params.get('array')
    remove_empty_strings = params.get('remove_empty_strings', True)
    remove_zero = params.get('remove_zero', False)
    remove_false = params.get('remove_false', False)

    if array is None:
        raise ValidationError("Missing required parameter: array", field="array")

    if not isinstance(array, list):
        raise ValidationError("Parameter must be an array", field="array")

    original_length = len(array)
    result = []

    for item in array:
        # Always remove None
        if item is None:
            continue

        # Optionally remove empty strings
        if remove_empty_strings and item == '':
            continue

        # Optionally remove zero
        if remove_zero and item == 0:
            continue

        # Optionally remove false
        if remove_false and item is False:
            continue

        result.append(item)

    return {
        'ok': True,
        'data': {
            'result': result,
            'removed': original_length - len(result)
        }
    }
