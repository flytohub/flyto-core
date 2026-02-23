# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Image Resize Module
Resize images to specified dimensions
"""
import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


def _compute_new_dimensions(
    original_width: int, original_height: int,
    width: Optional[int], height: Optional[int],
    scale: Optional[float], maintain_aspect: bool,
) -> Tuple[int, int]:
    if scale:
        return int(original_width * scale), int(original_height * scale)
    if maintain_aspect:
        if width and height:
            ratio = min(width / original_width, height / original_height)
            return int(original_width * ratio), int(original_height * ratio)
        if width:
            ratio = width / original_width
            return width, int(original_height * ratio)
        ratio = height / original_height
        return int(original_width * ratio), height
    return width or original_width, height or original_height


def _validate_resize_params(input_path, width, height, scale):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not width and not height and not scale:
        raise ValueError("Must specify either width/height or scale factor")


def _get_resampling(Image, algorithm: str):
    resampling_map = {
        'lanczos': Image.Resampling.LANCZOS,
        'bilinear': Image.Resampling.BILINEAR,
        'bicubic': Image.Resampling.BICUBIC,
        'nearest': Image.Resampling.NEAREST,
    }
    return resampling_map.get(algorithm, Image.Resampling.LANCZOS)


@register_module(
    module_id='image.resize',
    version='1.0.0',
    category='image',
    subcategory='transform',
    tags=['image', 'resize', 'scale', 'transform', 'path_restricted'],
    label='Resize Image',
    label_key='modules.image.resize.label',
    description='Resize images to specified dimensions with various algorithms',
    description_key='modules.image.resize.description',
    icon='Image',
    color='#9C27B0',

    input_types=['file', 'bytes'],
    output_types=['file', 'bytes'],
    can_connect_to=['file.*', 'image.*'],
    can_receive_from=['file.*', 'browser.*', 'http.*', 'flow.*', 'start'],

    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        presets.IMAGE_INPUT_PATH(),
        presets.IMAGE_OUTPUT_PATH(),
        presets.IMAGE_WIDTH(),
        presets.IMAGE_HEIGHT(),
        presets.IMAGE_SCALE(),
        presets.IMAGE_RESIZE_ALGORITHM(),
        presets.IMAGE_MAINTAIN_ASPECT(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the resized image'
        ,
                'description_key': 'modules.image.resize.output.output_path.description'},
        'original_size': {
            'type': 'object',
            'description': 'Original image dimensions'
        ,
                'description_key': 'modules.image.resize.output.original_size.description'},
        'new_size': {
            'type': 'object',
            'description': 'New image dimensions'
        ,
                'description_key': 'modules.image.resize.output.new_size.description'}
    },
    examples=[
        {
            'title': 'Resize to specific dimensions',
            'title_key': 'modules.image.resize.examples.dimensions.title',
            'params': {
                'input_path': '/path/to/image.png',
                'width': 800,
                'height': 600
            }
        },
        {
            'title': 'Scale by factor',
            'title_key': 'modules.image.resize.examples.scale.title',
            'params': {
                'input_path': '/path/to/image.png',
                'scale': 0.5
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def image_resize(context: Dict[str, Any]) -> Dict[str, Any]:
    """Resize image to specified dimensions"""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow is required for image.resize. Install with: pip install Pillow")

    params = context['params']
    input_path = params['input_path']
    output_path = params.get('output_path')
    width = params.get('width')
    height = params.get('height')
    scale = params.get('scale')
    algorithm = params.get('algorithm', 'lanczos')
    maintain_aspect = params.get('maintain_aspect', True)

    _validate_resize_params(input_path, width, height, scale)
    resampling = _get_resampling(Image, algorithm)

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_resized{ext}"

    def _resize():
        with Image.open(input_path) as img:
            original_width, original_height = img.size
            new_width, new_height = _compute_new_dimensions(
                original_width, original_height,
                width, height, scale, maintain_aspect,
            )
            resized = img.resize((new_width, new_height), resampling)
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            resized.save(output_path)
            return {
                'original_size': {'width': original_width, 'height': original_height},
                'new_size': {'width': new_width, 'height': new_height}
            }

    result = await asyncio.to_thread(_resize)
    logger.info(f"Resized image from {result['original_size']} to {result['new_size']}")

    return {
        'ok': True,
        'output_path': output_path,
        'original_size': result['original_size'],
        'new_size': result['new_size']
    }
