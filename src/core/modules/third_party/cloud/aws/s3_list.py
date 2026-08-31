# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AWS S3 List Module
List objects in an Amazon S3 bucket using boto3.

HOW FAR THIS MODULE FOLLOWS REALITY: two rungs, decided per call.

  the response carried objects        OBSERVED
      Every entry in `objects` is a key, a size and a timestamp the service put
      in `Contents`. Nothing about them is inferred and nothing is a restatement
      of the caller's input: this is a measurement of what is in the bucket.
      A listing changes nothing, so what is observed here is state rather than
      an effect -- which is the reading `database.query` already gives a read.

  the response carried none           ACCEPTED
      `len(objects) == 0` is the empty-read case, and it reads identically
      whether the bucket is empty, the prefix matched nothing, or the caller
      pointed at the wrong bucket entirely. It is the same shape as
      `database.query`'s `row_count == 0` and it earns the same answer: the
      service answered, and the answer contains no observation of any object.

`truncated` is `IsTruncated` from the response -- the service's own statement
that it stopped early -- so it travels as evidence in the effect and never
lifts the rung.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

from .....engine.outcome import ClaimBy, Outcome, envelope
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
    label_key='modules.aws.s3.list.label',
    description='List objects in an AWS S3 bucket with optional prefix filter',
    description_key='modules.aws.s3.list.description',
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
            'description_key': 'modules.aws.s3.list.output.objects.description',
            'items': {
                'type': 'object',
                'properties': {
                    'key': {'type': 'string', 'description': 'Object key'},
                    'size': {'type': 'number', 'description': 'Object size in bytes'},
                    'last_modified': {'type': 'string', 'description': 'Last modified timestamp (ISO 8601)'},
                },
            },
        },
        'count': {'type': 'number', 'description': 'Number of objects returned', 'description_key': 'modules.aws.s3.list.output.count.description'},
        'truncated': {'type': 'boolean', 'description': 'Whether the results are truncated', 'description_key': 'modules.aws.s3.list.output.truncated.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this listing was followed into reality: observed when '
                'the service returned objects, accepted when it returned none '
                '-- an empty listing is the same answer for an empty bucket and '
                'for a prefix that matched nothing'
            ),
            'description_key': 'modules.aws.s3.list.output.outcome.description',
        },
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
    author='Flyto2 Team',
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
    client = _make_s3_client(params)

    objects, truncated = await _list_objects(client, bucket, prefix, max_keys)
    return {
        'ok': True,
        'data': {
            'objects': objects,
            'count': len(objects),
            'truncated': truncated,
            'outcome': _listing_outcome(bucket, prefix, objects, truncated),
        },
    }


def _listing_outcome(
    bucket: str, prefix: str, objects: List[Dict[str, Any]], truncated: bool
) -> Dict[str, Any]:
    """OBSERVED when the service returned objects, ACCEPTED when it returned none."""
    if not objects:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_objects_returned',
                'bucket': bucket,
                'prefix': prefix,
                'measured_by': None,
                'detail': (
                    'The service answered with an empty Contents. That is not an '
                    'observation of the bucket: it reads the same whether the '
                    'bucket is empty, the prefix matched nothing, or the caller '
                    'named the wrong bucket.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'objects_returned',
            'bucket': bucket,
            'prefix': prefix,
            'count': len(objects),
            'truncated': truncated,
            'measured_by': "len() over the Contents entries the service returned",
            'detail': (
                'Keys, sizes and timestamps the service reported for objects that '
                'exist. `truncated` is the service saying it stopped early, so the '
                'count is a floor on what matched, not a total.'
            ),
        }],
    )


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


async def _list_objects(client, bucket: str, prefix: str, max_keys: int):
    """Run list_objects_v2 in executor and return (objects, truncated)."""
    objects = []
    truncated = False

    def _run():
        nonlocal objects, truncated
        kwargs = {'Bucket': bucket, 'MaxKeys': max_keys}
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
        await loop.run_in_executor(None, _run)
    except Exception as exc:
        error_name = type(exc).__name__
        raise ModuleError(f'S3 list failed ({error_name}): {exc}')

    return objects, truncated
