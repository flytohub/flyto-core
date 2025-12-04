"""
Google Cloud Storage (GCS) Integration Modules

Provides upload and download operations for Google Cloud Storage.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='cloud.gcs.upload',
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'gcs', 'google', 'storage', 'upload'],
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
    timeout=300,  # 5 minutes for large file uploads
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['cloud.storage.write'],

    params_schema={
        'file_path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.cloud.gcs.upload.params.file_path.label',
            'description': 'Local file path to upload',
            'description_key': 'modules.cloud.gcs.upload.params.file_path.description',
            'required': True
        },
        'bucket': {
            'type': 'string',
            'label': 'Bucket',
            'label_key': 'modules.cloud.gcs.upload.params.bucket.label',
            'description': 'GCS bucket name',
            'description_key': 'modules.cloud.gcs.upload.params.bucket.description',
            'required': True
        },
        'object_name': {
            'type': 'string',
            'label': 'Object Name',
            'label_key': 'modules.cloud.gcs.upload.params.object_name.label',
            'description': 'Name for the uploaded object (default: filename)',
            'description_key': 'modules.cloud.gcs.upload.params.object_name.description',
            'required': False
        },
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.cloud.gcs.upload.params.content_type.label',
            'description': 'MIME type (optional)',
            'description_key': 'modules.cloud.gcs.upload.params.content_type.description',
            'required': False
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
        'url': {'type': 'string'},
        'bucket': {'type': 'string'},
        'object_name': {'type': 'string'},
        'size': {'type': 'number'},
        'public_url': {'type': 'string'}
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

    def validate_params(self):
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
        try:
            # Import GCS library
            try:
                from google.cloud import storage
            except ImportError:
                raise ImportError(
                    "Google Cloud Storage library not installed. "
                    "Install with: pip install google-cloud-storage"
                )

            import os

            # Check file exists
            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"File not found: {self.file_path}")

            # Get file size
            file_size = os.path.getsize(self.file_path)

            # Initialize client
            client = storage.Client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(self.object_name)

            # Set content type if provided
            if self.content_type:
                blob.content_type = self.content_type

            # Upload file
            blob.upload_from_filename(self.file_path)

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
                "public_url": public_url
            }

        except Exception as e:
            raise RuntimeError(f"GCS upload error: {str(e)}")


@register_module(
    module_id='cloud.gcs.download',
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'gcs', 'google', 'storage', 'download'],
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
    timeout=300,  # 5 minutes for large file downloads
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['cloud.storage.read'],

    params_schema={
        'bucket': {
            'type': 'string',
            'label': 'Bucket',
            'label_key': 'modules.cloud.gcs.download.params.bucket.label',
            'description': 'GCS bucket name',
            'description_key': 'modules.cloud.gcs.download.params.bucket.description',
            'required': True
        },
        'object_name': {
            'type': 'string',
            'label': 'Object Name',
            'label_key': 'modules.cloud.gcs.download.params.object_name.label',
            'description': 'Object to download',
            'description_key': 'modules.cloud.gcs.download.params.object_name.description',
            'required': True
        },
        'destination_path': {
            'type': 'string',
            'label': 'Destination Path',
            'label_key': 'modules.cloud.gcs.download.params.destination_path.label',
            'description': 'Local path to save file',
            'description_key': 'modules.cloud.gcs.download.params.destination_path.description',
            'required': True
        }
    },
    output_schema={
        'file_path': {'type': 'string'},
        'size': {'type': 'number'},
        'bucket': {'type': 'string'},
        'object_name': {'type': 'string'}
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

    def validate_params(self):
        self.bucket = self.params.get('bucket')
        self.object_name = self.params.get('object_name')
        self.destination_path = self.params.get('destination_path')

        if not self.bucket or not self.object_name or not self.destination_path:
            raise ValueError("bucket, object_name, and destination_path are required")

    async def execute(self) -> Any:
        try:
            # Import GCS library
            try:
                from google.cloud import storage
            except ImportError:
                raise ImportError(
                    "Google Cloud Storage library not installed. "
                    "Install with: pip install google-cloud-storage"
                )

            import os

            # Ensure destination directory exists
            dest_dir = os.path.dirname(self.destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            # Initialize client
            client = storage.Client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(self.object_name)

            # Download file
            blob.download_to_filename(self.destination_path)

            # Get file size
            file_size = os.path.getsize(self.destination_path)

            return {
                "file_path": self.destination_path,
                "size": file_size,
                "bucket": self.bucket,
                "object_name": self.object_name
            }

        except Exception as e:
            raise RuntimeError(f"GCS download error: {str(e)}")
