"""
Regex Extract Module
Extract named groups from text using regex.
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='regex.extract',
    version='1.0.0',
    category='regex',
    tags=['regex', 'extract', 'groups', 'pattern', 'parse'],
    label='Regex Extract',
    label_key='modules.regex.extract.label',
    description='Extract named groups from text',
    description_key='modules.regex.extract.description',
    icon='FileOutput',
    color='#EC4899',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['object.*', 'data.*', 'flow.*'],

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
            label_key='modules.regex.extract.params.text.label',
            description='Text to extract from',
            description_key='modules.regex.extract.params.text.description',
            required=True,
            placeholder='Name: John, Age: 30',
            group=FieldGroup.BASIC,
        ),
        field(
            'pattern',
            type='string',
            label='Pattern',
            label_key='modules.regex.extract.params.pattern.label',
            description='Regex with named groups (?P<name>...)',
            description_key='modules.regex.extract.params.pattern.description',
            required=True,
            placeholder='Name: (?P<name>\\w+), Age: (?P<age>\\d+)',
            group=FieldGroup.BASIC,
        ),
        field(
            'ignore_case',
            type='boolean',
            label='Ignore Case',
            label_key='modules.regex.extract.params.ignore_case.label',
            description='Case-insensitive matching',
            description_key='modules.regex.extract.params.ignore_case.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'extracted': {
            'type': 'object',
            'description': 'Extracted named groups',
            'description_key': 'modules.regex.extract.output.extracted.description'
        },
        'matched': {
            'type': 'boolean',
            'description': 'Whether pattern matched',
            'description_key': 'modules.regex.extract.output.matched.description'
        },
        'full_match': {
            'type': 'string',
            'description': 'Full matched text',
            'description_key': 'modules.regex.extract.output.full_match.description'
        }
    },
    timeout_ms=5000,
)
async def regex_extract(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract named groups from text."""
    params = context['params']
    text = params.get('text')
    pattern = params.get('pattern')
    ignore_case = params.get('ignore_case', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if pattern is None:
        raise ValidationError("Missing required parameter: pattern", field="pattern")

    flags = re.IGNORECASE if ignore_case else 0

    try:
        regex = re.compile(pattern, flags)
        match = regex.search(str(text))

        if match:
            extracted = match.groupdict()
            matched = True
            full_match = match.group()
        else:
            extracted = {}
            matched = False
            full_match = ''
    except re.error as e:
        raise ValidationError(f"Invalid regex pattern: {e}", field="pattern")

    return {
        'ok': True,
        'data': {
            'extracted': extracted,
            'matched': matched,
            'full_match': full_match
        }
    }
