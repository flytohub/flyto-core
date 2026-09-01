# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AWS S3 Upload Module
Upload a local file to an Amazon S3 bucket using boto3.

HOW FAR THIS MODULE FOLLOWS REALITY: accepted, and no further.

`boto3`'s `upload_file` returns `None`. It raises on a failed transfer and is
silent on a successful one, so the single fact this module has when it comes
back is "the SDK finished without raising" -- the peer took the bytes and said
so. That is exactly ACCEPTED: the other side acknowledged taking it.

What is NOT evidence, and is the reason this stops one rung below its twin
`aws.s3.download`:

  * `size` is `os.path.getsize(file_path)` read from the LOCAL source file
    before a byte left this host. It is the same number if the object never
    reached the bucket, if it landed truncated, or if it landed at a different
    key entirely. Under the test this contract exists for -- would this value be
    unchanged had the effect not happened? -- it is unchanged, so nothing may
    rest on it. It travels as `bytes_offered`, named for what it is.

  * `url` is an f-string built from two caller parameters. It is not a link the
    service returned and it is not proof anything is at the other end of it.

OBSERVED would need a read-back: a `head_object` against the same key after the
transfer, whose `ContentLength` could be compared with the bytes offered.
`cloud.aws_s3.upload` already makes that call and does earn OBSERVED from it;
this module makes no second request, and adding one here is a change to what an
upload costs, which belongs to whoever owns that decision rather than to a
contract declaration. Until then this says `accepted`, which is true.
"""

import asyncio
import logging
import os
from typing import Any, Dict

from .....utils import validate_path_with_env_config
from .....engine.outcome import ClaimBy, Outcome, envelope
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
        'size': {
            'type': 'number',
            'description': (
                'Size of the LOCAL source file, from os.path.getsize before the '
                'transfer. Not a measurement of the object in the bucket'
            ),
            'description_key': 'modules.aws.s3.upload.output.size.description',
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this upload was followed into reality. Always '
                '"accepted": boto3 returning without raising is the peer '
                'acknowledging the bytes, and nothing here reads the object back'
            ),
            'description_key': 'modules.aws.s3.upload.output.outcome.description',
        },
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
    author='Flyto2 Team',
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

    # SECURITY: the mirror image of GHSA-hmq9-xw4w-7ppc. That advisory closed
    # the cloud.*.download write path; this is the upload read path, where an
    # unvalidated file_path ships any host file to a caller-chosen bucket.
    file_path = validate_path_with_env_config(str(file_path))

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
            'outcome': envelope(
                Outcome.ACCEPTED,
                # NONE: no caller declared an expected outcome and this module
                # infers none, so there is no expectation that could have been
                # broken and no author to attribute one to.
                claim_by=ClaimBy.NONE,
                effects=[
                    {
                        'kind': 'object_bytes_offered',
                        'bucket': bucket,
                        'key': key,
                        'bytes_offered': file_size,
                        'measured_by': 'os.path.getsize(file_path), before the transfer',
                        'detail': (
                            'Size of the local source file. Says nothing about the '
                            'object in the bucket: it reads identically whether S3 '
                            'stored every byte, some of them, or none.'
                        ),
                    },
                    {
                        'kind': 'object_not_read_back',
                        'measured_by': None,
                        'detail': (
                            'boto3 upload_file returns None and this module issues no '
                            'head_object. The transfer was acknowledged by the service '
                            'and followed no further.'
                        ),
                    },
                ],
            ),
        },
    }
