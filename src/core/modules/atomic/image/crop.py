# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Image Crop Module
Crop image to specified region.
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
    module_id='image.crop',
    version='1.0.0',
    category='image',
    subcategory='transform',
    tags=['image', 'crop', 'trim', 'cut', 'transform', 'path_restricted'],
    label='Crop Image',
    label_key='modules.image.crop.label',
    description='Crop image to specified region',
    description_key='modules.image.crop.description',
    icon='Crop',
    color='#10B981',
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
            label_key='modules.image.crop.params.input_path.label',
            description='Path to the source image',
            description_key='modules.image.crop.params.input_path.description',
            required=True,
            placeholder='/path/to/image.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'output_path',
            type='string',
            label='Output Path',
            label_key='modules.image.crop.params.output_path.label',
            description='Path to save the cropped image',
            description_key='modules.image.crop.params.output_path.description',
            required=True,
            placeholder='/path/to/cropped.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'left',
            type='number',
            label='Left',
            label_key='modules.image.crop.params.left.label',
            description='Left coordinate of crop region (pixels)',
            description_key='modules.image.crop.params.left.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'top',
            type='number',
            label='Top',
            label_key='modules.image.crop.params.top.label',
            description='Top coordinate of crop region (pixels)',
            description_key='modules.image.crop.params.top.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'right',
            type='number',
            label='Right',
            label_key='modules.image.crop.params.right.label',
            description='Right coordinate of crop region (pixels)',
            description_key='modules.image.crop.params.right.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'bottom',
            type='number',
            label='Bottom',
            label_key='modules.image.crop.params.bottom.label',
            description='Bottom coordinate of crop region (pixels)',
            description_key='modules.image.crop.params.bottom.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the cropped image',
            'description_key': 'modules.image.crop.output.output_path.description',
        },
        'width': {
            'type': 'integer',
            'description': 'Width of the cropped image',
            'description_key': 'modules.image.crop.output.width.description',
        },
        'height': {
            'type': 'integer',
            'description': 'Height of the cropped image',
            'description_key': 'modules.image.crop.output.height.description',
        },
        'original_width': {
            'type': 'integer',
            'description': 'Original image width',
            'description_key': 'modules.image.crop.output.original_width.description',
        },
        'original_height': {
            'type': 'integer',
            'description': 'Original image height',
            'description_key': 'modules.image.crop.output.original_height.description',
        },
    },
    examples=[
        {
            'title': 'Crop center region',
            'title_key': 'modules.image.crop.examples.center.title',
            'params': {
                'input_path': '/path/to/image.png',
                'output_path': '/path/to/cropped.png',
                'left': 100,
                'top': 100,
                'right': 500,
                'bottom': 400,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def image_crop(context: Dict[str, Any]) -> Dict[str, Any]:
    """Crop image to specified region."""
    try:
        from PIL import Image
    except ImportError:
        raise ModuleError("Pillow is required for image.crop. Install with: pip install Pillow")

    params = context['params']
    input_path = params.get('input_path')
    output_path = params.get('output_path')
    left = params.get('left')
    top = params.get('top')
    right = params.get('right')
    bottom = params.get('bottom')

    if not input_path:
        raise ValidationError("Missing required parameter: input_path", field="input_path")
    if not output_path:
        raise ValidationError("Missing required parameter: output_path", field="output_path")
    if left is None or top is None or right is None or bottom is None:
        raise ValidationError("All crop coordinates (left, top, right, bottom) are required")

    if not os.path.exists(input_path):
        raise ModuleError(f"Input file not found: {input_path}")

    if left >= right:
        raise ValidationError("left must be less than right", field="left")
    if top >= bottom:
        raise ValidationError("top must be less than bottom", field="top")

    def _crop():
        with Image.open(input_path) as img:
            original_width, original_height = img.size

            # Clamp coordinates to image bounds
            crop_left = max(0, int(left))
            crop_top = max(0, int(top))
            crop_right = min(original_width, int(right))
            crop_bottom = min(original_height, int(bottom))

            cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))

            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            cropped.save(output_path)

            return {
                'output_path': output_path,
                'width': cropped.width,
                'height': cropped.height,
                'original_width': original_width,
                'original_height': original_height,
            }

    result = await asyncio.to_thread(_crop)
    logger.info(
        f"Cropped image from {result['original_width']}x{result['original_height']} "
        f"to {result['width']}x{result['height']}"
    )

    return {
        'ok': True,
        'data': result,
    }
