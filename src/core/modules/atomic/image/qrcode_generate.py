# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
QR Code Generator Module
Generate QR codes from text, URLs, or data
"""
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, patch, presets


logger = logging.getLogger(__name__)


def _clean_param(val, default):
    if not val or (isinstance(val, str) and val.startswith('${')):
        return default
    return val


def _parse_qr_params(params):
    data = params['data']
    output_path = _clean_param(params.get('output_path'), '/tmp/qrcode.png')
    size = _clean_param(params.get('size'), 300)
    color = _clean_param(params.get('color'), '#000000')
    background = _clean_param(params.get('background'), '#FFFFFF')
    error_correction = _clean_param(params.get('error_correction'), 'M')
    logo_path = params.get('logo_path')
    border = params.get('border')
    border = int(border) if border is not None and border != '' else 4
    version_param = params.get('version')
    try:
        version = int(version_param) if version_param else None
        if version is not None and version < 1:
            version = None
    except (ValueError, TypeError):
        version = None
    output_format = _clean_param(params.get('format'), 'png')
    return {
        'data': data, 'output_path': output_path, 'size': size,
        'color': color, 'background': background,
        'error_correction': error_correction, 'logo_path': logo_path,
        'border': border, 'version': version, 'output_format': output_format,
    }


def _create_qr_code(qrcode, p, ec_map, border):
    from qrcode.constants import ERROR_CORRECT_M
    ec_level = ec_map.get(p['error_correction'], ERROR_CORRECT_M)
    output_path = p['output_path']
    if p['output_format'] == 'svg' and output_path.endswith('.png'):
        output_path = output_path[:-4] + '.svg'
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    qr = qrcode.QRCode(
        version=p['version'], error_correction=ec_level,
        box_size=10, border=border,
    )
    qr.add_data(p['data'])
    qr.make(fit=True)
    return output_path, qr


def _generate_svg_qr(qr, output_path, color, background, border):
    import base64
    from io import BytesIO
    import qrcode.image.svg

    img = qr.make_image(
        image_factory=qrcode.image.svg.SvgImage,
        fill_color=color,
        back_color=background,
    )
    img.save(output_path)
    file_size = os.path.getsize(output_path)

    buf = BytesIO()
    img.save(buf)
    svg_data = buf.getvalue()
    base64_image = base64.b64encode(svg_data).decode('utf-8')
    data_uri = f'data:image/svg+xml;base64,{base64_image}'

    modules_count = qr.modules_count
    svg_size = (modules_count + border * 2) * 10
    dimensions = {'width': svg_size, 'height': svg_size}
    return file_size, base64_image, data_uri, dimensions


def _generate_png_qr(qr, output_path, color, background, size, logo_path):
    import base64
    from io import BytesIO
    from PIL import Image

    img = qr.make_image(fill_color=color, back_color=background)
    img = img.resize((size, size), Image.Resampling.LANCZOS)

    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path)
            logo_size = int(size * 0.25)
            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            logo_pos = ((size - logo_size) // 2, (size - logo_size) // 2)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            if logo.mode == 'RGBA':
                img.paste(logo, logo_pos, logo)
            else:
                img.paste(logo, logo_pos)
        except Exception as e:
            logger.warning(f"Could not add logo: {e}")

    img.save(output_path)
    file_size = os.path.getsize(output_path)

    buf = BytesIO()
    img.save(buf, format='PNG')
    base64_image = base64.b64encode(buf.getvalue()).decode('utf-8')
    data_uri = f'data:image/png;base64,{base64_image}'
    dimensions = {'width': size, 'height': size}
    return file_size, base64_image, data_uri, dimensions


@register_module(
    module_id='image.qrcode_generate',
    version='1.1.0',
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
    can_receive_from=['file.*', 'browser.*', 'http.*', 'flow.*', 'start'],

    # Execution settings
    timeout_ms=60000,
    retryable=True,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        # --- Basic ---
        presets.QRCODE_DATA(),
        presets.IMAGE_OUTPUT_PATH(key='output_path', placeholder='/tmp/qrcode.png'),
        presets.QRCODE_FORMAT(),         # early: controls conditional visibility below
        # --- Appearance ---
        presets.QRCODE_SIZE(),           # slider 100-2000  (hidden when SVG)
        presets.QRCODE_COLOR(),          # color picker
        presets.QRCODE_BACKGROUND(),     # color picker
        presets.QRCODE_ERROR_CORRECTION(),  # select dropdown
        presets.QRCODE_BORDER(),         # slider 0-20
        # --- Advanced ---
        presets.QRCODE_VERSION(),        # number input (empty = auto)
        presets.QRCODE_LOGO_PATH(),      # path selector (hidden when SVG)
        # --- Conditional visibility: SVG doesn't support resize or logo ---
        patch("size", displayOptions={"hide": {"format": ["svg"]}}),
        patch("logo_path", displayOptions={"hide": {"format": ["svg"]}}),
        on_conflict="merge",
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the generated QR code image',
            'description_key': 'modules.image.qrcode_generate.output.output_path.description',
        },
        'file_size': {
            'type': 'number',
            'description': 'Size of the output file in bytes',
            'description_key': 'modules.image.qrcode_generate.output.file_size.description',
        },
        'dimensions': {
            'type': 'object',
            'description': 'Image dimensions {width, height}',
            'description_key': 'modules.image.qrcode_generate.output.dimensions.description',
        },
    },
    examples=[
        {
            'title': 'Generate URL QR code',
            'title_key': 'modules.image.qrcode_generate.examples.url.title',
            'params': {
                'data': 'https://flyto.dev',
                'output_path': '/tmp/flyto_qr.png',
            },
        },
        {
            'title': 'Custom styled QR code',
            'title_key': 'modules.image.qrcode_generate.examples.styled.title',
            'params': {
                'data': 'Hello World',
                'color': '#6366F1',
                'size': 500,
                'error_correction': 'H',
            },
        },
        {
            'title': 'SVG QR code',
            'title_key': 'modules.image.qrcode_generate.examples.svg.title',
            'params': {
                'data': 'https://flyto.dev',
                'format': 'svg',
                'border': 2,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def qrcode_generate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate QR code image"""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
    except ImportError:
        raise ImportError("qrcode is required. Install with: pip install qrcode[pil]")

    p = _parse_qr_params(context['params'])
    data = p['data']
    output_format = p['output_format']
    border = p['border']

    ec_map = {
        'L': ERROR_CORRECT_L, 'M': ERROR_CORRECT_M,
        'Q': ERROR_CORRECT_Q, 'H': ERROR_CORRECT_H,
    }
    output_path, qr = _create_qr_code(
        qrcode, p, ec_map, border,
    )

    if output_format == 'svg':
        file_size, base64_image, data_uri, dimensions = _generate_svg_qr(
            qr, output_path, p['color'], p['background'], border
        )
    else:
        file_size, base64_image, data_uri, dimensions = _generate_png_qr(
            qr, output_path, p['color'], p['background'], p['size'], p['logo_path']
        )

    logger.info(f"Generated QR code: {output_path} ({output_format})")

    return {
        'ok': True,
        '__display__': True,
        'type': 'image',
        'title': data[:50],
        'output_path': output_path,
        'file_size': file_size,
        'dimensions': dimensions,
        'data_length': len(data),
        'format': output_format,
        'base64': base64_image,
        'data_uri': data_uri,
        'message': f'Generated {output_format.upper()} QR code with {len(data)} characters of data',
    }
