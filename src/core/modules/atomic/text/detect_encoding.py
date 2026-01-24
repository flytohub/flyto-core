"""
Detect Encoding Module
Detect text encoding using heuristics
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


def detect_encoding_heuristic(data: bytes) -> tuple:
    """
    Simple encoding detection using heuristics.
    Returns (encoding, confidence)
    """
    if data.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig', 1.0

    if data.startswith(b'\xff\xfe\x00\x00'):
        return 'utf-32-le', 1.0

    if data.startswith(b'\x00\x00\xfe\xff'):
        return 'utf-32-be', 1.0

    if data.startswith(b'\xff\xfe'):
        return 'utf-16-le', 1.0

    if data.startswith(b'\xfe\xff'):
        return 'utf-16-be', 1.0

    try:
        data.decode('utf-8')
        has_high_bytes = any(b > 127 for b in data)
        if has_high_bytes:
            return 'utf-8', 0.9
        else:
            return 'ascii', 0.95
    except UnicodeDecodeError:
        pass

    try:
        data.decode('iso-8859-1')
        return 'iso-8859-1', 0.6
    except UnicodeDecodeError:
        pass

    try:
        data.decode('cp1252')
        return 'cp1252', 0.5
    except UnicodeDecodeError:
        pass

    return 'unknown', 0.0


@register_module(
    module_id='text.detect_encoding',
    version='1.0.0',
    category='text',
    tags=['text', 'encoding', 'detect', 'charset', 'analysis'],
    label='Detect Encoding',
    label_key='modules.text.detect_encoding.label',
    description='Detect text encoding',
    description_key='modules.text.detect_encoding.description',
    icon='FileCode',
    color='#F59E0B',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'flow.*', 'file.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.text.detect_encoding.params.text.label',
            'description': 'Text or bytes to detect encoding',
            'description_key': 'modules.text.detect_encoding.params.text.description',
            'placeholder': 'Enter text',
            'required': True
        }
    },
    output_schema={
        'encoding': {
            'type': 'string',
            'description': 'Detected encoding',
            'description_key': 'modules.text.detect_encoding.output.encoding.description'
        },
        'confidence': {
            'type': 'number',
            'description': 'Confidence score (0-1)',
            'description_key': 'modules.text.detect_encoding.output.confidence.description'
        },
        'is_ascii': {
            'type': 'boolean',
            'description': 'Whether text is pure ASCII',
            'description_key': 'modules.text.detect_encoding.output.is_ascii.description'
        },
        'has_bom': {
            'type': 'boolean',
            'description': 'Whether BOM was detected',
            'description_key': 'modules.text.detect_encoding.output.has_bom.description'
        }
    },
    timeout_ms=5000,
)
async def text_detect_encoding(context: Dict[str, Any]) -> Dict[str, Any]:
    """Detect text encoding."""
    params = context['params']
    text = params.get('text')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    if isinstance(text, bytes):
        data = text
    else:
        data = str(text).encode('utf-8', errors='surrogateescape')

    encoding, confidence = detect_encoding_heuristic(data)

    is_ascii = all(b < 128 for b in data)

    has_bom = (
        data.startswith(b'\xef\xbb\xbf') or
        data.startswith(b'\xff\xfe') or
        data.startswith(b'\xfe\xff') or
        data.startswith(b'\xff\xfe\x00\x00') or
        data.startswith(b'\x00\x00\xfe\xff')
    )

    return {
        'ok': True,
        'data': {
            'encoding': encoding,
            'confidence': confidence,
            'is_ascii': is_ascii,
            'has_bom': has_bom
        }
    }
