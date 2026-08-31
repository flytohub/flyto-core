# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Google Cloud Storage (GCS) Integration Modules

Provides upload and download operations for Google Cloud Storage.

HOW FAR THESE TWO MODULES FOLLOW REALITY, and why they differ

The pair is not symmetric, because the evidence available to each is not.

`cloud.gcs.upload` is ACCEPTED. `blob.upload_from_filename` returns None, and
the `size` this module reports is `os.path.getsize` of the LOCAL source file
read before the upload -- the same number whether the object reached the bucket
whole, truncated, or not at all. It fails the test this contract turns on, so no
rung rests on it. What the library does leave behind after a successful upload
is the service's own account of the object it says it stored (`blob.size`,
`blob.etag`, `blob.md5_hash`, populated from the upload response); those are
reported as evidence and are exactly what ACCEPTED means -- taking the peer's
word for its own work. Nothing here reads the object back.

`cloud.gcs.download` is OBSERVED when the file it wrote is non-empty. The effect
of a download is a local file, and `os.path.getsize(destination_path)` after
`download_to_filename` measures the file that now exists on this host -- a
measurement of the world, not of our own inputs.

The zero-byte case is ACCEPTED instead, and the reason is the same one that
demoted an empty result set in `database.query`: a size of 0 reads identically
whether the object was empty, the destination was already an empty file, or
nothing was written at all. A number that would be unchanged had the effect not
happened is not evidence of it.

Neither module declares a postcondition, so `ceiling_for(None)` caps both at
OBSERVED. That ceiling never binds: the honest claims are at or below it.
"""
from typing import Any, Dict

from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module


def _peer_reported(blob: Any) -> Dict[str, Any]:
    """What the service says it stored, read off the blob after the upload.

    `getattr` with a default throughout: these are populated from the upload
    response and an absent one is an absent fact, not an error. They are
    reported, never compared -- comparing our own file size against the length
    the service claims for its copy would still be reading the peer's report of
    the peer's own work.
    """
    reported = {
        'size': getattr(blob, 'size', None),
        'etag': getattr(blob, 'etag', None),
        'md5_hash': getattr(blob, 'md5_hash', None),
        'generation': getattr(blob, 'generation', None),
    }
    return {key: value for key, value in reported.items() if value is not None}


def _local_file_outcome(*, path: str, size: int, source: str) -> Dict[str, Any]:
    """OBSERVED for a file with bytes in it, ACCEPTED for one without.

    The split is not fussiness. `os.path.getsize` returning a positive number
    after `download_to_filename` is a fact about this host that could not be
    true unless something wrote those bytes. Returning 0 is not: an empty
    object, an empty file that was already there, and a write that never
    happened all produce it.
    """
    if size > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'local_file_observed',
                'path': path,
                'source': source,
                'bytes_on_disk': size,
                'measured_by': 'os.path.getsize(destination_path), after the download',
                'detail': (
                    'Size the filesystem reports for the file that now exists here. '
                    'Not fsync-ed, and not compared against the object: what is '
                    'observed is that a non-empty file was written, not that its '
                    'contents are the ones asked for.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'local_file_empty',
            'path': path,
            'source': source,
            'bytes_on_disk': 0,
            'measured_by': None,
            'detail': (
                'The transfer returned without raising and the destination is zero '
                'bytes. That is not an observation of anything: an empty object, a '
                'pre-existing empty file and a write that never happened all read '
                'the same here.'
            ),
        }],
    )


@register_module(
    module_id='cloud.gcs.upload',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'file.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'gcs', 'google', 'storage', 'upload', 'path_restricted', 'ssrf_protected'],
    label='GCS Upload',
    label_key='modules.cloud.gcs.upload.label',
    description='Upload file to Google Cloud Storage',
    description_key='modules.cloud.gcs.upload.description',
    icon='Upload',
    color='#4285F4',

    # Connection types
    input_types=['file', 'binary'],
    output_types=['url', 'json'],

    # Phase 2: Execution settings
    timeout_ms=300000,  # 5 minutes for large file uploads
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GOOGLE_CLOUD_CREDENTIALS'],
    handles_sensitive_data=True,
    required_permissions=['cloud.storage'],

    params_schema={
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.cloud.gcs.upload.params.file_path.label',
            'description': 'Local file path to upload',
            'description_key': 'modules.cloud.gcs.upload.params.file_path.description',
            'required': True
        ,
            'placeholder': '/path/to/file',
},
        'bucket': {
            'type': 'string',
            'label': 'Bucket',
            'label_key': 'modules.cloud.gcs.upload.params.bucket.label',
            'description': 'GCS bucket name',
            'description_key': 'modules.cloud.gcs.upload.params.bucket.description',
            'required': True
        ,
            'placeholder': 'my-bucket',
},
        'object_name': {
            'type': 'string',
            'label': 'Object Name',
            'label_key': 'modules.cloud.gcs.upload.params.object_name.label',
            'description': 'Name for the uploaded object (default: filename)',
            'description_key': 'modules.cloud.gcs.upload.params.object_name.description',
            'required': False
        ,
            'placeholder': 'my-name',
},
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.cloud.gcs.upload.params.content_type.label',
            'description': 'MIME type (optional)',
            'description_key': 'modules.cloud.gcs.upload.params.content_type.description',
            'required': False
        ,
            'placeholder': 'application/json',
},
        'public': {
            'type': 'boolean',
            'label': 'Public',
            'label_key': 'modules.cloud.gcs.upload.params.public.label',
            'description': 'Make file publicly accessible',
            'description_key': 'modules.cloud.gcs.upload.params.public.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'url': {'type': 'string', 'description': 'URL address',
                'description_key': 'modules.cloud.gcs.upload.output.url.description'},
        'bucket': {'type': 'string', 'description': 'Storage bucket name',
                'description_key': 'modules.cloud.gcs.upload.output.bucket.description'},
        'object_name': {'type': 'string', 'description': 'Object name in storage',
                'description_key': 'modules.cloud.gcs.upload.output.object_name.description'},
        'size': {'type': 'number',
                'description': (
                    'Size of the LOCAL source file, read before the upload. Not '
                    'a measurement of the object in the bucket'
                ),
                'description_key': 'modules.cloud.gcs.upload.output.size.description'},
        'public_url': {'type': 'string', 'description': 'Public accessible URL',
                'description_key': 'modules.cloud.gcs.upload.output.public_url.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far this upload was followed into reality. Always '
                    '"accepted": the service acknowledged the transfer and the '
                    'object is never read back'
                ),
                'description_key': 'modules.cloud.gcs.upload.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Upload image',
            'params': {
                'file_path': '/tmp/screenshot.png',
                'bucket': 'my-bucket',
                'object_name': 'screenshots/2024/screenshot.png',
                'content_type': 'image/png',
                'public': True
            }
        },
        {
            'title': 'Upload CSV data',
            'params': {
                'file_path': '/tmp/report.csv',
                'bucket': 'data-backup',
                'object_name': 'reports/daily.csv'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GCSUploadModule(BaseModule):
    """Google Cloud Storage Upload Module"""

    def validate_params(self) -> None:
        self.file_path = self.params.get('file_path')
        self.bucket = self.params.get('bucket')
        self.object_name = self.params.get('object_name')
        self.content_type = self.params.get('content_type')
        self.public = self.params.get('public', False)

        if not self.file_path or not self.bucket:
            raise ValueError("file_path and bucket are required")

        # Default object name to filename
        if not self.object_name:
            import os
            self.object_name = os.path.basename(self.file_path)

    async def execute(self) -> Any:
        # SECURITY: the download twin below confines destination_path; this side
        # read whatever host file the caller named and streamed it to a
        # caller-chosen bucket (GHSA-45hf-2fmj-q442). Validated before the try
        # block so the rejection surfaces as PathTraversalError rather than being
        # rewritten into a generic upload error.
        file_path = validate_path_with_env_config(self.file_path)

        try:
            # Import GCS library
            try:
                from google.cloud import storage
            except ImportError:
                raise ImportError(
                    "Google Cloud Storage library not installed. "
                    "Install with: pip install google-cloud-storage"
                ) from None

            import os

            # Check file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # Get file size
            file_size = os.path.getsize(file_path)

            # Initialize client
            client = storage.Client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(self.object_name)

            # Set content type if provided
            if self.content_type:
                blob.content_type = self.content_type

            # Upload file
            blob.upload_from_filename(file_path)

            # Make public if requested
            if self.public:
                blob.make_public()

            # Get URLs
            gs_url = f"gs://{self.bucket}/{self.object_name}"
            public_url = blob.public_url if self.public else None

            return {
                "url": gs_url,
                "bucket": self.bucket,
                "object_name": self.object_name,
                "size": file_size,
                "public_url": public_url,
                "outcome": envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[
                        {
                            'kind': 'object_bytes_offered',
                            'bucket': self.bucket,
                            'object_name': self.object_name,
                            'bytes_offered': file_size,
                            'measured_by': 'os.path.getsize(file_path), before the upload',
                            'detail': (
                                'Size of the local source file. It reads identically '
                                'whether GCS stored every byte, some of them, or none.'
                            ),
                        },
                        {
                            'kind': 'object_reported_by_service',
                            'reported': _peer_reported(blob),
                            'measured_by': (
                                'blob properties populated from the upload response'
                            ),
                            'detail': (
                                "The service's own account of the object it says it "
                                'stored. No second request was made and the object was '
                                'not read back.'
                            ),
                        },
                    ],
                ),
            }

        except Exception as e:
            raise RuntimeError(f"GCS upload error: {str(e)}") from e


@register_module(
    module_id='cloud.gcs.download',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'file.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'gcs', 'google', 'storage', 'download', 'ssrf_protected', 'path_restricted'],
    label='GCS Download',
    label_key='modules.cloud.gcs.download.label',
    description='Download file from Google Cloud Storage',
    description_key='modules.cloud.gcs.download.description',
    icon='Download',
    color='#4285F4',

    # Connection types
    input_types=['url', 'text'],
    output_types=['file', 'binary'],

    # Phase 2: Execution settings
    timeout_ms=300000,  # 5 minutes for large file downloads
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GOOGLE_CLOUD_CREDENTIALS'],
    handles_sensitive_data=True,
    required_permissions=['cloud.storage'],

    params_schema={
        'bucket': {
            'type': 'string',
            'label': 'Bucket',
            'label_key': 'modules.cloud.gcs.download.params.bucket.label',
            'description': 'GCS bucket name',
            'description_key': 'modules.cloud.gcs.download.params.bucket.description',
            'placeholder': 'my-bucket',
            'required': True
        },
        'object_name': {
            'type': 'string',
            'label': 'Object Name',
            'label_key': 'modules.cloud.gcs.download.params.object_name.label',
            'description': 'Object to download',
            'description_key': 'modules.cloud.gcs.download.params.object_name.description',
            'placeholder': 'path/to/object',
            'required': True
        },
        'destination_path': {
            'type': 'string',
            'label': 'Destination Path',
            'label_key': 'modules.cloud.gcs.download.params.destination_path.label',
            'description': 'Local path to save file',
            'description_key': 'modules.cloud.gcs.download.params.destination_path.description',
            'required': True
        ,
            'placeholder': '/path/to/file',
}
    },
    output_schema={
        'file_path': {'type': 'string', 'description': 'The file path'},
        'size': {
            'type': 'number',
            'description': (
                'Size of the file that now exists on this host, from '
                'os.path.getsize after the download'
            ),
        },
        'bucket': {'type': 'string', 'description': 'Storage bucket name'},
        'object_name': {'type': 'string', 'description': 'Object name in storage'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this download was followed into reality: observed when '
                'the saved file is non-empty, accepted at zero bytes -- which '
                'reads the same as a file that was never written'
            ),
        }
    },
    examples=[
        {
            'title': 'Download backup',
            'params': {
                'bucket': 'my-backups',
                'object_name': 'data/backup-2024.zip',
                'destination_path': '/tmp/backup.zip'
            }
        },
        {
            'title': 'Download image',
            'params': {
                'bucket': 'image-storage',
                'object_name': 'photos/vacation.jpg',
                'destination_path': '/tmp/photo.jpg'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GCSDownloadModule(BaseModule):
    """Google Cloud Storage Download Module"""

    def validate_params(self) -> None:
        self.bucket = self.params.get('bucket')
        self.object_name = self.params.get('object_name')
        self.destination_path = self.params.get('destination_path')

        if not self.bucket or not self.object_name or not self.destination_path:
            raise ValueError("bucket, object_name, and destination_path are required")

    async def execute(self) -> Any:
        destination_path = validate_path_with_env_config(self.destination_path)

        try:
            # Import GCS library
            try:
                from google.cloud import storage
            except ImportError:
                raise ImportError(
                    "Google Cloud Storage library not installed. "
                    "Install with: pip install google-cloud-storage"
                ) from None

            import os

            # Ensure destination directory exists
            dest_dir = os.path.dirname(destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            # Initialize client
            client = storage.Client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(self.object_name)

            # Download file
            blob.download_to_filename(destination_path)

            # Get file size
            file_size = os.path.getsize(destination_path)

            return {
                "file_path": destination_path,
                "size": file_size,
                "bucket": self.bucket,
                "object_name": self.object_name,
                "outcome": _local_file_outcome(
                    path=destination_path,
                    size=file_size,
                    source=f'gs://{self.bucket}/{self.object_name}',
                ),
            }

        except Exception as e:
            raise RuntimeError(f"GCS download error: {str(e)}") from e
