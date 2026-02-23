# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Image Compress Module
Compress images to reduce file size
"""
import asyncio
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


def _build_compress_kwargs(ext: str, output_format, quality: int, optimize: bool) -> dict:
    save_kwargs = {'optimize': optimize}
    if ext in ('.jpg', '.jpeg') or output_format == 'jpeg':
        save_kwargs['quality'] = quality
        save_kwargs['progressive'] = True
    elif ext == '.webp' or output_format == 'webp':
        save_kwargs['quality'] = quality
    elif ext == '.png' or output_format == 'png':
        save_kwargs['compress_level'] = min(9, max(0, int((100 - quality) / 10)))
    return save_kwargs


def _build_compress_result(output_path, original_size, compressed_size):
    compression_ratio = original_size / compressed_size if compressed_size > 0 else 0
    savings_percent = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
    return {
        'ok': True,
        'output_path': output_path,
        'original_size_bytes': original_size,
        'compressed_size_bytes': compressed_size,
        'compression_ratio': round(compression_ratio, 2),
        'savings_percent': round(savings_percent, 1),
    }


def _resolve_compress_output(input_path, output_path, output_format):
    if not output_path:
        base, ext = os.path.splitext(input_path)
        if output_format:
            ext = f'.{output_format}'
        output_path = f"{base}_compressed{ext}"
    return output_path


def _compress_to_target_size(img, output_path, save_kwargs, ext, output_format, quality, max_size_kb):
    target_bytes = max_size_kb * 1024
    current_quality = quality

    for _ in range(10):
        if ext in ('.jpg', '.jpeg', '.webp') or output_format in ('jpeg', 'webp'):
            save_kwargs['quality'] = current_quality

        img.save(output_path, **save_kwargs)
        current_size = os.path.getsize(output_path)

        if current_size <= target_bytes or current_quality <= 10:
            break

        current_quality = int(current_quality * (target_bytes / current_size) * 0.95)
        current_quality = max(10, min(100, current_quality))


@register_module(
    module_id='image.compress',
    version='1.0.0',
    category='image',
    subcategory='optimization',
    tags=['image', 'compress', 'optimize', 'quality', 'path_restricted'],
    label='Compress Image',
    label_key='modules.image.compress.label',
    description='Compress images to reduce file size while maintaining quality',
    description_key='modules.image.compress.description',
    icon='Image',
    color='#FF5722',

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
        presets.IMAGE_QUALITY(),
        presets.IMAGE_OPTIMIZE(),
        presets.IMAGE_MAX_SIZE_KB(),
        presets.IMAGE_FORMAT(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the compressed image'
        ,
                'description_key': 'modules.image.compress.output.output_path.description'},
        'original_size_bytes': {
            'type': 'number',
            'description': 'Original file size in bytes'
        ,
                'description_key': 'modules.image.compress.output.original_size_bytes.description'},
        'compressed_size_bytes': {
            'type': 'number',
            'description': 'Compressed file size in bytes'
        ,
                'description_key': 'modules.image.compress.output.compressed_size_bytes.description'},
        'compression_ratio': {
            'type': 'number',
            'description': 'Compression ratio (original/compressed)'
        ,
                'description_key': 'modules.image.compress.output.compression_ratio.description'}
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
    author='Flyto Team',
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
    output_path = _resolve_compress_output(input_path, output_path, output_format)

    def _compress():
        with Image.open(input_path) as img:
            if img.mode in ('RGBA', 'P') and output_format == 'jpeg':
                img = img.convert('RGB')

            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            ext = os.path.splitext(output_path)[1].lower()
            save_kwargs = _build_compress_kwargs(ext, output_format, quality, optimize)

            if max_size_kb:
                _compress_to_target_size(
                    img, output_path, save_kwargs, ext, output_format, quality, max_size_kb
                )
            else:
                img.save(output_path, **save_kwargs)

    await asyncio.to_thread(_compress)
    compressed_size = os.path.getsize(output_path)

    result = _build_compress_result(output_path, original_size, compressed_size)
    logger.info(
        f"Compressed image: {original_size} -> {compressed_size} bytes "
        f"({result['savings_percent']}% reduction)"
    )
    return result
