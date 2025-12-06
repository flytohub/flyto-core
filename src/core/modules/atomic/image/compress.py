"""
Image Compress Module
Compress images to reduce file size
"""
import asyncio
import logging
import os
from typing import Any, Dict

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='image.compress',
    version='1.0.0',
    category='image',
    subcategory='optimization',
    tags=['image', 'compress', 'optimize', 'quality'],
    label='Compress Image',
    label_key='modules.image.compress.label',
    description='Compress images to reduce file size while maintaining quality',
    description_key='modules.image.compress.description',
    icon='ImageIcon',
    color='#FF5722',

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
            'label_key': 'modules.image.compress.params.input_path.label',
            'description': 'Path to the source image file',
            'description_key': 'modules.image.compress.params.input_path.description',
            'required': True
        },
        'output_path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'modules.image.compress.params.output_path.label',
            'description': 'Path for compressed image (optional)',
            'description_key': 'modules.image.compress.params.output_path.description',
            'required': False
        },
        'quality': {
            'type': 'number',
            'label': 'Quality',
            'label_key': 'modules.image.compress.params.quality.label',
            'description': 'Compression quality (1-100, higher is better)',
            'description_key': 'modules.image.compress.params.quality.description',
            'required': False,
            'default': 85,
            'minimum': 1,
            'maximum': 100
        },
        'optimize': {
            'type': 'boolean',
            'label': 'Optimize',
            'label_key': 'modules.image.compress.params.optimize.label',
            'description': 'Apply additional optimization',
            'description_key': 'modules.image.compress.params.optimize.description',
            'required': False,
            'default': True
        },
        'max_size_kb': {
            'type': 'number',
            'label': 'Max Size (KB)',
            'label_key': 'modules.image.compress.params.max_size_kb.label',
            'description': 'Target maximum file size in KB (will auto-adjust quality)',
            'description_key': 'modules.image.compress.params.max_size_kb.description',
            'required': False
        },
        'format': {
            'type': 'string',
            'label': 'Output Format',
            'label_key': 'modules.image.compress.params.format.label',
            'description': 'Output format (defaults to input format)',
            'description_key': 'modules.image.compress.params.format.description',
            'required': False,
            'enum': ['jpeg', 'png', 'webp']
        }
    },
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the compressed image'
        },
        'original_size_bytes': {
            'type': 'number',
            'description': 'Original file size in bytes'
        },
        'compressed_size_bytes': {
            'type': 'number',
            'description': 'Compressed file size in bytes'
        },
        'compression_ratio': {
            'type': 'number',
            'description': 'Compression ratio (original/compressed)'
        }
    },
    examples=[
        {
            'title': 'Compress with quality setting',
            'title_key': 'modules.image.compress.examples.quality.title',
            'params': {
                'input_path': '/path/to/image.jpg',
                'quality': 75
            }
        },
        {
            'title': 'Compress to target size',
            'title_key': 'modules.image.compress.examples.target_size.title',
            'params': {
                'input_path': '/path/to/image.png',
                'max_size_kb': 500
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def image_compress(context: Dict[str, Any]) -> Dict[str, Any]:
    """Compress image to reduce file size"""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow is required for image.compress. Install with: pip install Pillow")

    params = context['params']
    input_path = params['input_path']
    output_path = params.get('output_path')
    quality = params.get('quality', 85)
    optimize = params.get('optimize', True)
    max_size_kb = params.get('max_size_kb')
    output_format = params.get('format')

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    original_size = os.path.getsize(input_path)

    def _compress():
        with Image.open(input_path) as img:
            if img.mode in ('RGBA', 'P') and output_format == 'jpeg':
                img = img.convert('RGB')

            nonlocal output_path
            if not output_path:
                base, ext = os.path.splitext(input_path)
                if output_format:
                    ext = f'.{output_format}'
                output_path = f"{base}_compressed{ext}"

            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

            save_kwargs = {'optimize': optimize}

            ext = os.path.splitext(output_path)[1].lower()
            if ext in ('.jpg', '.jpeg') or output_format == 'jpeg':
                save_kwargs['quality'] = quality
                save_kwargs['progressive'] = True
            elif ext == '.webp' or output_format == 'webp':
                save_kwargs['quality'] = quality
            elif ext == '.png' or output_format == 'png':
                save_kwargs['compress_level'] = min(9, max(0, int((100 - quality) / 10)))

            if max_size_kb:
                current_quality = quality
                target_bytes = max_size_kb * 1024

                for _ in range(10):
                    if ext in ('.jpg', '.jpeg', '.webp') or output_format in ('jpeg', 'webp'):
                        save_kwargs['quality'] = current_quality

                    img.save(output_path, **save_kwargs)
                    current_size = os.path.getsize(output_path)

                    if current_size <= target_bytes or current_quality <= 10:
                        break

                    current_quality = int(current_quality * (target_bytes / current_size) * 0.95)
                    current_quality = max(10, min(100, current_quality))
            else:
                img.save(output_path, **save_kwargs)

        return output_path

    output_path = await asyncio.to_thread(_compress)
    compressed_size = os.path.getsize(output_path)

    compression_ratio = original_size / compressed_size if compressed_size > 0 else 0
    savings_percent = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

    logger.info(
        f"Compressed image: {original_size} -> {compressed_size} bytes "
        f"({savings_percent:.1f}% reduction)"
    )

    return {
        'ok': True,
        'output_path': output_path,
        'original_size_bytes': original_size,
        'compressed_size_bytes': compressed_size,
        'compression_ratio': round(compression_ratio, 2),
        'savings_percent': round(savings_percent, 1)
    }
