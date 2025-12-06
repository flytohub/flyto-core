"""
Image Resize Module
Resize images to specified dimensions
"""
import asyncio
import logging
import os
from typing import Any, Dict, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='image.resize',
    version='1.0.0',
    category='image',
    subcategory='transform',
    tags=['image', 'resize', 'scale', 'transform'],
    label='Resize Image',
    label_key='modules.image.resize.label',
    description='Resize images to specified dimensions with various algorithms',
    description_key='modules.image.resize.description',
    icon='ImageIcon',
    color='#9C27B0',

    input_types=['file', 'bytes'],
    output_types=['file', 'bytes'],
    can_connect_to=['file.*', 'image.*'],

    timeout=60,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read', 'file.write'],

    params_schema={
        'input_path': {
            'type': 'string',
            'label': 'Input Path',
            'label_key': 'modules.image.resize.params.input_path.label',
            'description': 'Path to the source image file',
            'description_key': 'modules.image.resize.params.input_path.description',
            'required': True
        },
        'output_path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'modules.image.resize.params.output_path.label',
            'description': 'Path for the resized image (optional, defaults to input with _resized suffix)',
            'description_key': 'modules.image.resize.params.output_path.description',
            'required': False
        },
        'width': {
            'type': 'number',
            'label': 'Width',
            'label_key': 'modules.image.resize.params.width.label',
            'description': 'Target width in pixels (use 0 to maintain aspect ratio)',
            'description_key': 'modules.image.resize.params.width.description',
            'required': False
        },
        'height': {
            'type': 'number',
            'label': 'Height',
            'label_key': 'modules.image.resize.params.height.label',
            'description': 'Target height in pixels (use 0 to maintain aspect ratio)',
            'description_key': 'modules.image.resize.params.height.description',
            'required': False
        },
        'scale': {
            'type': 'number',
            'label': 'Scale Factor',
            'label_key': 'modules.image.resize.params.scale.label',
            'description': 'Scale factor (e.g., 0.5 for half size, 2.0 for double)',
            'description_key': 'modules.image.resize.params.scale.description',
            'required': False
        },
        'algorithm': {
            'type': 'string',
            'label': 'Algorithm',
            'label_key': 'modules.image.resize.params.algorithm.label',
            'description': 'Resampling algorithm',
            'description_key': 'modules.image.resize.params.algorithm.description',
            'required': False,
            'enum': ['lanczos', 'bilinear', 'bicubic', 'nearest'],
            'default': 'lanczos'
        },
        'maintain_aspect': {
            'type': 'boolean',
            'label': 'Maintain Aspect Ratio',
            'label_key': 'modules.image.resize.params.maintain_aspect.label',
            'description': 'Maintain original aspect ratio when resizing',
            'description_key': 'modules.image.resize.params.maintain_aspect.description',
            'required': False,
            'default': True
        }
    },
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the resized image'
        },
        'original_size': {
            'type': 'object',
            'description': 'Original image dimensions'
        },
        'new_size': {
            'type': 'object',
            'description': 'New image dimensions'
        }
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
    author='Flyto2 Team',
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

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not width and not height and not scale:
        raise ValueError("Must specify either width/height or scale factor")

    resampling_map = {
        'lanczos': Image.Resampling.LANCZOS,
        'bilinear': Image.Resampling.BILINEAR,
        'bicubic': Image.Resampling.BICUBIC,
        'nearest': Image.Resampling.NEAREST
    }
    resampling = resampling_map.get(algorithm, Image.Resampling.LANCZOS)

    def _resize():
        with Image.open(input_path) as img:
            original_size = img.size
            original_width, original_height = original_size

            if scale:
                new_width = int(original_width * scale)
                new_height = int(original_height * scale)
            elif maintain_aspect:
                if width and height:
                    ratio = min(width / original_width, height / original_height)
                    new_width = int(original_width * ratio)
                    new_height = int(original_height * ratio)
                elif width:
                    ratio = width / original_width
                    new_width = width
                    new_height = int(original_height * ratio)
                else:
                    ratio = height / original_height
                    new_width = int(original_width * ratio)
                    new_height = height
            else:
                new_width = width or original_width
                new_height = height or original_height

            resized = img.resize((new_width, new_height), resampling)

            nonlocal output_path
            if not output_path:
                base, ext = os.path.splitext(input_path)
                output_path = f"{base}_resized{ext}"

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
