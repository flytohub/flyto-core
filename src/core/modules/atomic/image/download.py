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
from ...schema import compose, presets
from ....utils import validate_url_with_env_config, SSRFError


logger = logging.getLogger(__name__)


@register_module(
    module_id='image.download',
    version='1.0.0',
    category='image',
    subcategory='download',
    tags=['image', 'download', 'http', 'media', 'ssrf_protected', 'path_restricted'],
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
    can_receive_from=['file.*', 'browser.*', 'screenshot.*', 'api.*', 'flow.*', 'start'],

    # Execution settings
    timeout_ms=60000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        presets.IMAGE_URL(),
        presets.IMAGE_OUTPUT_PATH(placeholder='/tmp/downloaded_image.jpg'),
        presets.OUTPUT_DIRECTORY(),
        presets.HEADERS(),
        presets.TIMEOUT_S(default=30),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Local file path of downloaded image'
        ,
                'description_key': 'modules.image.download.output.path.description'},
        'size': {
            'type': 'number',
            'description': 'File size in bytes'
        ,
                'description_key': 'modules.image.download.output.size.description'},
        'content_type': {
            'type': 'string',
            'description': 'Content type of the image'
        ,
                'description_key': 'modules.image.download.output.content_type.description'},
        'filename': {
            'type': 'string',
            'description': 'Filename of the downloaded image'
        ,
                'description_key': 'modules.image.download.output.filename.description'}
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

    # SECURITY: Validate URL against SSRF attacks
    try:
        validate_url_with_env_config(url)
    except SSRFError as e:
        logger.warning(f"SSRF protection blocked image download from: {url}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSRF_BLOCKED'
        }

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
