"""
String Pad Module
Pad a string to a specified length.
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='string.pad',
    version='1.0.0',
    category='string',
    tags=['string', 'pad', 'fill', 'align', 'format'],
    label='Pad String',
    label_key='modules.string.pad.label',
    description='Pad a string to a specified length',
    description_key='modules.string.pad.description',
    icon='AlignJustify',
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
            label_key='modules.string.pad.params.text.label',
            description='Text to pad',
            description_key='modules.string.pad.params.text.description',
            required=True,
            placeholder='Hello',
            group=FieldGroup.BASIC,
        ),
        field(
            'length',
            type='number',
            label='Length',
            label_key='modules.string.pad.params.length.label',
            description='Target length',
            description_key='modules.string.pad.params.length.description',
            required=True,
            min=1,
            placeholder='10',
            group=FieldGroup.BASIC,
        ),
        field(
            'pad_char',
            type='string',
            label='Pad Character',
            label_key='modules.string.pad.params.pad_char.label',
            description='Character to pad with',
            description_key='modules.string.pad.params.pad_char.description',
            default=' ',
            group=FieldGroup.OPTIONS,
            placeholder='Enter Pad Char...',
        ),
        field(
            'position',
            type='string',
            label='Position',
            label_key='modules.string.pad.params.position.label',
            description='Where to add padding',
            description_key='modules.string.pad.params.position.description',
            default='end',
            options=[
                {'value': 'start', 'label': 'Start (left)'},
                {'value': 'end', 'label': 'End (right)'},
                {'value': 'both', 'label': 'Both (center)'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Padded string',
            'description_key': 'modules.string.pad.output.result.description'
        },
        'original': {
            'type': 'string',
            'description': 'Original string',
            'description_key': 'modules.string.pad.output.original.description'
        },
        'added': {
            'type': 'number',
            'description': 'Characters added',
            'description_key': 'modules.string.pad.output.added.description'
        }
    },
    timeout_ms=5000,
)
async def string_pad(context: Dict[str, Any]) -> Dict[str, Any]:
    """Pad a string to a specified length."""
    params = context['params']
    text = params.get('text')
    length = params.get('length')
    pad_char = params.get('pad_char', ' ')
    position = params.get('position', 'end')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if length is None:
        raise ValidationError("Missing required parameter: length", field="length")

    text = str(text)
    length = int(length)
    pad_char = str(pad_char)[0] if pad_char else ' '

    original = text
    original_len = len(text)

    if original_len >= length:
        result = text
    elif position == 'start':
        result = text.rjust(length, pad_char)
    elif position == 'end':
        result = text.ljust(length, pad_char)
    elif position == 'both':
        result = text.center(length, pad_char)
    else:
        result = text.ljust(length, pad_char)

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': original,
            'added': len(result) - original_len
        }
    }
