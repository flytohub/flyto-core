# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AWS S3 Download Module
Download a file from an Amazon S3 bucket to the local filesystem using boto3.

HOW FAR THIS MODULE FOLLOWS REALITY

The effect of a download is a LOCAL file, so the evidence has to be local too.
Three answers, decided per call from what could be measured:

  local size read back, and it equals the object's length   OBSERVED
      `os.stat(output_path).st_size` after the transfer is a measurement of the
      world: the file that now exists on this host. `download_file` writes
      through a temporary file and renames, so the size after it returns is the
      size of what it put there, and the baseline is not needed. Comparing it
      with the `ContentLength` the service reports for the same key is a
      cross-check of one side against the other, which is why `claim_by` is
      INFERRED -- the equality is this module's own predicate, not a caller's.

  local size read back, and it does not match              INDETERMINATE
      Not FAILED. Nobody declared a size contract, and the mismatch has an
      innocent reading: `head_object` is a second request, so an object
      overwritten between the GET and the HEAD reports a length that was never
      ours. An inference of ours that may be wrong is INDETERMINATE by the
      definition in engine/outcome.py; calling it FAILED would put a red mark on
      a correct download.

  local size could not be read                              ACCEPTED
      The stat failed, or the service reported no ContentLength. The transfer
      itself already returned without raising, so the bytes were acknowledged;
      all that is lost is our ability to look.

What the pre-existing `size` field is NOT: evidence of the download. It is
`head_object(...)['ContentLength']` -- the length of the REMOTE object, which
reads identically whether the local write happened or not. It stays in the
payload under its old name because callers use it, and `bytes_on_disk` is the
number the rung actually rests on.

Error paths carry no envelope: every one of them raises, and a raised exception
becomes a StepExecutionError with the payload discarded (see the same note on
`http.request`). A timeout here is a genuine INDETERMINATE and has nowhere to
sit until raise-paths can carry one.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

from .....utils import validate_path_with_env_config
from .....engine.outcome import ClaimBy, Outcome, envelope
from ....errors import ModuleError, ValidationError
from ....registry import register_module
from ....schema import compose
from ....schema.builders import field
from ....schema.constants import FieldGroup

logger = logging.getLogger(__name__)


def _observe_size_on_disk(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` when the downloaded file could be read back, else ``(None, why)``.

    The only line in this module that measures the world rather than reporting
    what the service said about itself.
    """
    try:
        return os.stat(path).st_size, None
    except OSError as error:
        return None, f"{type(error).__name__}: {error.strerror or error}"


def _download_outcome(
    *,
    path: str,
    remote_bytes: Optional[int],
    local_bytes: Optional[int],
    observation_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this download earned, and the measurements that earned it."""
    remote_effect = {
        'kind': 'object_length_reported',
        'bytes': remote_bytes,
        'measured_by': "head_object(...)['ContentLength']",
        'detail': (
            'Length the service reports for the object. A fact about the bucket, '
            'not about this host: it is the same number whether or not the local '
            'file was written.'
        ),
    }

    if local_bytes is None or remote_bytes is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                remote_effect,
                {
                    'kind': 'local_file_not_observed',
                    'measured_by': None,
                    'reason': observation_error or (
                        'the service reported no ContentLength for this object, so '
                        'there was nothing to compare the local file against'
                    ),
                    'detail': (
                        'The transfer returned without raising and the file was not '
                        'read back.'
                    ),
                },
            ],
        )

    local_effect = {
        'kind': 'local_file_observed',
        'path': path,
        'bytes_on_disk': local_bytes,
        'measured_by': 'os.stat(output_path).st_size, after the transfer returned',
        'detail': (
            'Size the kernel reports for the file that now exists on this host. '
            'Not fsync-ed: durability across power loss is not observed and is '
            'not claimed.'
        ),
    }

    if local_bytes == remote_bytes:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: a predicate was evaluated and it was ours. No caller
            # asked for a byte count.
            claim_by=ClaimBy.INFERRED,
            effects=[remote_effect, local_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            remote_effect,
            local_effect,
            {
                'kind': 'object_length_disagrees',
                'predicate': "os.stat(output_path).st_size == head_object['ContentLength']",
                'expected_bytes': remote_bytes,
                'actual_bytes': local_bytes,
                'detail': (
                    'The local file is not the length the service reports for the '
                    'object. That may be a short write, or it may be this module\'s '
                    'inference being wrong -- head_object is a second request, and an '
                    'object replaced between the two would report a length that was '
                    'never the one we downloaded. We cannot say which, so this is '
                    'indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='aws.s3.download',
    version='1.0.0',
    category='cloud',
    tags=['cloud', 'aws', 's3', 'storage', 'download', 'file', 'path_restricted'],
    label='S3 Download',
    label_key='modules.aws.s3.download.label',
    description='Download a file from an AWS S3 bucket to a local path',
    description_key='modules.aws.s3.download.description',
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
        'path': {'type': 'string', 'description': 'Local file path where the file was saved', 'description_key': 'modules.aws.s3.download.output.path.description'},
        'size': {
            'type': 'number',
            'description': (
                'Length the service reports for the REMOTE object, from '
                "head_object ContentLength. Not a measurement of the local file "
                '-- see bytes_on_disk'
            ),
            'description_key': 'modules.aws.s3.download.output.size.description',
        },
        'bytes_on_disk': {
            'type': 'number',
            'description': (
                'Size the filesystem reports for the downloaded file, from '
                'os.stat. null when the file could not be read back'
            ),
            'description_key': 'modules.aws.s3.download.output.bytes_on_disk.description',
        },
        'content_type': {'type': 'string', 'description': 'MIME type of the downloaded file', 'description_key': 'modules.aws.s3.download.output.content_type.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this download was followed into reality: observed when '
                'the local file matches the length the service reports, '
                'indeterminate when it does not, accepted when the file could '
                'not be read back'
            ),
            'description_key': 'modules.aws.s3.download.output.outcome.description',
        },
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
    author='Flyto2 Team',
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

    output_path = validate_path_with_env_config(output_path)

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
        raise ModuleError(
            'boto3 package is required. Install with: pip install boto3'
        ) from None

    content_type = ''
    # None, not 0, when the service reports no length: "no number came back" and
    # "the object is empty" are different facts, and a 0 standing in for both
    # would let an unreported length masquerade as a match against an empty
    # local file.
    remote_bytes: Optional[int] = None

    def _download():
        nonlocal content_type, remote_bytes
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
        remote_bytes = head.get('ContentLength')

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _download)
    except Exception as exc:
        error_name = type(exc).__name__
        raise ModuleError(f'S3 download failed ({error_name}): {exc}') from exc

    # The one measurement of the world in this module, and the reason it can say
    # more than `accepted`. Outside the executor: the transfer has returned, so
    # st_size is a size and not a race.
    local_bytes, observation_error = _observe_size_on_disk(output_path)

    return {
        'ok': True,
        'data': {
            'path': output_path,
            'size': remote_bytes if remote_bytes is not None else 0,
            'bytes_on_disk': local_bytes,
            'content_type': content_type,
            'outcome': _download_outcome(
                path=output_path,
                remote_bytes=remote_bytes,
                local_bytes=local_bytes,
                observation_error=observation_error,
            ),
        },
    }
