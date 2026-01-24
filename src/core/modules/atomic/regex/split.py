"""
Regex Split Module
Split text by a regex pattern.
"""
from typing import Any, Dict, List
import re

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='regex.split',
    version='1.0.0',
    category='regex',
    tags=['regex', 'split', 'divide', 'pattern', 'array'],
    label='Regex Split',
    label_key='modules.regex.split.label',
    description='Split text by a regex pattern',
    description_key='modules.regex.split.description',
    icon='Scissors',
    color='#EC4899',
    input_types=['string'],
    output_types=['array'],

    can_receive_from=['*'],
    can_connect_to=['array.*', 'string.*', 'data.*', 'flow.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'text',
            type='text',
            label='Text',
            label_key='modules.regex.split.params.text.label',
            description='Text to split',
            description_key='modules.regex.split.params.text.description',
            required=True,
            placeholder='apple,banana;cherry|date',
            group=FieldGroup.BASIC,
        ),
        field(
            'pattern',
            type='string',
            label='Pattern',
            label_key='modules.regex.split.params.pattern.label',
            description='Regular expression pattern for delimiter',
            description_key='modules.regex.split.params.pattern.description',
            required=True,
            placeholder='[,;|]',
            group=FieldGroup.BASIC,
        ),
        field(
            'ignore_case',
            type='boolean',
            label='Ignore Case',
            label_key='modules.regex.split.params.ignore_case.label',
            description='Case-insensitive matching',
            description_key='modules.regex.split.params.ignore_case.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'max_split',
            type='number',
            label='Max Split',
            label_key='modules.regex.split.params.max_split.label',
            description='Maximum number of splits (0 = unlimited)',
            description_key='modules.regex.split.params.max_split.description',
            default=0,
            min=0,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'remove_empty',
            type='boolean',
            label='Remove Empty',
            label_key='modules.regex.split.params.remove_empty.label',
            description='Remove empty strings from result',
            description_key='modules.regex.split.params.remove_empty.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'array',
            'description': 'Split parts',
            'description_key': 'modules.regex.split.output.result.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of parts',
            'description_key': 'modules.regex.split.output.count.description'
        }
    },
    timeout_ms=5000,
)
async def regex_split(context: Dict[str, Any]) -> Dict[str, Any]:
    """Split text by a regex pattern."""
    params = context['params']
    text = params.get('text')
    pattern = params.get('pattern')
    ignore_case = params.get('ignore_case', False)
    max_split = params.get('max_split', 0)
    remove_empty = params.get('remove_empty', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if pattern is None:
        raise ValidationError("Missing required parameter: pattern", field="pattern")

    flags = re.IGNORECASE if ignore_case else 0

    try:
        regex = re.compile(pattern, flags)
        if max_split > 0:
            result = regex.split(str(text), maxsplit=int(max_split))
        else:
            result = regex.split(str(text))

        if remove_empty:
            result = [part for part in result if part]
    except re.error as e:
        raise ValidationError(f"Invalid regex pattern: {e}", field="pattern")

    return {
        'ok': True,
        'data': {
            'result': result,
            'count': len(result)
        }
    }
