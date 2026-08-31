# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Azure Blob Storage Integration Modules

Provides upload and download operations for Azure Blob Storage.

HOW FAR THESE TWO MODULES FOLLOW REALITY, and why they differ

`cloud.azure.upload` is ACCEPTED. `upload_blob` returns the service's response
-- an `etag` and a `last_modified` for the blob it says it now holds -- and the
`size` this module reports is `os.path.getsize` of the local source file, read
before a byte left the host. That number is identical whether the blob landed
whole, truncated, or not at all, so nothing rests on it; the etag is the peer's
own account of the peer's own work, which is precisely what ACCEPTED means. The
response used to be discarded entirely, which left this module with nothing to
say beyond "no exception". It is captured now.

`cloud.azure.download` can say more, because it holds both halves. `readall()`
returns the bytes in memory and the file is written with `open(..., 'wb')`,
which truncates at open -- so the file's size afterwards is the size of what
this module wrote, with a baseline of zero guaranteed by the mode rather than
assumed. Comparing `os.path.getsize` against `len(payload)` is therefore a real
read-back of a real write:

    equal        OBSERVED (claim_by INFERRED -- the predicate is ours)
    not equal    INDETERMINATE, not FAILED. Nobody declared a size contract and
                 a short write is not the only reading; an inference of ours
                 that may be wrong is INDETERMINATE by definition.
    unreadable   ACCEPTED. The stat failed; the write had already returned.

Note what OBSERVED does not say here: that the bytes are the blob's. Both
numbers describe the payload this module received, so what is observed is that
the download was written out whole -- not that the service sent the right blob.
"""
import os
from typing import Any, Dict, Optional, Tuple

from ....utils import validate_path_with_env_config
from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ._azure_endpoint import enforce_azure_endpoint


def _size_on_disk(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` for the file just written, or ``(None, why)``."""
    try:
        return os.path.getsize(path), None
    except OSError as error:
        return None, f'{type(error).__name__}: {error.strerror or error}'


def _write_back_outcome(
    *,
    path: str,
    payload_bytes: int,
    size_on_disk: Optional[int],
    observation_error: Optional[str],
) -> Dict[str, Any]:
    """The rung the local write earned, from the two numbers that decide it."""
    payload_effect = {
        'kind': 'blob_bytes_received',
        'bytes': payload_bytes,
        'measured_by': 'len() of the payload readall() returned',
        'detail': (
            'Bytes this module was handed by the service. On its own it says '
            'nothing about the file: it is unchanged if the write went nowhere.'
        ),
    }

    if size_on_disk is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                payload_effect,
                {
                    'kind': 'local_file_not_observed',
                    'measured_by': None,
                    'reason': observation_error,
                    'detail': (
                        'The file was not read back. The write returned without '
                        'raising and was followed no further.'
                    ),
                },
            ],
        )

    disk_effect = {
        'kind': 'local_file_observed',
        'path': path,
        'bytes_on_disk': size_on_disk,
        'measured_by': "os.path.getsize(destination_path), after the 'wb' handle closed",
        'detail': (
            "Size the filesystem reports for the file that now exists here. 'wb' "
            'truncates at open, so the baseline is zero by the guarantee of the '
            'mode and this size is what this module wrote. Not fsync-ed.'
        ),
    }

    if size_on_disk == payload_bytes:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[payload_effect, disk_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            payload_effect,
            disk_effect,
            {
                'kind': 'local_file_length_disagrees',
                'predicate': 'os.path.getsize(destination_path) == len(payload)',
                'expected_bytes': payload_bytes,
                'actual_bytes': size_on_disk,
                'detail': (
                    'The file is not the length of the payload that was written to '
                    'it. That may be a short write on a full disk, or something '
                    'else changing the file between the write and the stat. We '
                    'cannot say which, so this is indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='cloud.azure.upload',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'file.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'azure', 'blob', 'storage', 'upload', 'path_restricted', 'ssrf_protected', 'filesystem_write'],
    label='Azure Upload',
    label_key='modules.cloud.azure.upload.label',
    description='Upload file to Azure Blob Storage',
    description_key='modules.cloud.azure.upload.description',
    icon='Upload',
    color='#0078D4',

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
    credential_keys=['AZURE_STORAGE_CONNECTION_STRING'],
    handles_sensitive_data=True,
    required_permissions=['cloud.storage'],

    params_schema={
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.cloud.azure.upload.params.file_path.label',
            'description': 'Local file path to upload',
            'description_key': 'modules.cloud.azure.upload.params.file_path.description',
            'required': True
        ,
            'placeholder': '/path/to/file',
},
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.cloud.azure.upload.params.connection_string.label',
            'description': 'Azure Storage connection string (use env var AZURE_STORAGE_CONNECTION_STRING)',
            'description_key': 'modules.cloud.azure.upload.params.connection_string.description',
            'required': False,
            'sensitive': True
        ,
            'placeholder': 'Enter connection string...',
},
        'container': {
            'type': 'string',
            'label': 'Container',
            'label_key': 'modules.cloud.azure.upload.params.container.label',
            'description': 'Azure container name',
            'description_key': 'modules.cloud.azure.upload.params.container.description',
            'required': True
        ,
            'placeholder': 'my-container',
},
        'blob_name': {
            'type': 'string',
            'label': 'Blob Name',
            'label_key': 'modules.cloud.azure.upload.params.blob_name.label',
            'description': 'Name for the uploaded blob (default: filename)',
            'description_key': 'modules.cloud.azure.upload.params.blob_name.description',
            'required': False
        ,
            'placeholder': 'my-name',
},
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.cloud.azure.upload.params.content_type.label',
            'description': 'MIME type (optional)',
            'description_key': 'modules.cloud.azure.upload.params.content_type.description',
            'required': False
        ,
            'placeholder': 'application/json',
}
    },
    output_schema={
        'url': {'type': 'string', 'description': 'URL address',
                'description_key': 'modules.cloud.azure.upload.output.url.description'},
        'container': {'type': 'string', 'description': 'The container',
                'description_key': 'modules.cloud.azure.upload.output.container.description'},
        'blob_name': {'type': 'string', 'description': 'The blob name',
                'description_key': 'modules.cloud.azure.upload.output.blob_name.description'},
        'size': {'type': 'number',
                'description': (
                    'Size of the LOCAL source file, read before the upload. Not '
                    'a measurement of the blob'
                ),
                'description_key': 'modules.cloud.azure.upload.output.size.description'},
        'etag': {'type': 'string',
                'description': (
                    'ETag the service returned for the blob it says it stored. '
                    'Empty when the response carried none'
                ),
                'description_key': 'modules.cloud.azure.upload.output.etag.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far this upload was followed into reality. Always '
                    '"accepted": the service acknowledged the blob and it is '
                    'never read back'
                ),
                'description_key': 'modules.cloud.azure.upload.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Upload image',
            'params': {
                'file_path': '/tmp/screenshot.png',
                'container': 'images',
                'blob_name': 'screenshots/2024/screenshot.png',
                'content_type': 'image/png'
            }
        },
        {
            'title': 'Upload document',
            'params': {
                'file_path': '/tmp/report.pdf',
                'container': 'documents',
                'blob_name': 'reports/monthly.pdf'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class AzureUploadModule(BaseModule):
    """Azure Blob Storage Upload Module"""

    def validate_params(self) -> None:
        self.file_path = self.params.get('file_path')
        self.connection_string = self.params.get('connection_string')
        self.container = self.params.get('container')
        self.blob_name = self.params.get('blob_name')
        self.content_type = self.params.get('content_type')

        if not self.file_path or not self.container:
            raise ValueError("file_path and container are required")

        # Get connection string from env if not provided
        if not self.connection_string:
            import os
            self.connection_string = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
            if not self.connection_string:
                raise ValueError(
                    "connection_string parameter or AZURE_STORAGE_CONNECTION_STRING "
                    "environment variable is required"
                )

        # Default blob name to filename
        if not self.blob_name:
            import os
            self.blob_name = os.path.basename(self.file_path)

    async def execute(self) -> Any:
        # SECURITY: the download twin below confines destination_path; this side
        # read whatever host file the caller named and streamed it to a
        # caller-chosen bucket (GHSA-45hf-2fmj-q442). Validated before the try
        # block so the rejection surfaces as PathTraversalError rather than being
        # rewritten into a generic upload error.
        file_path = validate_path_with_env_config(self.file_path)
        enforce_azure_endpoint(self.connection_string)

        try:
            # Import Azure library
            try:
                from azure.storage.blob import BlobServiceClient
            except ImportError:
                raise ImportError(
                    "Azure Blob Storage library not installed. "
                    "Install with: pip install azure-storage-blob"
                ) from None

            # Check file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # Get file size
            file_size = os.path.getsize(file_path)

            # Initialize client
            blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            container_client = blob_service_client.get_container_client(self.container)
            blob_client = container_client.get_blob_client(self.blob_name)

            # Upload file
            with open(file_path, 'rb') as data:
                content_settings = None
                if self.content_type:
                    from azure.storage.blob import ContentSettings
                    content_settings = ContentSettings(content_type=self.content_type)

                # The response was thrown away here. It is the only thing the
                # service says about this upload, so it is kept: etag and
                # last_modified for the blob it claims to hold.
                response = blob_client.upload_blob(
                    data,
                    overwrite=True,
                    content_settings=content_settings
                )

            reported = dict(response) if isinstance(response, dict) else {}
            etag = str(reported.get('etag', '') or '')
            last_modified = reported.get('last_modified')

            # Get URL
            url = blob_client.url

            return {
                "url": url,
                "container": self.container,
                "blob_name": self.blob_name,
                "size": file_size,
                "etag": etag,
                "outcome": envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[
                        {
                            'kind': 'blob_bytes_offered',
                            'container': self.container,
                            'blob_name': self.blob_name,
                            'bytes_offered': file_size,
                            'measured_by': 'os.path.getsize(file_path), before the upload',
                            'detail': (
                                'Size of the local source file. It reads identically '
                                'whether Azure stored every byte, some of them, or '
                                'none.'
                            ),
                        },
                        {
                            'kind': 'blob_reported_by_service',
                            'etag': etag,
                            'last_modified': (
                                last_modified.isoformat()
                                if hasattr(last_modified, 'isoformat')
                                else last_modified
                            ),
                            'measured_by': 'the response upload_blob returned',
                            'detail': (
                                "The service's own account of the blob it says it "
                                'stored. No second request was made and the blob was '
                                'not read back.'
                            ),
                        },
                    ],
                ),
            }

        except Exception as e:
            raise RuntimeError(f"Azure upload error: {str(e)}") from e


@register_module(
    module_id='cloud.azure.download',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'file.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'azure', 'blob', 'storage', 'download', 'ssrf_protected', 'path_restricted', 'filesystem_write'],
    label='Azure Download',
    label_key='modules.cloud.azure.download.label',
    description='Download file from Azure Blob Storage',
    description_key='modules.cloud.azure.download.description',
    icon='Download',
    color='#0078D4',

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
    credential_keys=['AZURE_STORAGE_CONNECTION_STRING'],
    handles_sensitive_data=True,
    required_permissions=['cloud.storage'],

    params_schema={
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.cloud.azure.download.params.connection_string.label',
            'description': 'Azure Storage connection string (use env var AZURE_STORAGE_CONNECTION_STRING)',
            'description_key': 'modules.cloud.azure.download.params.connection_string.description',
            'placeholder': 'DefaultEndpointsProtocol=https;...',
            'required': False,
            'sensitive': True
        },
        'container': {
            'type': 'string',
            'label': 'Container',
            'label_key': 'modules.cloud.azure.download.params.container.label',
            'description': 'Azure container name',
            'description_key': 'modules.cloud.azure.download.params.container.description',
            'placeholder': 'my-container',
            'required': True
        },
        'blob_name': {
            'type': 'string',
            'label': 'Blob Name',
            'label_key': 'modules.cloud.azure.download.params.blob_name.label',
            'description': 'Blob to download',
            'description_key': 'modules.cloud.azure.download.params.blob_name.description',
            'placeholder': 'my-blob',
            'required': True
        },
        'destination_path': {
            'type': 'string',
            'label': 'Destination Path',
            'label_key': 'modules.cloud.azure.download.params.destination_path.label',
            'description': 'Local path to save file',
            'description_key': 'modules.cloud.azure.download.params.destination_path.description',
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
                'os.path.getsize after the write. null when it could not be read '
                'back'
            ),
        },
        'bytes_received': {
            'type': 'number',
            'description': 'Length of the payload the service sent, before writing',
        },
        'container': {'type': 'string', 'description': 'The container'},
        'blob_name': {'type': 'string', 'description': 'The blob name'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this download was followed into reality: observed when '
                'the file written is the length of the payload received, '
                'indeterminate when it is not, accepted when it could not be '
                'read back'
            ),
        }
    },
    examples=[
        {
            'title': 'Download backup',
            'params': {
                'container': 'backups',
                'blob_name': 'data/backup-2024.zip',
                'destination_path': '/tmp/backup.zip'
            }
        },
        {
            'title': 'Download image',
            'params': {
                'container': 'images',
                'blob_name': 'photos/vacation.jpg',
                'destination_path': '/tmp/photo.jpg'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class AzureDownloadModule(BaseModule):
    """Azure Blob Storage Download Module"""

    def validate_params(self) -> None:
        self.connection_string = self.params.get('connection_string')
        self.container = self.params.get('container')
        self.blob_name = self.params.get('blob_name')
        self.destination_path = self.params.get('destination_path')

        if not self.container or not self.blob_name or not self.destination_path:
            raise ValueError("container, blob_name, and destination_path are required")

        # Get connection string from env if not provided
        if not self.connection_string:
            import os
            self.connection_string = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
            if not self.connection_string:
                raise ValueError(
                    "connection_string parameter or AZURE_STORAGE_CONNECTION_STRING "
                    "environment variable is required"
                )

    async def execute(self) -> Any:
        destination_path = validate_path_with_env_config(self.destination_path)
        enforce_azure_endpoint(self.connection_string)

        try:
            # Import Azure library
            try:
                from azure.storage.blob import BlobServiceClient
            except ImportError:
                raise ImportError(
                    "Azure Blob Storage library not installed. "
                    "Install with: pip install azure-storage-blob"
                ) from None

            # Ensure destination directory exists
            dest_dir = os.path.dirname(destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            # Initialize client
            blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            container_client = blob_service_client.get_container_client(self.container)
            blob_client = container_client.get_blob_client(self.blob_name)

            # Download file. The payload is held in a name rather than passed
            # straight into write() -- `readall()` already materialises the whole
            # blob in memory either way, so this costs nothing and it is what
            # makes a read-back possible: without len(payload) there is no number
            # to compare the file against.
            payload = blob_client.download_blob().readall()
            with open(destination_path, 'wb') as download_file:
                download_file.write(payload)

            # Outside the `with`: the handle is closed, so the buffered bytes
            # have reached the kernel and the size is a size, not a race.
            file_size, observation_error = _size_on_disk(destination_path)

            return {
                "file_path": destination_path,
                "size": file_size,
                "bytes_received": len(payload),
                "container": self.container,
                "blob_name": self.blob_name,
                "outcome": _write_back_outcome(
                    path=destination_path,
                    payload_bytes=len(payload),
                    size_on_disk=file_size,
                    observation_error=observation_error,
                ),
            }

        except Exception as e:
            raise RuntimeError(f"Azure download error: {str(e)}") from e
