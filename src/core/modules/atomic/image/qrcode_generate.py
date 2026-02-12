"""
QR Code Generator Module
Generate QR codes from text, URLs, or data
"""
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='image.qrcode_generate',
    version='1.0.0',
    category='image',
    subcategory='generate',
    tags=['qrcode', 'qr', 'image', 'generate', 'barcode', 'path_restricted'],
    label='Generate QR Code',
    label_key='modules.image.qrcode_generate.label',
    description='Generate QR codes from text, URLs, or data',
    description_key='modules.image.qrcode_generate.description',
    icon='QrCode',
    color='#1F2937',

    # Connection types
    input_types=['string', 'object'],
    output_types=['file_path', 'bytes'],
    can_connect_to=['file.*', 'image.*'],
    can_receive_from=['file.*', 'browser.*', 'screenshot.*', 'api.*', 'flow.*', 'start'],

    # Execution settings
    timeout_ms=60000,
    retryable=True,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        presets.QRCODE_DATA(),
        presets.IMAGE_OUTPUT_PATH(key='output_path', placeholder='/tmp/qrcode.png'),
        presets.QRCODE_SIZE(),
        presets.QRCODE_COLOR(),
        presets.QRCODE_BACKGROUND(),
        presets.QRCODE_ERROR_CORRECTION(),
        presets.QRCODE_LOGO_PATH(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the generated QR code image'
        ,
                'description_key': 'modules.image.qrcode_generate.output.output_path.description'},
        'file_size': {
            'type': 'number',
            'description': 'Size of the output file in bytes'
        ,
                'description_key': 'modules.image.qrcode_generate.output.file_size.description'},
        'dimensions': {
            'type': 'object',
            'description': 'Image dimensions {width, height}'
        ,
                'description_key': 'modules.image.qrcode_generate.output.dimensions.description'}
    },
    examples=[
        {
            'title': 'Generate URL QR code',
            'title_key': 'modules.image.qrcode_generate.examples.url.title',
            'params': {
                'data': 'https://flyto.dev',
                'output_path': '/tmp/flyto_qr.png'
            }
        },
        {
            'title': 'Custom styled QR code',
            'title_key': 'modules.image.qrcode_generate.examples.styled.title',
            'params': {
                'data': 'Hello World',
                'color': '#6366F1',
                'size': 500,
                'error_correction': 'H'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def qrcode_generate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate QR code image"""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
    except ImportError:
        raise ImportError("qrcode is required. Install with: pip install qrcode[pil]")

    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow is required. Install with: pip install Pillow")

    params = context['params']
    data = params['data']
    output_path = params.get('output_path', '/tmp/qrcode.png')
    size = params.get('size', 300)
    color = params.get('color', '#000000')
    background = params.get('background', '#FFFFFF')
    error_correction = params.get('error_correction', 'M')
    logo_path = params.get('logo_path')

    # Map error correction level
    ec_map = {
        'L': ERROR_CORRECT_L,
        'M': ERROR_CORRECT_M,
        'Q': ERROR_CORRECT_Q,
        'H': ERROR_CORRECT_H
    }
    ec_level = ec_map.get(error_correction, ERROR_CORRECT_M)

    # Create output directory if needed
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=ec_level,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    # Create image
    img = qr.make_image(fill_color=color, back_color=background)

    # Resize to desired size
    img = img.resize((size, size), Image.Resampling.LANCZOS)

    # Add logo if provided
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path)
            # Logo should be ~25% of QR code size
            logo_size = int(size * 0.25)
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

            # Calculate center position
            logo_pos = ((size - logo_size) // 2, (size - logo_size) // 2)

            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Paste logo
            if logo.mode == 'RGBA':
                img.paste(logo, logo_pos, logo)
            else:
                img.paste(logo, logo_pos)
        except Exception as e:
            logger.warning(f"Could not add logo: {e}")

    # Save image
    img.save(output_path)

    # Get file size
    file_size = os.path.getsize(output_path)

    logger.info(f"Generated QR code: {output_path} ({size}x{size})")

    return {
        'ok': True,
        'output_path': output_path,
        'file_size': file_size,
        'dimensions': {
            'width': size,
            'height': size
        },
        'data_length': len(data),
        'message': f'Generated QR code with {len(data)} characters of data'
    }
