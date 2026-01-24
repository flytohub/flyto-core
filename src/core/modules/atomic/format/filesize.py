"""
Format Filesize Module
Format bytes as human-readable file size
"""
from typing import Any, Dict

from ...registry import register_module
from ...errors import ValidationError


BINARY_UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
DECIMAL_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


@register_module(
    module_id='format.filesize',
    version='1.0.0',
    category='format',
    tags=['format', 'filesize', 'bytes', 'size'],
    label='Format Filesize',
    label_key='modules.format.filesize.label',
    description='Format bytes as human-readable file size',
    description_key='modules.format.filesize.description',
    icon='HardDrive',
    color='#EC4899',
    input_types=['number'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['string.*', 'data.*', 'flow.*', 'notification.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'bytes': {
            'type': 'number',
            'label': 'Bytes',
            'label_key': 'modules.format.filesize.params.bytes.label',
            'description': 'Size in bytes',
            'description_key': 'modules.format.filesize.params.bytes.description',
            'placeholder': '1048576',
            'required': True
        },
        'binary': {
            'type': 'boolean',
            'label': 'Binary Units',
            'label_key': 'modules.format.filesize.params.binary.label',
            'description': 'Use binary units (KiB, MiB) instead of decimal (KB, MB)',
            'description_key': 'modules.format.filesize.params.binary.description',
            'default': False,
            'required': False
        },
        'decimal_places': {
            'type': 'number',
            'label': 'Decimal Places',
            'label_key': 'modules.format.filesize.params.decimal_places.label',
            'description': 'Number of decimal places',
            'description_key': 'modules.format.filesize.params.decimal_places.description',
            'default': 2,
            'min': 0,
            'max': 4,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Formatted file size string',
            'description_key': 'modules.format.filesize.output.result.description'
        },
        'original': {
            'type': 'number',
            'description': 'Original bytes',
            'description_key': 'modules.format.filesize.output.original.description'
        },
        'unit': {
            'type': 'string',
            'description': 'Unit used',
            'description_key': 'modules.format.filesize.output.unit.description'
        },
        'value': {
            'type': 'number',
            'description': 'Numeric value in unit',
            'description_key': 'modules.format.filesize.output.value.description'
        }
    },
    timeout_ms=5000,
)
async def format_filesize(context: Dict[str, Any]) -> Dict[str, Any]:
    """Format bytes as human-readable file size."""
    params = context['params']
    bytes_val = params.get('bytes')
    binary = params.get('binary', False)
    decimal_places = params.get('decimal_places', 2)

    if bytes_val is None:
        raise ValidationError("Missing required parameter: bytes", field="bytes")

    try:
        size = float(bytes_val)
    except (ValueError, TypeError):
        raise ValidationError("Invalid bytes value", field="bytes")

    if binary:
        units = BINARY_UNITS
        base = 1024
    else:
        units = DECIMAL_UNITS
        base = 1000

    unit_index = 0
    value = abs(size)

    while value >= base and unit_index < len(units) - 1:
        value /= base
        unit_index += 1

    if size < 0:
        value = -value

    unit = units[unit_index]
    result = f"{value:.{decimal_places}f} {unit}"

    return {
        'ok': True,
        'data': {
            'result': result,
            'original': bytes_val,
            'unit': unit,
            'value': round(value, decimal_places)
        }
    }
