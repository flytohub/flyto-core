# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
from ...errors import ModuleError
from ....utils import (
    guarded_client_session,
    validate_url_with_env_config,
    SSRFError,
    validate_path_with_env_config,
    PathTraversalError,
)


logger = logging.getLogger(__name__)


def _validate_and_prepare_download(url: str, parsed, output_path, output_dir, headers):
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    default_headers.update(headers)

    if not output_path:
        url_path = parsed.path
        filename = os.path.basename(url_path) or 'downloaded_image'
        if '.' not in filename:
            filename += '.jpg'
        output_path = os.path.join(output_dir, filename)

    return output_path, default_headers


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
    can_receive_from=['file.*', 'browser.*', 'http.*', 'flow.*', 'start'],

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

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    try:
        validate_url_with_env_config(url)
    except SSRFError as e:
        logger.warning(f"SSRF protection blocked image download from: {url}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'SSRF_BLOCKED'
        }

    output_path, default_headers = _validate_and_prepare_download(
        url, parsed, output_path, output_dir, headers
    )

    # SECURITY: confine the write to FLYTO_SANDBOX_DIR. The previous check
    # validated output_path against the caller-supplied output_dir, so the
    # caller controlled both the target and its base and the check was a no-op
    # (GHSA-2956-977x-2w3r). Use the central sandbox guard instead.
    try:
        target_real = validate_path_with_env_config(output_path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    Path(os.path.dirname(target_real)).mkdir(parents=True, exist_ok=True)

    async with guarded_client_session() as session:
        async with session.get(
            url,
            headers=default_headers,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            content = await response.read()
            with open(target_real, 'wb') as f:
                f.write(content)

    file_size = os.path.getsize(target_real)
    filename = os.path.basename(target_real)
    logger.info(f"Downloaded image: {url} -> {target_real} ({file_size} bytes)")

    return {
        'ok': True,
        'path': target_real,
        'size': file_size,
        'content_type': content_type,
        'filename': filename
    }
