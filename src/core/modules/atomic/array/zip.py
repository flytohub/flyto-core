"""
Array Zip Module
Combine multiple arrays element-wise.
"""
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='array.zip',
    version='1.0.0',
    category='array',
    tags=['array', 'zip', 'combine', 'merge', 'advanced'],
    label='Zip Arrays',
    label_key='modules.array.zip.label',
    description='Combine multiple arrays element-wise',
    description_key='modules.array.zip.description',
    icon='Combine',
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
            'arrays',
            type='array',
            label='Arrays',
            label_key='modules.array.zip.params.arrays.label',
            description='Array of arrays to zip',
            description_key='modules.array.zip.params.arrays.description',
            required=True,
            placeholder='[[1, 2, 3], ["a", "b", "c"]]',
            group=FieldGroup.BASIC,
        ),
        field(
            'fill_value',
            type='any',
            label='Fill Value',
            label_key='modules.array.zip.params.fill_value.label',
            description='Value for missing elements',
            description_key='modules.array.zip.params.fill_value.description',
            default=None,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Zipped array',
            'description_key': 'modules.array.zip.output.result.description'
        },
        'length': {
            'type': 'number',
            'description': 'Result length',
            'description_key': 'modules.array.zip.output.length.description'
        }
    },
    timeout_ms=5000,
)
async def array_zip(context: Dict[str, Any]) -> Dict[str, Any]:
    """Combine multiple arrays element-wise."""
    params = context['params']
    arrays = params.get('arrays')
    fill_value = params.get('fill_value')

    if arrays is None:
        raise ValidationError("Missing required parameter: arrays", field="arrays")

    if not isinstance(arrays, list):
        raise ValidationError("Parameter must be an array", field="arrays")

    if len(arrays) == 0:
        return {
            'ok': True,
            'data': {
                'result': [],
                'length': 0
            }
        }

    # Validate all items are arrays
    for i, arr in enumerate(arrays):
        if not isinstance(arr, list):
            raise ValidationError(f"Item at index {i} is not an array", field="arrays")

    # Find max length
    max_length = max(len(arr) for arr in arrays)

    # Zip with fill value
    result = []
    for i in range(max_length):
        row = []
        for arr in arrays:
            if i < len(arr):
                row.append(arr[i])
            else:
                row.append(fill_value)
        result.append(row)

    return {
        'ok': True,
        'data': {
            'result': result,
            'length': len(result)
        }
    }
