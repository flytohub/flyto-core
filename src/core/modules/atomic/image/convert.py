"""
Image Convert Module
Convert image between formats (PNG, JPEG, WEBP, etc.)
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ...registry import register_module


logger = logging.getLogger(__name__)


# Supported formats and their extensions
SUPPORTED_FORMATS = {
    'jpeg': ['.jpg', '.jpeg'],
    'png': ['.png'],
    'webp': ['.webp'],
    'gif': ['.gif'],
    'bmp': ['.bmp'],
    'tiff': ['.tiff', '.tif'],
    'ico': ['.ico'],
}

FORMAT_ALIASES = {
    'jpg': 'jpeg',
    'tif': 'tiff',
}


def get_format_from_extension(path: str) -> Optional[str]:
    """Get format name from file extension"""
    ext = os.path.splitext(path)[1].lower()
    for fmt, extensions in SUPPORTED_FORMATS.items():
        if ext in extensions:
            return fmt
    return None


@register_module(
    module_id='image.convert',
    version='1.0.0',
    category='image',
    subcategory='convert',
    tags=['image', 'convert', 'format', 'media'],
    label='Convert Image',
    label_key='modules.image.convert.label',
    description='Convert image to different format (PNG, JPEG, WEBP, etc.)',
    description_key='modules.image.convert.description',
    icon='Image',
    color='#8B5CF6',

    # Connection types
    input_types=['file_path', 'binary'],
    output_types=['file_path', 'binary'],
    can_connect_to=['image.*', 'file.*'],

    # Execution settings
    timeout=120,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.read', 'file.write'],

    params_schema={
        'input_path': {
            'type': 'string',
            'label': 'Input Path',
            'label_key': 'modules.image.convert.params.input_path.label',
            'description': 'Path to the source image',
            'description_key': 'modules.image.convert.params.input_path.description',
            'required': True,
            'placeholder': '/path/to/image.png'
        },
        'output_path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'modules.image.convert.params.output_path.label',
            'description': 'Path for the converted image (optional)',
            'description_key': 'modules.image.convert.params.output_path.description',
            'required': False
        },
        'format': {
            'type': 'string',
            'label': 'Output Format',
            'label_key': 'modules.image.convert.params.format.label',
            'description': 'Target format: jpeg, png, webp, gif, bmp, tiff',
            'description_key': 'modules.image.convert.params.format.description',
            'required': True,
            'enum': ['jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff'],
            'default': 'png'
        },
        'quality': {
            'type': 'number',
            'label': 'Quality',
            'label_key': 'modules.image.convert.params.quality.label',
            'description': 'Output quality (1-100, for JPEG/WEBP)',
            'description_key': 'modules.image.convert.params.quality.description',
            'required': False,
            'default': 85,
            'minimum': 1,
            'maximum': 100
        },
        'resize': {
            'type': 'object',
            'label': 'Resize',
            'label_key': 'modules.image.convert.params.resize.label',
            'description': 'Resize options: {width, height, keep_aspect}',
            'description_key': 'modules.image.convert.params.resize.description',
            'required': False
        }
    },
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Path to the converted image'
        },
        'size': {
            'type': 'number',
            'description': 'File size in bytes'
        },
        'format': {
            'type': 'string',
            'description': 'Output format'
        },
        'dimensions': {
            'type': 'object',
            'description': 'Image dimensions {width, height}'
        }
    },
    examples=[
        {
            'title': 'Convert PNG to JPEG',
            'title_key': 'modules.image.convert.examples.png_to_jpeg.title',
            'params': {
                'input_path': '/tmp/image.png',
                'format': 'jpeg',
                'quality': 90
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def image_convert(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert image to different format"""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow is required for image conversion. Install with: pip install Pillow")

    params = context['params']
    input_path = params['input_path']
    output_format = params['format'].lower()
    quality = params.get('quality', 85)
    resize = params.get('resize')
    output_path = params.get('output_path')

    # Normalize format
    if output_format in FORMAT_ALIASES:
        output_format = FORMAT_ALIASES[output_format]

    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {output_format}")

    # Validate input file
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Determine output path
    if not output_path:
        base_name = os.path.splitext(input_path)[0]
        extension = SUPPORTED_FORMATS[output_format][0]
        output_path = f"{base_name}{extension}"

    # Ensure output directory exists
    Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)

    # Open and convert image
    with Image.open(input_path) as img:
        # Handle resize
        if resize:
            width = resize.get('width')
            height = resize.get('height')
            keep_aspect = resize.get('keep_aspect', True)

            if width and height:
                if keep_aspect:
                    img.thumbnail((width, height), Image.Resampling.LANCZOS)
                else:
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
            elif width:
                ratio = width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((width, new_height), Image.Resampling.LANCZOS)
            elif height:
                ratio = height / img.height
                new_width = int(img.width * ratio)
                img = img.resize((new_width, height), Image.Resampling.LANCZOS)

        # Convert color mode if needed
        if output_format == 'jpeg' and img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Save with appropriate options
        save_kwargs = {}
        if output_format in ('jpeg', 'webp'):
            save_kwargs['quality'] = quality
        if output_format == 'png':
            save_kwargs['optimize'] = True

        img.save(output_path, format=output_format.upper(), **save_kwargs)

        dimensions = {'width': img.width, 'height': img.height}

    file_size = os.path.getsize(output_path)

    logger.info(f"Converted image: {input_path} -> {output_path} ({output_format})")

    return {
        'ok': True,
        'path': output_path,
        'size': file_size,
        'format': output_format,
        'dimensions': dimensions
    }
