# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Image Watermark Module
Add text or image watermark to images.
"""
import asyncio
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError


logger = logging.getLogger(__name__)


def _validate_watermark_params(input_path, output_path, text, watermark_image_path):
    if not input_path:
        raise ValidationError("Missing required parameter: input_path", field="input_path")
    if not output_path:
        raise ValidationError("Missing required parameter: output_path", field="output_path")
    if not text and not watermark_image_path:
        raise ValidationError("Either 'text' or 'watermark_image' must be provided")
    if not os.path.exists(input_path):
        raise ModuleError(f"Input file not found: {input_path}")


def _calculate_position(base_size, overlay_size, pos_name):
    base_w, base_h = base_size
    overlay_w, overlay_h = overlay_size
    margin = 10
    positions = {
        'center': ((base_w - overlay_w) // 2, (base_h - overlay_h) // 2),
        'top-left': (margin, margin),
        'top-right': (base_w - overlay_w - margin, margin),
        'bottom-left': (margin, base_h - overlay_h - margin),
        'bottom-right': (base_w - overlay_w - margin, base_h - overlay_h - margin),
    }
    return positions.get(pos_name, positions['bottom-right'])


def _apply_image_watermark(base_img, watermark_image_path, position, opacity):
    from PIL import Image
    with Image.open(watermark_image_path) as wm_img:
        if wm_img.mode != 'RGBA':
            wm_img = wm_img.convert('RGBA')
        alpha = wm_img.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        wm_img.putalpha(alpha)
        x, y = _calculate_position(base_img.size, wm_img.size, position)
        layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
        layer.paste(wm_img, (x, y))
        return Image.alpha_composite(base_img, layer)


def _save_watermark_result(result, output_path):
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    ext = os.path.splitext(output_path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        result = result.convert('RGB')
    result.save(output_path)


def _apply_text_watermark(base_img, text, position, opacity, font_size):
    from PIL import Image, ImageDraw, ImageFont
    txt_layer = Image.new('RGBA', base_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    try:
        font = ImageFont.truetype("arial.ttf", int(font_size))
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(font_size))
        except (OSError, IOError):
            font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x, y = _calculate_position(base_img.size, (text_w, text_h), position)
    alpha_value = int(255 * opacity)
    draw.text((x, y), text, fill=(255, 255, 255, alpha_value), font=font)
    return Image.alpha_composite(base_img, txt_layer)


@register_module(
    module_id='image.watermark',
    version='1.0.0',
    category='image',
    subcategory='transform',
    tags=['image', 'watermark', 'overlay', 'text', 'protect', 'path_restricted'],
    label='Add Watermark',
    label_key='modules.image.watermark.label',
    description='Add text or image watermark to images',
    description_key='modules.image.watermark.description',
    icon='Droplet',
    color='#8B5CF6',
    input_types=['file'],
    output_types=['file'],

    can_receive_from=['file.*', 'image.*', 'browser.*', 'http.*', 'flow.*', 'start'],
    can_connect_to=['file.*', 'image.*', 'flow.*'],

    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    timeout_ms=60000,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'input_path',
            type='string',
            format='path',
            label='Input Path',
            label_key='modules.image.watermark.params.input_path.label',
            description='Path to the source image',
            description_key='modules.image.watermark.params.input_path.description',
            required=True,
            placeholder='/path/to/image.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'output_path',
            type='string',
            format='path',
            label='Output Path',
            label_key='modules.image.watermark.params.output_path.label',
            description='Path to save the watermarked image',
            description_key='modules.image.watermark.params.output_path.description',
            required=True,
            placeholder='/path/to/watermarked.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'text',
            type='string',
            label='Watermark Text',
            label_key='modules.image.watermark.params.text.label',
            description='Text to use as watermark (optional if watermark_image is set)',
            description_key='modules.image.watermark.params.text.description',
            required=False,
            placeholder='© 2026 Company',
            group=FieldGroup.BASIC,
        ),
        field(
            'watermark_image',
            type='string',
            format='path',
            label='Watermark Image',
            label_key='modules.image.watermark.params.watermark_image.label',
            description='Path to watermark image (optional if text is set)',
            description_key='modules.image.watermark.params.watermark_image.description',
            required=False,
            placeholder='/path/to/logo.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'position',
            type='select',
            label='Position',
            label_key='modules.image.watermark.params.position.label',
            description='Watermark position on the image',
            description_key='modules.image.watermark.params.position.description',
            default='bottom-right',
            options=[
                {'value': 'center', 'label': 'Center'},
                {'value': 'top-left', 'label': 'Top Left'},
                {'value': 'top-right', 'label': 'Top Right'},
                {'value': 'bottom-left', 'label': 'Bottom Left'},
                {'value': 'bottom-right', 'label': 'Bottom Right'},
            ],
            group=FieldGroup.OPTIONS,
        ),
        field(
            'opacity',
            type='number',
            label='Opacity',
            label_key='modules.image.watermark.params.opacity.label',
            description='Watermark opacity (0.0 = transparent, 1.0 = opaque)',
            description_key='modules.image.watermark.params.opacity.description',
            default=0.5,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'font_size',
            type='number',
            label='Font Size',
            label_key='modules.image.watermark.params.font_size.label',
            description='Font size for text watermark',
            description_key='modules.image.watermark.params.font_size.description',
            default=36,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the watermarked image',
            'description_key': 'modules.image.watermark.output.output_path.description',
        },
        'watermark_type': {
            'type': 'string',
            'description': 'Type of watermark applied (text or image)',
            'description_key': 'modules.image.watermark.output.watermark_type.description',
        },
    },
    examples=[
        {
            'title': 'Add text watermark',
            'title_key': 'modules.image.watermark.examples.text.title',
            'params': {
                'input_path': '/path/to/image.png',
                'output_path': '/path/to/watermarked.png',
                'text': '© 2026 Company',
                'position': 'bottom-right',
                'opacity': 0.5,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def image_watermark(context: Dict[str, Any]) -> Dict[str, Any]:
    """Add text or image watermark to an image."""
    try:
        from PIL import Image
    except ImportError:
        raise ModuleError("Pillow is required for image.watermark. Install with: pip install Pillow")

    params = context['params']
    input_path = params.get('input_path')
    output_path = params.get('output_path')
    text = params.get('text')
    watermark_image_path = params.get('watermark_image')
    position = params.get('position', 'bottom-right')
    opacity = params.get('opacity', 0.5)
    font_size = params.get('font_size', 36)

    _validate_watermark_params(input_path, output_path, text, watermark_image_path)
    opacity = max(0.0, min(1.0, float(opacity)))

    def _apply_watermark():
        with Image.open(input_path) as base_img:
            if base_img.mode != 'RGBA':
                base_img = base_img.convert('RGBA')

            if watermark_image_path and os.path.exists(watermark_image_path):
                watermark_type = 'image'
                result = _apply_image_watermark(base_img, watermark_image_path, position, opacity)
            elif text:
                watermark_type = 'text'
                result = _apply_text_watermark(base_img, text, position, opacity, font_size)
            else:
                watermark_type = 'none'
                result = base_img

            _save_watermark_result(result, output_path)
            return {'output_path': output_path, 'watermark_type': watermark_type}

    result = await asyncio.to_thread(_apply_watermark)
    logger.info(f"Applied {result['watermark_type']} watermark to {input_path}")

    return {
        'ok': True,
        'data': result,
    }
