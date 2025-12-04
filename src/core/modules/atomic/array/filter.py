"""
Array Operation Modules
Array data manipulation and transformation
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.filter',
    version='1.0.0',
    category='atomic',
    subcategory='array',
    tags=['array', 'filter', 'data', 'atomic'],
    label='Filter Array',
    label_key='modules.array.filter.label',
    description='Filter array elements by condition',
    description_key='modules.array.filter.description',
    icon='Filter',
    color='#10B981',

    # Connection types
    input_types=['any'],
    output_types=['any'],

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
            'label_key': 'modules.array.filter.params.array.label',
            'description': 'Array to filter',
            'description_key': 'modules.array.filter.params.array.description',
            'required': True
        },
        'condition': {
            'type': 'string',
            'label': 'Condition',
            'label_key': 'modules.array.filter.params.condition.label',
            'description': 'Filter condition (gt, lt, eq, ne, contains)',
            'description_key': 'modules.array.filter.params.condition.description',
            'required': True,
            'options': [
                {'value': 'gt', 'label': 'Greater Than'},
                {'value': 'lt', 'label': 'Less Than'},
                {'value': 'eq', 'label': 'Equal'},
                {'value': 'ne', 'label': 'Not Equal'},
                {'value': 'contains', 'label': 'Contains'}
            ]
        },
        'value': {
            'type': 'string',
            'label': 'Value',
            'label_key': 'modules.array.filter.params.value.label',
            'description': 'Value to compare against',
            'description_key': 'modules.array.filter.params.value.description',
            'required': True
        }
    },
    output_schema={
        'filtered': {
            'type': 'array',
            'description': 'Filtered array'
        },
        'count': {
            'type': 'number',
            'description': 'Number of items in filtered array'
        }
    },
    examples=[
        {
            'title': 'Filter numbers greater than 5',
            'title_key': 'modules.array.filter.examples.numbers.title',
            'params': {
                'array': [1, 5, 10, 15, 3],
                'condition': 'gt',
                'value': '5'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def array_filter(context):
    """Filter array by condition"""
    params = context['params']
    array = params['array']
    condition = params['condition']
    value = params['value']

    # Try to convert value to number if possible
    try:
        value = float(value)
    except (ValueError, TypeError):
        pass

    filtered = []
    for item in array:
        if condition == 'gt':
            if isinstance(item, (int, float)) and isinstance(value, (int, float)) and item > value:
                filtered.append(item)
        elif condition == 'lt':
            if isinstance(item, (int, float)) and isinstance(value, (int, float)) and item < value:
                filtered.append(item)
        elif condition == 'eq':
            if item == value:
                filtered.append(item)
        elif condition == 'ne':
            if item != value:
                filtered.append(item)
        elif condition == 'contains':
            if isinstance(item, str) and isinstance(value, str) and value in item:
                filtered.append(item)

    return {
        'filtered': filtered,
        'count': len(filtered)
    }


