"""
Array Operation Modules
Array data manipulation and transformation
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='array.unique',
    version='1.0.0',
    category='atomic',
    subcategory='array',
    tags=['array', 'unique', 'dedupe', 'atomic'],
    label='Array Unique',
    label_key='modules.array.unique.label',
    description='Remove duplicate values from array',
    description_key='modules.array.unique.description',
    icon='Layers',
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
            'label_key': 'modules.array.unique.params.array.label',
            'description': 'Array to deduplicate',
            'description_key': 'modules.array.unique.params.array.description',
            'required': True
        },
        'preserve_order': {
            'type': 'boolean',
            'label': 'Preserve Order',
            'label_key': 'modules.array.unique.params.preserve_order.label',
            'description': 'Maintain original order of elements',
            'description_key': 'modules.array.unique.params.preserve_order.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'unique': {
            'type': 'array',
            'description': 'Array with unique values'
        },
        'count': {
            'type': 'number',
            'description': 'Number of unique items'
        },
        'duplicates_removed': {
            'type': 'number',
            'description': 'Number of duplicates removed'
        }
    },
    examples=[
        {
            'title': 'Remove duplicates',
            'title_key': 'modules.array.unique.examples.simple.title',
            'params': {
                'array': [1, 2, 2, 3, 4, 3, 5],
                'preserve_order': True
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def array_unique(context):
    """Remove duplicate values from array"""
    params = context['params']
    array = params['array']
    preserve_order = params.get('preserve_order', True)

    original_count = len(array)

    if preserve_order:
        seen = set()
        unique = []
        for item in array:
            # Handle unhashable types
            try:
                if item not in seen:
                    seen.add(item)
                    unique.append(item)
            except TypeError:
                # For unhashable types, do linear search
                if item not in unique:
                    unique.append(item)
    else:
        unique = list(set(array))

    return {
        'unique': unique,
        'count': len(unique),
        'duplicates_removed': original_count - len(unique)
    }
