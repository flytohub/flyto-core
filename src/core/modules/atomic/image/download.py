"""
Image Download Module
Download images from URL to local file
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import aiohttp

from ...registry import register_module


logger = logging.getLogger(__name__)


@register_module(
    module_id='image.download',
    version='1.0.0',
    category='image',
    subcategory='download',
    tags=['image', 'download', 'http', 'media'],
    label='Download Image',
    label_key='modules.image.download.label',
    description='Download image from URL to local file',
    description_key='modules.image.download.description',
    icon='Download',
    color='#10B981',

    # Connection types
    input_types=['url'],
    output_types=['file_path', 'binary'],
    can_connect_to=['image.*', 'file.*'],

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['network.http', 'file.write'],

    params_schema={
        'url': {
            'type': 'string',
            'label': 'Image URL',
            'label_key': 'modules.image.download.params.url.label',
            'description': 'URL of the image to download',
            'description_key': 'modules.image.download.params.url.description',
            'required': True,
            'placeholder': 'https://example.com/image.jpg'
        },
        'output_path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'modules.image.download.params.output_path.label',
            'description': 'Local path to save the image (optional, auto-generated if not provided)',
            'description_key': 'modules.image.download.params.output_path.description',
            'required': False,
            'placeholder': '/tmp/downloaded_image.jpg'
        },
        'output_dir': {
            'type': 'string',
            'label': 'Output Directory',
            'label_key': 'modules.image.download.params.output_dir.label',
            'description': 'Directory to save the image (used if output_path not provided)',
            'description_key': 'modules.image.download.params.output_dir.description',
            'required': False,
            'default': '/tmp'
        },
        'headers': {
            'type': 'object',
            'label': 'HTTP Headers',
            'label_key': 'modules.image.download.params.headers.label',
            'description': 'Custom HTTP headers for the request',
            'description_key': 'modules.image.download.params.headers.description',
            'required': False,
            'default': {}
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout',
            'label_key': 'modules.image.download.params.timeout.label',
            'description': 'Request timeout in seconds',
            'description_key': 'modules.image.download.params.timeout.description',
            'required': False,
            'default': 30
        }
    },
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Local file path of downloaded image'
        },
        'size': {
            'type': 'number',
            'description': 'File size in bytes'
        },
        'content_type': {
            'type': 'string',
            'description': 'Content type of the image'
        },
        'filename': {
            'type': 'string',
            'description': 'Filename of the downloaded image'
        }
    },
    examples=[
        {
            'title': 'Download image from URL',
            'title_key': 'modules.image.download.examples.basic.title',
            'params': {
                'url': 'https://example.com/photo.jpg',
                'output_dir': '/tmp/images'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def image_download(context: Dict[str, Any]) -> Dict[str, Any]:
    """Download image from URL"""
    params = context['params']
    url = params['url']
    output_path = params.get('output_path')
    output_dir = params.get('output_dir', '/tmp')
    headers = params.get('headers', {})
    timeout = params.get('timeout', 30)

    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    # Set default headers
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    default_headers.update(headers)

    # Determine output path
    if not output_path:
        # Extract filename from URL
        url_path = parsed.path
        filename = os.path.basename(url_path) or 'downloaded_image'
        if '.' not in filename:
            filename += '.jpg'  # Default extension
        output_path = os.path.join(output_dir, filename)

    # Ensure output directory exists
    Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)

    # Download image
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            headers=default_headers,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', 'image/jpeg')

            # Read content
            content = await response.read()

            # Write to file
            with open(output_path, 'wb') as f:
                f.write(content)

    file_size = os.path.getsize(output_path)
    filename = os.path.basename(output_path)

    logger.info(f"Downloaded image: {url} -> {output_path} ({file_size} bytes)")

    return {
        'ok': True,
        'path': output_path,
        'size': file_size,
        'content_type': content_type,
        'filename': filename
    }
