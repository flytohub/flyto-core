# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
AWS S3 List Module
List objects in an Amazon S3 bucket using boto3.
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
    module_id='aws.s3.list',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'list', 'browse'],
    label='S3 List Objects',
    description='List objects in an AWS S3 bucket with optional prefix filter',
    icon='Cloud',
    color='#FF9900',
    input_types=['string'],
    output_types=['array', 'object'],
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
        field('prefix', type='string', label='Prefix',
              group=FieldGroup.BASIC,
              description='Filter objects by key prefix (e.g. "uploads/")',
              placeholder='uploads/'),
        field('max_keys', type='number', label='Max Keys',
              group=FieldGroup.OPTIONS, description='Maximum number of objects to return',
              default=100, min=1, max=1000),
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
        'objects': {
            'type': 'array',
            'description': 'List of S3 objects',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string', 'description': 'Object key'},
                    'size': {'type': 'number', 'description': 'Object size in bytes'},
                    'last_modified': {'type': 'string', 'description': 'Last modified timestamp (ISO 8601)'},
                },
            },
        },
        'count': {'type': 'number', 'description': 'Number of objects returned'},
        'truncated': {'type': 'boolean', 'description': 'Whether the results are truncated'},
    },
    examples=[
        {
            'title': 'List objects with prefix',
            'params': {
                'bucket': 'my-bucket',
                'prefix': 'uploads/',
                'max_keys': 50,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def aws_s3_list(context: Dict[str, Any]) -> Dict[str, Any]:
    """List objects in an S3 bucket."""
    params = context.get('params', {})

    bucket = params.get('bucket')
    if not bucket:
        raise ValidationError('Bucket name is required', field='bucket')

    prefix = params.get('prefix', '')
    max_keys = int(params.get('max_keys', 100))
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

    objects = []
    truncated = False

    def _list():
        nonlocal objects, truncated
        client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        kwargs = {
            'Bucket': bucket,
            'MaxKeys': max_keys,
        }
        if prefix:
            kwargs['Prefix'] = prefix

        response = client.list_objects_v2(**kwargs)
        truncated = response.get('IsTruncated', False)

        for obj in response.get('Contents', []):
            last_modified = obj.get('LastModified')
            objects.append({
                'key': obj['Key'],
                'size': obj.get('Size', 0),
                'last_modified': last_modified.isoformat() if last_modified else '',
            })

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _list)
    except Exception as exc:
        error_name = type(exc).__name__
        raise ModuleError(f'S3 list failed ({error_name}): {exc}')

    return {
        'ok': True,
        'data': {
            'objects': objects,
            'count': len(objects),
            'truncated': truncated,
        },
    }
