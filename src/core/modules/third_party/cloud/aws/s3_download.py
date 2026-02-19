# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
AWS S3 Download Module
Download a file from an Amazon S3 bucket to the local filesystem using boto3.
"""

import asyncio
import logging
import os
from typing import Any, Dict

from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup
from ....errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='aws.s3.download',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'download', 'file', 'path_restricted'],
    label='S3 Download',
    description='Download a file from an AWS S3 bucket to a local path',
    icon='Cloud',
    color='#FF9900',
    input_types=['string'],
    output_types=['file', 'binary'],
    can_receive_from=['*'],
    can_connect_to=['*'],
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    timeout_ms=60000,
    requires_credentials=True,
    credential_keys=['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
    handles_sensitive_data=True,
    required_permissions=['cloud.storage'],
    params_schema=compose(
        field('bucket', type='string', label='Bucket Name', required=True,
              group=FieldGroup.BASIC, description='S3 bucket name',
              placeholder='my-bucket'),
        field('key', type='string', label='Object Key', required=True,
              group=FieldGroup.BASIC, description='S3 object key (path in bucket)',
              placeholder='data/file.txt'),
        field('output_path', type='string', label='Output Path', required=True,
              group=FieldGroup.BASIC, description='Local file path to save the downloaded file',
              placeholder='/tmp/downloaded-file.txt', format='path'),
        field('region', type='string', label='Region',
              group=FieldGroup.CONNECTION, description='AWS region',
              default='us-east-1', placeholder='us-east-1'),
        field('access_key_id', type='string', label='Access Key ID',
              group=FieldGroup.CONNECTION,
              description='AWS access key ID (falls back to env AWS_ACCESS_KEY_ID)',
              placeholder='${env.AWS_ACCESS_KEY_ID}'),
        field('secret_access_key', type='string', label='Secret Access Key',
              group=FieldGroup.CONNECTION,
              description='AWS secret access key (falls back to env AWS_SECRET_ACCESS_KEY)',
              placeholder='${env.AWS_SECRET_ACCESS_KEY}', format='password'),
    ),
    output_schema={
        'path': {'type': 'string', 'description': 'Local file path where the file was saved'},
        'size': {'type': 'number', 'description': 'File size in bytes'},
        'content_type': {'type': 'string', 'description': 'MIME type of the downloaded file'},
    },
    examples=[
        {
            'title': 'Download a file from S3',
            'params': {
                'bucket': 'my-bucket',
                'key': 'data/report.csv',
                'output_path': '/tmp/report.csv',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def aws_s3_download(context: Dict[str, Any]) -> Dict[str, Any]:
    """Download a file from AWS S3."""
    params = context.get('params', {})

    bucket = params.get('bucket')
    key = params.get('key')
    output_path = params.get('output_path')

    if not bucket:
        raise ValidationError('Bucket name is required', field='bucket')
    if not key:
        raise ValidationError('Object key is required', field='key')
    if not output_path:
        raise ValidationError('Output path is required', field='output_path')

    region = params.get('region') or os.getenv('AWS_REGION', 'us-east-1')
    access_key_id = params.get('access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
    secret_access_key = params.get('secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')

    if not access_key_id or not secret_access_key:
        raise ModuleError(
            'AWS credentials required. Provide access_key_id/secret_access_key '
            'params or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY env vars.'
        )

    try:
        import boto3
        from botocore.exceptions import ClientError, BotoCoreError
    except ImportError:
        raise ModuleError(
            'boto3 package is required. Install with: pip install boto3'
        )

    content_type = ''
    file_size = 0

    def _download():
        nonlocal content_type, file_size
        client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        client.download_file(bucket, key, output_path)

        # Get object metadata
        head = client.head_object(Bucket=bucket, Key=key)
        content_type = head.get('ContentType', '')
        file_size = head.get('ContentLength', 0)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _download)
    except Exception as exc:
        error_name = type(exc).__name__
        raise ModuleError(f'S3 download failed ({error_name}): {exc}')

    return {
        'ok': True,
        'data': {
            'path': output_path,
            'size': file_size,
            'content_type': content_type,
        },
    }
