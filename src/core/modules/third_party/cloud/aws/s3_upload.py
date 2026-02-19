# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
AWS S3 Upload Module
Upload a local file to an Amazon S3 bucket using boto3.
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
    module_id='aws.s3.upload',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'upload', 'file', 'path_restricted'],
    label='S3 Upload',
    label_key='modules.aws.s3.upload.label',
    description='Upload a local file to an AWS S3 bucket',
    description_key='modules.aws.s3.upload.description',
    icon='Cloud',
    color='#FF9900',
    input_types=['file', 'string'],
    output_types=['object'],
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
              placeholder='uploads/file.txt'),
        field('file_path', type='string', label='File Path', required=True,
              group=FieldGroup.BASIC, description='Local file path to upload',
              placeholder='/path/to/file.txt', format='path'),
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
        field('content_type', type='string', label='Content Type',
              group=FieldGroup.OPTIONS,
              description='MIME type of the file (auto-detected if not set)',
              placeholder='application/octet-stream'),
    ),
    output_schema={
        'bucket': {'type': 'string', 'description': 'S3 bucket name', 'description_key': 'modules.aws.s3.upload.output.bucket.description'},
        'key': {'type': 'string', 'description': 'S3 object key', 'description_key': 'modules.aws.s3.upload.output.key.description'},
        'url': {'type': 'string', 'description': 'Public URL of the uploaded object', 'description_key': 'modules.aws.s3.upload.output.url.description'},
        'size': {'type': 'number', 'description': 'File size in bytes', 'description_key': 'modules.aws.s3.upload.output.size.description'},
    },
    examples=[
        {
            'title': 'Upload a local file',
            'params': {
                'bucket': 'my-bucket',
                'key': 'data/report.csv',
                'file_path': '/tmp/report.csv',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def aws_s3_upload(context: Dict[str, Any]) -> Dict[str, Any]:
    """Upload a local file to AWS S3."""
    params = context.get('params', {})

    bucket = params.get('bucket')
    key = params.get('key')
    file_path = params.get('file_path')

    if not bucket:
        raise ValidationError('Bucket name is required', field='bucket')
    if not key:
        raise ValidationError('Object key is required', field='key')
    if not file_path:
        raise ValidationError('File path is required', field='file_path')

    if not os.path.isfile(file_path):
        raise ModuleError(f'File not found: {file_path}')

    region = params.get('region') or os.getenv('AWS_REGION', 'us-east-1')
    access_key_id = params.get('access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
    secret_access_key = params.get('secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')

    if not access_key_id or not secret_access_key:
        raise ModuleError(
            'AWS credentials required. Provide access_key_id/secret_access_key '
            'params or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY env vars.'
        )

    content_type = params.get('content_type')
    file_size = os.path.getsize(file_path)

    try:
        import boto3
        from botocore.exceptions import ClientError, BotoCoreError
    except ImportError:
        raise ModuleError(
            'boto3 package is required. Install with: pip install boto3'
        )

    def _upload():
        client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        client.upload_file(file_path, bucket, key, ExtraArgs=extra_args or None)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _upload)
    except Exception as exc:
        error_name = type(exc).__name__
        raise ModuleError(f'S3 upload failed ({error_name}): {exc}')

    url = f'https://{bucket}.s3.amazonaws.com/{key}'

    return {
        'ok': True,
        'data': {
            'bucket': bucket,
            'key': key,
            'url': url,
            'size': file_size,
        },
    }
