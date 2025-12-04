"""
Array Operation Modules
Array data manipulation and transformation
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.sort',
    version='1.0.0',
    category='atomic',
    subcategory='array',
    tags=['array', 'sort', 'data', 'atomic'],
    label='Sort Array',
    label_key='modules.array.sort.label',
    description='Sort array elements in ascending or descending order',
    description_key='modules.array.sort.description',
    icon='ArrowUpDown',
    color='#10B981',

    # Phase 2: Execution settings
    # No timeout - instant array operation
    retryable=False,  # Logic errors won't fix themselves
    concurrent_safe=True,  # Stateless operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'array': {
            'type': 'array',
            'label': 'Array',
            'label_key': 'modules.array.sort.params.array.label',
            'description': 'Array to sort',
            'description_key': 'modules.array.sort.params.array.description',
            'required': True
        },
        'order': {
            'type': 'string',
            'label': 'Order',
            'label_key': 'modules.array.sort.params.order.label',
            'description': 'Sort order',
            'description_key': 'modules.array.sort.params.order.description',
            'default': 'asc',
            'required': False,
            'options': [
                {'value': 'asc', 'label': 'Ascending'},
                {'value': 'desc', 'label': 'Descending'}
            ]
        }
    },
    output_schema={
        'sorted': {
            'type': 'array',
            'description': 'Sorted array'
        },
        'count': {
            'type': 'number',
            'description': 'Number of items'
        }
    },
    examples=[
        {
            'title': 'Sort numbers ascending',
            'title_key': 'modules.array.sort.examples.ascending.title',
            'params': {
                'array': [5, 2, 8, 1, 9],
                'order': 'asc'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def array_sort(context):
    """Sort array elements"""
    params = context['params']
    array = params['array']
    order = params.get('order', 'asc')

    sorted_array = sorted(array, reverse=(order == 'desc'))

    return {
        'sorted': sorted_array,
        'count': len(sorted_array)
    }


