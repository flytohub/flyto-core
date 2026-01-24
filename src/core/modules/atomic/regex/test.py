"""
Regex Test Module
Test if a string matches a regular expression pattern.
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='regex.test',
    version='1.0.0',
    category='regex',
    tags=['regex', 'test', 'match', 'pattern', 'validate'],
    label='Regex Test',
    label_key='modules.regex.test.label',
    description='Test if string matches a regex pattern',
    description_key='modules.regex.test.description',
    icon='Search',
    color='#EC4899',
    input_types=['string'],
    output_types=['boolean'],

    can_receive_from=['*'],
    can_connect_to=['logic.*', 'flow.*', 'data.*'],

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
            label_key='modules.regex.test.params.text.label',
            description='Text to test',
            description_key='modules.regex.test.params.text.description',
            required=True,
            placeholder='Hello World 123',
            group=FieldGroup.BASIC,
        ),
        field(
            'pattern',
            type='string',
            label='Pattern',
            label_key='modules.regex.test.params.pattern.label',
            description='Regular expression pattern',
            description_key='modules.regex.test.params.pattern.description',
            required=True,
            placeholder='\\d+',
            group=FieldGroup.BASIC,
        ),
        field(
            'ignore_case',
            type='boolean',
            label='Ignore Case',
            label_key='modules.regex.test.params.ignore_case.label',
            description='Case-insensitive matching',
            description_key='modules.regex.test.params.ignore_case.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'full_match',
            type='boolean',
            label='Full Match',
            label_key='modules.regex.test.params.full_match.label',
            description='Require pattern to match entire string',
            description_key='modules.regex.test.params.full_match.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'boolean',
            'description': 'Whether pattern matches',
            'description_key': 'modules.regex.test.output.result.description'
        },
        'pattern': {
            'type': 'string',
            'description': 'Pattern used',
            'description_key': 'modules.regex.test.output.pattern.description'
        }
    },
    timeout_ms=5000,
)
async def regex_test(context: Dict[str, Any]) -> Dict[str, Any]:
    """Test if string matches a regex pattern."""
    params = context['params']
    text = params.get('text')
    pattern = params.get('pattern')
    ignore_case = params.get('ignore_case', False)
    full_match = params.get('full_match', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if pattern is None:
        raise ValidationError("Missing required parameter: pattern", field="pattern")

    flags = re.IGNORECASE if ignore_case else 0

    try:
        regex = re.compile(pattern, flags)
        if full_match:
            match = regex.fullmatch(str(text))
        else:
            match = regex.search(str(text))
        result = match is not None
    except re.error as e:
        raise ValidationError(f"Invalid regex pattern: {e}", field="pattern")

    return {
        'ok': True,
        'data': {
            'result': result,
            'pattern': pattern
        }
    }
