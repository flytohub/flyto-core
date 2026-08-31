# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Cloud Storage Integration Modules
Provides integrations with cloud storage services like AWS S3

HOW FAR THESE TWO MODULES FOLLOW REALITY

Both make a second request, and that is what separates them from the boto3
twins in `aws/`: `cloud.aws_s3.upload` calls `head_object` after the PUT, and
`cloud.aws_s3.download` reads the bytes it was sent. A second look at the store
is the difference between taking the service's word and measuring what is
there, so both can reach OBSERVED where `aws.s3.upload` cannot.

What is compared, on every path: a length measured on OUR side against a length
the store reports for the same key.

    upload, file    os.path.getsize(file_path)  vs head ContentLength
    upload, content len(body)                   vs head ContentLength
    download, file  os.stat(dest).st_size       vs head ContentLength
    download, memory len(bytes actually read)   vs get_object ContentLength

  equal              OBSERVED, claim_by INFERRED -- the predicate is ours
  not equal          INDETERMINATE, not FAILED. Nobody declared a size
                     contract, and there are innocent readings: head_object is a
                     separate request, so an object replaced between the two
                     calls reports a length that was never ours.
  one side missing   ACCEPTED. The service took the bytes and answered; nothing
                     could be compared.

The residual gap in the upload case, stated plainly because a reader deserves
it: an object of exactly the same length already sitting at that key would be
indistinguishable from ours. The equality is evidence, not proof, which is why
the claim stops at OBSERVED -- "we saw the world change, not that the right
thing changed" -- and why `claim_by` records that the predicate was inferred
here rather than asked for by a caller.

`etag` stays what it always was: the store's own identifier for what it says it
holds. It is reported, and no rung rests on it.
"""

import os
from typing import Any, Dict, Optional

from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module


def _length_outcome(
    *,
    kind: str,
    local_bytes: Optional[int],
    local_by: str,
    store_bytes: Optional[int],
    store_by: str,
    detail: str,
) -> Dict[str, Any]:
    """The rung a length comparison earned, and the two numbers that earned it.

    One helper for four paths because the question is the same one each time:
    does what the store reports for this key agree with what this host measured?
    The paths differ only in where each number came from, so both provenances
    travel in the effects rather than being flattened into a bare integer.
    """
    local_effect = {
        'kind': f'{kind}_bytes_local',
        'bytes': local_bytes,
        # `measured_by` names the line that produced the number. Where there is
        # no number there was no such line, so it is None and the note about why
        # travels as `reason` -- a failure message sitting in `measured_by`
        # would read as a measurement to anything scanning for one.
        'measured_by': local_by if local_bytes is not None else None,
        'reason': None if local_bytes is not None else local_by,
        'detail': (
            'Measured on this host. On its own it says nothing about the store: '
            'it reads identically whether the transfer landed whole, short, or '
            'not at all.'
        ),
    }
    store_effect = {
        'kind': f'{kind}_bytes_in_store',
        'bytes': store_bytes,
        'measured_by': store_by,
        'detail': detail,
    }

    if local_bytes is None or store_bytes is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                local_effect,
                {
                    'kind': f'{kind}_not_compared',
                    'measured_by': None,
                    'detail': (
                        'One of the two lengths was not available, so no comparison '
                        'was made. The service acknowledged the request and it was '
                        'followed no further.'
                    ),
                },
            ],
        )

    if local_bytes == store_bytes:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[local_effect, store_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            local_effect,
            store_effect,
            {
                'kind': f'{kind}_length_disagrees',
                'predicate': 'bytes measured on this host == bytes the store reports',
                'local_bytes': local_bytes,
                'store_bytes': store_bytes,
                'detail': (
                    'The two lengths do not agree. That may be a partial transfer, '
                    'or it may be this inference being wrong -- the metadata read is '
                    'a separate request, and an object replaced between the two would '
                    'report a length that was never ours. We cannot say which, so '
                    'this is indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='cloud.aws_s3.upload',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'file.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'upload', 'file', 'path_restricted', 'ssrf_protected'],
    label='AWS S3 Upload',
    label_key='modules.cloud.aws_s3.upload.label',
    description='Upload a file or data to AWS S3 bucket',
    description_key='modules.cloud.aws_s3.upload.description',
    icon='Cloud',
    color='#FF9900',

    # Connection types
    input_types=['file', 'binary', 'string'],
    output_types=['object'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # Cloud uploads can take time depending on file size
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple uploads can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
    handles_sensitive_data=True,  # Files may contain sensitive data
    required_permissions=['cloud.storage'],

    params_schema={
        'aws_access_key_id': {
            'type': 'string',
            'label': 'AWS Access Key ID',
            'label_key': 'modules.cloud.aws_s3.upload.params.aws_access_key_id.label',
            'description': 'AWS access key ID (defaults to env.AWS_ACCESS_KEY_ID)',
            'description_key': 'modules.cloud.aws_s3.upload.params.aws_access_key_id.description',
            'placeholder': '${env.AWS_ACCESS_KEY_ID}',
            'required': False,
            'sensitive': True
        },
        'aws_secret_access_key': {
            'type': 'string',
            'label': 'AWS Secret Access Key',
            'label_key': 'modules.cloud.aws_s3.upload.params.aws_secret_access_key.label',
            'description': 'AWS secret access key (defaults to env.AWS_SECRET_ACCESS_KEY)',
            'description_key': 'modules.cloud.aws_s3.upload.params.aws_secret_access_key.description',
            'placeholder': '${env.AWS_SECRET_ACCESS_KEY}',
            'required': False,
            'sensitive': True
        },
        'region': {
            'type': 'string',
            'label': 'Region',
            'label_key': 'modules.cloud.aws_s3.upload.params.region.label',
            'description': 'AWS region (defaults to env.AWS_REGION or us-east-1)',
            'description_key': 'modules.cloud.aws_s3.upload.params.region.description',
            'placeholder': '${env.AWS_REGION}',
            'default': 'us-east-1',
            'required': False
        },
        'bucket': {
            'type': 'string',
            'label': 'Bucket Name',
            'label_key': 'modules.cloud.aws_s3.upload.params.bucket.label',
            'description': 'S3 bucket name',
            'description_key': 'modules.cloud.aws_s3.upload.params.bucket.description',
            'required': True,
            'placeholder': 'my-bucket'
        },
        'key': {
            'type': 'string',
            'label': 'Object Key',
            'label_key': 'modules.cloud.aws_s3.upload.params.key.label',
            'description': 'S3 object key (file path in bucket)',
            'description_key': 'modules.cloud.aws_s3.upload.params.key.description',
            'required': True,
            'placeholder': 'uploads/file.txt'
        },
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.cloud.aws_s3.upload.params.file_path.label',
            'description': 'Local file path to upload',
            'description_key': 'modules.cloud.aws_s3.upload.params.file_path.description',
            'required': False,
            'help': 'Either file_path or content must be provided'
        ,
            'placeholder': '/path/to/file',
},
        'content': {
            'type': 'string',
            'label': 'Content',
            'label_key': 'modules.cloud.aws_s3.upload.params.content.label',
            'description': 'File content to upload (as string or base64)',
            'description_key': 'modules.cloud.aws_s3.upload.params.content.description',
            'required': False,
            'multiline': True,
            'help': 'Either file_path or content must be provided'
        ,
            'placeholder': 'Enter content...',
},
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.cloud.aws_s3.upload.params.content_type.label',
            'description': 'MIME type of the file',
            'description_key': 'modules.cloud.aws_s3.upload.params.content_type.description',
            'required': False,
            'placeholder': 'text/plain',
            'help': 'Auto-detected if not provided'
        },
        'acl': {
            'type': 'string',
            'label': 'ACL',
            'label_key': 'modules.cloud.aws_s3.upload.params.acl.label',
            'description': 'Access control list for the object',
            'description_key': 'modules.cloud.aws_s3.upload.params.acl.description',
            'required': False,
            'default': 'private',
            'options': [
                {'value': 'private', 'label': 'Private'},
                {'value': 'public-read', 'label': 'Public Read'},
                {'value': 'public-read-write', 'label': 'Public Read/Write'}
            ]
        }
    },
    output_schema={
        'url': {
            'type': 'string',
            'description': 'S3 URL of uploaded object'
        ,
                'description_key': 'modules.cloud.aws_s3.upload.output.url.description'},
        'bucket': {
            'type': 'string',
            'description': 'Bucket name'
        ,
                'description_key': 'modules.cloud.aws_s3.upload.output.bucket.description'},
        'key': {
            'type': 'string',
            'description': 'Object key'
        ,
                'description_key': 'modules.cloud.aws_s3.upload.output.key.description'},
        'etag': {
            'type': 'string',
            'description': 'ETag of uploaded object'
        ,
                'description_key': 'modules.cloud.aws_s3.upload.output.etag.description'},
        'bytes_offered': {
            'type': 'number',
            'description': (
                'Bytes handed to the transfer, measured on this host: the source '
                'file size, or the length of the encoded content'
            ),
            'description_key': 'modules.cloud.aws_s3.upload.output.bytes_offered.description'},
        'bytes_in_store': {
            'type': 'number',
            'description': (
                'ContentLength the service reports for the object after the '
                'upload, from head_object. null when it reported none'
            ),
            'description_key': 'modules.cloud.aws_s3.upload.output.bytes_in_store.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this upload was followed into reality: observed when '
                'the object read back has the length offered, indeterminate '
                'when it does not, accepted when nothing could be compared'
            ),
            'description_key': 'modules.cloud.aws_s3.upload.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Upload text content',
            'title_key': 'modules.cloud.aws_s3.upload.examples.text.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'reports/daily-${timestamp}.txt',
                'content': '${report_text}',
                'content_type': 'text/plain'
            }
        },
        {
            'title': 'Upload local file',
            'title_key': 'modules.cloud.aws_s3.upload.examples.file.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'backups/database.sql',
                'file_path': '/tmp/backup.sql',
                'acl': 'private'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html'
)
async def aws_s3_upload(context):
    """Upload file to AWS S3"""
    params = context['params']

    # SECURITY: aws_s3_download confines its file_path; this side read whatever
    # host file the caller named and streamed it to a caller-chosen bucket with
    # caller-supplied credentials (GHSA-45hf-2fmj-q442).
    file_path = params.get('file_path')
    if file_path:
        file_path = validate_path_with_env_config(file_path)

    try:
        import aioboto3
    except ImportError:
        raise ImportError(
            "aioboto3 package required. Install with: pip install aioboto3"
        ) from None

    # Get AWS credentials
    aws_access_key_id = params.get('aws_access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = params.get('aws_secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')
    region = params.get('region') or os.getenv('AWS_REGION', 'us-east-1')

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValueError("AWS credentials required: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

    bucket = params['bucket']
    key = params['key']
    content = params.get('content')

    if not file_path and not content:
        raise ValueError("Either 'file_path' or 'content' must be provided")

    # Prepare upload
    session = aioboto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region
    )

    extra_args = {}
    if params.get('content_type'):
        extra_args['ContentType'] = params['content_type']
    if params.get('acl'):
        extra_args['ACL'] = params['acl']

    async with session.client('s3') as s3:
        if file_path:
            # Upload from file
            offered_bytes = os.path.getsize(file_path)
            offered_by = 'os.path.getsize(file_path), before the transfer'
            await s3.upload_file(file_path, bucket, key, ExtraArgs=extra_args)
        else:
            # Upload from content
            body = content.encode('utf-8') if isinstance(content, str) else content
            offered_bytes = len(body)
            offered_by = 'len() of the encoded body handed to put_object'
            await s3.put_object(Bucket=bucket, Key=key, Body=body, **extra_args)

        # Get object info. This is the read-back: a second request that asks the
        # store what is at the key now, rather than trusting the reply to the
        # write. It is what lets this module reach `observed`.
        response = await s3.head_object(Bucket=bucket, Key=key)
        etag = response.get('ETag', '').strip('"')
        # None, not 0: "no length came back" and "the object is empty" are
        # different facts, and a 0 standing in for both would let an unreported
        # length pass as a match against an empty upload.
        store_bytes = response.get('ContentLength')

    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

    return {
        'url': url,
        'bucket': bucket,
        'key': key,
        'etag': etag,
        'bytes_offered': offered_bytes,
        'bytes_in_store': store_bytes,
        'outcome': _length_outcome(
            kind='object',
            local_bytes=offered_bytes,
            local_by=offered_by,
            store_bytes=store_bytes,
            store_by="head_object(...)['ContentLength'], after the upload",
            detail=(
                'Length the store reports for the object now at this key, read back '
                'in a separate request. An object of identical length already at the '
                'key would be indistinguishable from ours, which is why this is '
                'evidence and not proof.'
            ),
        ),
    }


@register_module(
    module_id='cloud.aws_s3.download',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'file.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'download', 'file', 'ssrf_protected', 'path_restricted'],
    label='AWS S3 Download',
    label_key='modules.cloud.aws_s3.download.label',
    description='Download a file from AWS S3 bucket',
    description_key='modules.cloud.aws_s3.download.description',
    icon='Cloud',
    color='#FF9900',

    # Connection types
    input_types=['string'],
    output_types=['file', 'binary'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # Cloud downloads can take time depending on file size
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple downloads can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'],
    handles_sensitive_data=True,  # Files may contain sensitive data
    required_permissions=['cloud.storage'],

    params_schema={
        'aws_access_key_id': {
            'type': 'string',
            'label': 'AWS Access Key ID',
            'label_key': 'modules.cloud.aws_s3.download.params.aws_access_key_id.label',
            'description': 'AWS access key ID (defaults to env.AWS_ACCESS_KEY_ID)',
            'description_key': 'modules.cloud.aws_s3.download.params.aws_access_key_id.description',
            'placeholder': '${env.AWS_ACCESS_KEY_ID}',
            'required': False,
            'sensitive': True
        },
        'aws_secret_access_key': {
            'type': 'string',
            'label': 'AWS Secret Access Key',
            'label_key': 'modules.cloud.aws_s3.download.params.aws_secret_access_key.label',
            'description': 'AWS secret access key (defaults to env.AWS_SECRET_ACCESS_KEY)',
            'description_key': 'modules.cloud.aws_s3.download.params.aws_secret_access_key.description',
            'placeholder': '${env.AWS_SECRET_ACCESS_KEY}',
            'required': False,
            'sensitive': True
        },
        'region': {
            'type': 'string',
            'label': 'Region',
            'label_key': 'modules.cloud.aws_s3.download.params.region.label',
            'description': 'AWS region (defaults to env.AWS_REGION or us-east-1)',
            'description_key': 'modules.cloud.aws_s3.download.params.region.description',
            'placeholder': '${env.AWS_REGION}',
            'default': 'us-east-1',
            'required': False
        },
        'bucket': {
            'type': 'string',
            'label': 'Bucket Name',
            'label_key': 'modules.cloud.aws_s3.download.params.bucket.label',
            'description': 'S3 bucket name',
            'description_key': 'modules.cloud.aws_s3.download.params.bucket.description',
            'placeholder': 'my-bucket',
            'required': True
        },
        'key': {
            'type': 'string',
            'label': 'Object Key',
            'label_key': 'modules.cloud.aws_s3.download.params.key.label',
            'description': 'S3 object key (file path in bucket)',
            'description_key': 'modules.cloud.aws_s3.download.params.key.description',
            'placeholder': 'my-key',
            'required': True
        },
        'file_path': {
            'type': 'string',
            'label': 'Save to File Path',
            'label_key': 'modules.cloud.aws_s3.download.params.file_path.label',
            'description': 'Local file path to save downloaded content',
            'description_key': 'modules.cloud.aws_s3.download.params.file_path.description',
            'placeholder': '/path/to/file',
            'required': False,
            'help': 'If not provided, content is returned in memory'
        }
    },
    output_schema={
        'content': {
            'type': 'string',
            'description': 'File content (if file_path not provided)'
        },
        'file_path': {
            'type': 'string',
            'description': 'Path where file was saved (if file_path provided)'
        },
        'size': {
            'type': 'number',
            'description': (
                'ContentLength the service reports for the remote object. Not a '
                'measurement of what landed here -- see bytes_local'
            )
        },
        'bytes_local': {
            'type': 'number',
            'description': (
                'Bytes measured on this host: the saved file size from os.stat, '
                'or the length of the body actually read into memory'
            )
        },
        'content_type': {
            'type': 'string',
            'description': 'MIME type of the file'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this download was followed into reality: observed when '
                'what landed here is the length the service reports, '
                'indeterminate when it is not, accepted when nothing could be '
                'compared'
            )
        }
    },
    examples=[
        {
            'title': 'Download to memory',
            'title_key': 'modules.cloud.aws_s3.download.examples.memory.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'data/config.json'
            }
        },
        {
            'title': 'Download to file',
            'title_key': 'modules.cloud.aws_s3.download.examples.file.title',
            'params': {
                'bucket': 'my-bucket',
                'key': 'backups/database.sql',
                'file_path': '/tmp/downloaded.sql'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html'
)
async def aws_s3_download(context):
    """Download file from AWS S3"""
    params = context['params']
    file_path = params.get('file_path')
    if file_path:
        file_path = validate_path_with_env_config(file_path)

    try:
        import aioboto3
    except ImportError:
        raise ImportError(
            "aioboto3 package required. Install with: pip install aioboto3"
        ) from None

    # Get AWS credentials
    aws_access_key_id = params.get('aws_access_key_id') or os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = params.get('aws_secret_access_key') or os.getenv('AWS_SECRET_ACCESS_KEY')
    region = params.get('region') or os.getenv('AWS_REGION', 'us-east-1')

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValueError("AWS credentials required: set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")

    bucket = params['bucket']
    key = params['key']
    session = aioboto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region
    )

    async with session.client('s3') as s3:
        if file_path:
            # Download to file
            await s3.download_file(bucket, key, file_path)

            # Get metadata
            response = await s3.head_object(Bucket=bucket, Key=key)
            store_bytes = response.get('ContentLength')

            # The measurement of the world: the file that now exists here.
            local_bytes, local_by = _size_on_disk(file_path)

            return {
                'file_path': file_path,
                'size': store_bytes if store_bytes is not None else 0,
                'bytes_local': local_bytes,
                'content_type': response.get('ContentType', ''),
                'outcome': _length_outcome(
                    kind='download',
                    local_bytes=local_bytes,
                    local_by=local_by,
                    store_bytes=store_bytes,
                    store_by="head_object(...)['ContentLength']",
                    detail=(
                        'Length the store reports for the object. A fact about the '
                        'bucket, not about this host.'
                    ),
                ),
            }
        else:
            # Download to memory
            response = await s3.get_object(Bucket=bucket, Key=key)

            async with response['Body'] as stream:
                content = await stream.read()

            return {
                'content': content.decode('utf-8'),
                'size': response.get('ContentLength', 0),
                # Bytes that actually crossed the wire and were read off the
                # stream, which is not the same claim as the header's.
                'bytes_local': len(content),
                'content_type': response.get('ContentType', ''),
                'outcome': _length_outcome(
                    kind='download',
                    local_bytes=len(content),
                    local_by='len() of the body read off the response stream',
                    store_bytes=response.get('ContentLength'),
                    store_by="get_object(...)['ContentLength']",
                    detail=(
                        'Length the store declared for the body it was about to '
                        'send. Comparing it with what was read is a check that the '
                        'stream was not cut short.'
                    ),
                ),
            }


def _size_on_disk(path):
    """``(st_size, how)`` for a file that should now exist, or ``(None, how)``.

    A stat that fails is not a failed download -- the transfer already returned
    without raising. All that is lost is the ability to look, and the rung drops
    to `accepted` to match.
    """
    try:
        return os.stat(path).st_size, 'os.stat(file_path).st_size, after the transfer'
    except OSError as error:
        return None, f'os.stat failed: {type(error).__name__}'
