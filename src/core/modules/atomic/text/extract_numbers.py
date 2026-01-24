"""
Extract Numbers Module
Extract all numbers from text
"""
from typing import Any, Dict, List
import re

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='text.extract_numbers',
    version='1.0.0',
    category='text',
    tags=['text', 'number', 'extract', 'analysis'],
    label='Extract Numbers',
    label_key='modules.text.extract_numbers.label',
    description='Extract all numbers from text',
    description_key='modules.text.extract_numbers.description',
    icon='Hash',
    color='#F59E0B',
    input_types=['string'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'math.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.text.extract_numbers.params.text.label',
            'description': 'Text to extract numbers from',
            'description_key': 'modules.text.extract_numbers.params.text.description',
            'placeholder': 'There are 42 apples and 3.14 pies',
            'required': True
        },
        'include_decimals': {
            'type': 'boolean',
            'label': 'Include Decimals',
            'label_key': 'modules.text.extract_numbers.params.include_decimals.label',
            'description': 'Include decimal numbers',
            'description_key': 'modules.text.extract_numbers.params.include_decimals.description',
            'default': True,
            'required': False
        },
        'include_negative': {
            'type': 'boolean',
            'label': 'Include Negative',
            'label_key': 'modules.text.extract_numbers.params.include_negative.label',
            'description': 'Include negative numbers',
            'description_key': 'modules.text.extract_numbers.params.include_negative.description',
            'default': True,
            'required': False
        }
    },
    output_schema={
        'numbers': {
            'type': 'array',
            'description': 'List of extracted numbers',
            'description_key': 'modules.text.extract_numbers.output.numbers.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of numbers found',
            'description_key': 'modules.text.extract_numbers.output.count.description'
        },
        'sum': {
            'type': 'number',
            'description': 'Sum of all numbers',
            'description_key': 'modules.text.extract_numbers.output.sum.description'
        },
        'min': {
            'type': 'number',
            'description': 'Minimum value',
            'description_key': 'modules.text.extract_numbers.output.min.description'
        },
        'max': {
            'type': 'number',
            'description': 'Maximum value',
            'description_key': 'modules.text.extract_numbers.output.max.description'
        }
    },
    timeout_ms=5000,
)
async def text_extract_numbers(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all numbers from text."""
    params = context['params']
    text = params.get('text')
    include_decimals = params.get('include_decimals', True)
    include_negative = params.get('include_negative', True)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    if include_decimals and include_negative:
        pattern = r'-?\d+\.?\d*'
    elif include_decimals:
        pattern = r'\d+\.?\d*'
    elif include_negative:
        pattern = r'-?\d+'
    else:
        pattern = r'\d+'

    matches = re.findall(pattern, text)

    numbers = []
    for m in matches:
        try:
            if '.' in m:
                numbers.append(float(m))
            else:
                numbers.append(int(m))
        except ValueError:
            pass

    total_sum = sum(numbers) if numbers else 0
    min_val = min(numbers) if numbers else 0
    max_val = max(numbers) if numbers else 0

    return {
        'ok': True,
        'data': {
            'numbers': numbers,
            'count': len(numbers),
            'sum': total_sum,
            'min': min_val,
            'max': max_val
        }
    }
