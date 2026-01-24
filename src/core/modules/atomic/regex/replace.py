"""
Regex Replace Module
Replace pattern matches in text.
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='regex.replace',
    version='1.0.0',
    category='regex',
    tags=['regex', 'replace', 'substitute', 'pattern', 'transform'],
    label='Regex Replace',
    label_key='modules.regex.replace.label',
    description='Replace pattern matches in text',
    description_key='modules.regex.replace.description',
    icon='Replace',
    color='#EC4899',
    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['string.*', 'data.*', 'flow.*'],

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
            label_key='modules.regex.replace.params.text.label',
            description='Text to process',
            description_key='modules.regex.replace.params.text.description',
            required=True,
            placeholder='Hello 123 World 456',
            group=FieldGroup.BASIC,
        ),
        field(
            'pattern',
            type='string',
            label='Pattern',
            label_key='modules.regex.replace.params.pattern.label',
            description='Regular expression pattern',
            description_key='modules.regex.replace.params.pattern.description',
            required=True,
            placeholder='\\d+',
            group=FieldGroup.BASIC,
        ),
        field(
            'replacement',
            type='string',
            label='Replacement',
            label_key='modules.regex.replace.params.replacement.label',
            description='Replacement text (supports backreferences)',
            description_key='modules.regex.replace.params.replacement.description',
            required=True,
            placeholder='[NUMBER]',
            group=FieldGroup.BASIC,
        ),
        field(
            'ignore_case',
            type='boolean',
            label='Ignore Case',
            label_key='modules.regex.replace.params.ignore_case.label',
            description='Case-insensitive matching',
            description_key='modules.regex.replace.params.ignore_case.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'count',
            type='number',
            label='Max Count',
            label_key='modules.regex.replace.params.count.label',
            description='Maximum replacements (0 = unlimited)',
            description_key='modules.regex.replace.params.count.description',
            default=0,
            min=0,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Text with replacements',
            'description_key': 'modules.regex.replace.output.result.description'
        },
        'replacements': {
            'type': 'number',
            'description': 'Number of replacements made',
            'description_key': 'modules.regex.replace.output.replacements.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original text',
            'description_key': 'modules.regex.replace.output.original.description'
        }
    },
    timeout_ms=5000,
)
async def regex_replace(context: Dict[str, Any]) -> Dict[str, Any]:
    """Replace pattern matches in text."""
    params = context['params']
    text = params.get('text')
    pattern = params.get('pattern')
    replacement = params.get('replacement')
    ignore_case = params.get('ignore_case', False)
    count = params.get('count', 0)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if pattern is None:
        raise ValidationError("Missing required parameter: pattern", field="pattern")

    if replacement is None:
        raise ValidationError("Missing required parameter: replacement", field="replacement")

    flags = re.IGNORECASE if ignore_case else 0

    try:
        regex = re.compile(pattern, flags)
        original = str(text)

        # Count matches before replacement
        match_count = len(regex.findall(original))

        if count > 0:
            result = regex.sub(replacement, original, count=int(count))
            replacements = min(match_count, int(count))
        else:
            result = regex.sub(replacement, original)
            replacements = match_count
    except re.error as e:
        raise ValidationError(f"Invalid regex pattern: {e}", field="pattern")

    return {
        'ok': True,
        'data': {
            'result': result,
            'replacements': replacements,
            'original': original
        }
    }
