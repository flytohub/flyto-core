# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AWS S3 Delete Module
Delete an object from an Amazon S3 bucket using boto3.
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
    module_id='aws.s3.delete',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'delete', 'remove'],
    label='S3 Delete Object',
    label_key='modules.aws.s3.delete.label',
    description='Delete an object from an AWS S3 bucket',
    description_key='modules.aws.s3.delete.description',
    icon='Cloud',
    color='#FF9900',
    input_types=['string'],
    output_types=['object'],
    can_receive_from=['*'],
    can_connect_to=['*'],
    retryable=True,
    max_retries=3,
    concurrent_safe=True,
    timeout_ms=30000,
    requires_credentials=True,
    credential_keys=['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
    handles_sensitive_data=False,
    required_permissions=['cloud.storage'],
    params_schema=compose(
        field('bucket', type='string', label='Bucket Name', required=True,
              group=FieldGroup.BASIC, description='S3 bucket name',
              placeholder='my-bucket'),
        field('key', type='string', label='Object Key', required=True,
              group=FieldGroup.BASIC, description='S3 object key to delete',
              placeholder='uploads/file.txt'),
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
        'bucket': {'type': 'string', 'description': 'S3 bucket name', 'description_key': 'modules.aws.s3.delete.output.bucket.description'},
        'key': {'type': 'string', 'description': 'Deleted object key', 'description_key': 'modules.aws.s3.delete.output.key.description'},
        'deleted': {'type': 'boolean', 'description': 'Whether the object was deleted successfully', 'description_key': 'modules.aws.s3.delete.output.deleted.description'},
    },
    examples=[
        {
            'title': 'Delete an object',
            'params': {
                'bucket': 'my-bucket',
                'key': 'uploads/old-file.txt',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def aws_s3_delete(context: Dict[str, Any]) -> Dict[str, Any]:
    """Delete an object from AWS S3."""
    params = context.get('params', {})

    bucket = params.get('bucket')
    key = params.get('key')

    if not bucket:
        raise ValidationError('Bucket name is required', field='bucket')
    if not key:
        raise ValidationError('Object key is required', field='key')

    client = _make_s3_client(params)
    await _delete_object(client, bucket, key)

    return {
        'ok': True,
        'data': {'bucket': bucket, 'key': key, 'deleted': True},
    }


def _make_s3_client(params: Dict[str, Any]):
    """Build an S3 client from params or environment."""
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
    except ImportError:
        raise ModuleError('boto3 package is required. Install with: pip install boto3')

    return boto3.client(
        's3',
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


async def _delete_object(client, bucket: str, key: str):
    """Run delete_object in executor."""
    def _run():
        client.delete_object(Bucket=bucket, Key=key)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _run)
    except Exception as exc:
        error_name = type(exc).__name__
        raise ModuleError(f'S3 delete failed ({error_name}): {exc}')
