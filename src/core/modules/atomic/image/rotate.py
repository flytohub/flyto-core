"""
Image Rotate Module
Rotate image by specified angle.
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


@register_module(
    module_id='image.rotate',
    version='1.0.0',
    category='image',
    subcategory='transform',
    tags=['image', 'rotate', 'transform', 'angle', 'path_restricted'],
    label='Rotate Image',
    label_key='modules.image.rotate.label',
    description='Rotate image by specified angle',
    description_key='modules.image.rotate.description',
    icon='RotateCw',
    color='#F59E0B',
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
            label='Input Path',
            label_key='modules.image.rotate.params.input_path.label',
            description='Path to the source image',
            description_key='modules.image.rotate.params.input_path.description',
            required=True,
            placeholder='/path/to/image.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'output_path',
            type='string',
            label='Output Path',
            label_key='modules.image.rotate.params.output_path.label',
            description='Path to save the rotated image',
            description_key='modules.image.rotate.params.output_path.description',
            required=True,
            placeholder='/path/to/rotated.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'angle',
            type='number',
            label='Angle',
            label_key='modules.image.rotate.params.angle.label',
            description='Rotation angle in degrees (counter-clockwise)',
            description_key='modules.image.rotate.params.angle.description',
            required=True,
            placeholder='90',
            group=FieldGroup.BASIC,
        ),
        field(
            'expand',
            type='boolean',
            label='Expand Canvas',
            label_key='modules.image.rotate.params.expand.label',
            description='Expand output canvas to fit the entire rotated image',
            description_key='modules.image.rotate.params.expand.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'fill_color',
            type='string',
            label='Fill Color',
            label_key='modules.image.rotate.params.fill_color.label',
            description='Background fill color for empty areas (hex)',
            description_key='modules.image.rotate.params.fill_color.description',
            default='#000000',
            placeholder='#000000',
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the rotated image',
            'description_key': 'modules.image.rotate.output.output_path.description',
        },
        'width': {
            'type': 'integer',
            'description': 'Width of the rotated image',
            'description_key': 'modules.image.rotate.output.width.description',
        },
        'height': {
            'type': 'integer',
            'description': 'Height of the rotated image',
            'description_key': 'modules.image.rotate.output.height.description',
        },
        'angle': {
            'type': 'number',
            'description': 'Rotation angle applied',
            'description_key': 'modules.image.rotate.output.angle.description',
        },
    },
    examples=[
        {
            'title': 'Rotate 90 degrees',
            'title_key': 'modules.image.rotate.examples.rotate90.title',
            'params': {
                'input_path': '/path/to/image.png',
                'output_path': '/path/to/rotated.png',
                'angle': 90,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def image_rotate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Rotate image by specified angle."""
    try:
        from PIL import Image
    except ImportError:
        raise ModuleError("Pillow is required for image.rotate. Install with: pip install Pillow")

    params = context['params']
    input_path = params.get('input_path')
    output_path = params.get('output_path')
    angle = params.get('angle')
    expand = params.get('expand', True)
    fill_color = params.get('fill_color', '#000000')

    if not input_path:
        raise ValidationError("Missing required parameter: input_path", field="input_path")
    if not output_path:
        raise ValidationError("Missing required parameter: output_path", field="output_path")
    if angle is None:
        raise ValidationError("Missing required parameter: angle", field="angle")

    if not os.path.exists(input_path):
        raise ModuleError(f"Input file not found: {input_path}")

    def _hex_to_rgb(hex_color: str) -> tuple:
        """Convert hex color string to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join(c * 2 for c in hex_color)
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _rotate():
        with Image.open(input_path) as img:
            fill_rgb = _hex_to_rgb(fill_color)

            # Handle RGBA images
            if img.mode == 'RGBA':
                fill_value = fill_rgb + (255,)
            else:
                fill_value = fill_rgb

            rotated = img.rotate(
                angle,
                expand=expand,
                fillcolor=fill_value,
                resample=Image.Resampling.BICUBIC,
            )

            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            rotated.save(output_path)

            return {
                'output_path': output_path,
                'width': rotated.width,
                'height': rotated.height,
                'angle': float(angle),
            }

    result = await asyncio.to_thread(_rotate)
    logger.info(f"Rotated image by {angle} degrees -> {result['width']}x{result['height']}")

    return {
        'ok': True,
        'data': result,
    }
