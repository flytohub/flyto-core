"""
String Truncate Module
Truncate a string to a maximum length.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='string.truncate',
    version='1.0.0',
    category='string',
    tags=['string', 'truncate', 'cut', 'limit', 'shorten'],
    label='Truncate String',
    label_key='modules.string.truncate.label',
    description='Truncate a string to a maximum length',
    description_key='modules.string.truncate.description',
    icon='Scissors',
    color='#6366F1',
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
            label_key='modules.string.truncate.params.text.label',
            description='Text to truncate',
            description_key='modules.string.truncate.params.text.description',
            required=True,
            placeholder='This is a long text that needs to be shortened',
            group=FieldGroup.BASIC,
        ),
        field(
            'length',
            type='number',
            label='Max Length',
            label_key='modules.string.truncate.params.length.label',
            description='Maximum length',
            description_key='modules.string.truncate.params.length.description',
            required=True,
            min=1,
            placeholder='20',
            group=FieldGroup.BASIC,
        ),
        field(
            'suffix',
            type='string',
            label='Suffix',
            label_key='modules.string.truncate.params.suffix.label',
            description='Text to append if truncated',
            description_key='modules.string.truncate.params.suffix.description',
            default='...',
            group=FieldGroup.OPTIONS,
            placeholder='-suffix',
        ),
        field(
            'word_boundary',
            type='boolean',
            label='Word Boundary',
            label_key='modules.string.truncate.params.word_boundary.label',
            description='Break at word boundary',
            description_key='modules.string.truncate.params.word_boundary.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Truncated string',
            'description_key': 'modules.string.truncate.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original string',
            'description_key': 'modules.string.truncate.output.original.description'
        },
        'truncated': {
            'type': 'boolean',
            'description': 'Whether string was truncated',
            'description_key': 'modules.string.truncate.output.truncated.description'
        },
        'removed': {
            'type': 'number',
            'description': 'Characters removed',
            'description_key': 'modules.string.truncate.output.removed.description'
        }
    },
    timeout_ms=5000,
)
async def string_truncate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Truncate a string to a maximum length."""
    params = context['params']
    text = params.get('text')
    length = params.get('length')
    suffix = params.get('suffix', '...')
    word_boundary = params.get('word_boundary', False)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if length is None:
        raise ValidationError("Missing required parameter: length", field="length")

    text = str(text)
    length = int(length)
    suffix = str(suffix) if suffix else ''

    original = text
    original_len = len(text)

    if original_len <= length:
        result = text
        truncated = False
    else:
        # Reserve space for suffix
        cut_length = length - len(suffix)

        if cut_length < 1:
            cut_length = 1

        result = text[:cut_length]

        if word_boundary:
            # Find last space
            last_space = result.rfind(' ')
            if last_space > 0:
                result = result[:last_space]

        result = result.rstrip() + suffix
        truncated = True

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': original,
            'truncated': truncated,
            'removed': original_len - len(result) + len(suffix) if truncated else 0
        }
    }
