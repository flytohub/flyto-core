"""
Azure Blob Storage Integration Modules

Provides upload and download operations for Azure Blob Storage.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='cloud.azure.upload',
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'azure', 'blob', 'storage', 'upload'],
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
            'label_key': 'modules.cloud.azure.upload.params.file_path.label',
            'description': 'Local file path to upload',
            'description_key': 'modules.cloud.azure.upload.params.file_path.description',
            'required': True
        },
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.cloud.azure.upload.params.connection_string.label',
            'description': 'Azure Storage connection string (use env var AZURE_STORAGE_CONNECTION_STRING)',
            'description_key': 'modules.cloud.azure.upload.params.connection_string.description',
            'required': False,
            'sensitive': True
        },
        'container': {
            'type': 'string',
            'label': 'Container',
            'label_key': 'modules.cloud.azure.upload.params.container.label',
            'description': 'Azure container name',
            'description_key': 'modules.cloud.azure.upload.params.container.description',
            'required': True
        },
        'blob_name': {
            'type': 'string',
            'label': 'Blob Name',
            'label_key': 'modules.cloud.azure.upload.params.blob_name.label',
            'description': 'Name for the uploaded blob (default: filename)',
            'description_key': 'modules.cloud.azure.upload.params.blob_name.description',
            'required': False
        },
        'content_type': {
            'type': 'string',
            'label': 'Content Type',
            'label_key': 'modules.cloud.azure.upload.params.content_type.label',
            'description': 'MIME type (optional)',
            'description_key': 'modules.cloud.azure.upload.params.content_type.description',
            'required': False
        }
    },
    output_schema={
        'url': {'type': 'string'},
        'container': {'type': 'string'},
        'blob_name': {'type': 'string'},
        'size': {'type': 'number'}
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

    def validate_params(self):
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
        try:
            # Import Azure library
            try:
                from azure.storage.blob import BlobServiceClient
            except ImportError:
                raise ImportError(
                    "Azure Blob Storage library not installed. "
                    "Install with: pip install azure-storage-blob"
                )

            import os

            # Check file exists
            if not os.path.exists(self.file_path):
                raise FileNotFoundError(f"File not found: {self.file_path}")

            # Get file size
            file_size = os.path.getsize(self.file_path)

            # Initialize client
            blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            container_client = blob_service_client.get_container_client(self.container)
            blob_client = container_client.get_blob_client(self.blob_name)

            # Upload file
            with open(self.file_path, 'rb') as data:
                content_settings = None
                if self.content_type:
                    from azure.storage.blob import ContentSettings
                    content_settings = ContentSettings(content_type=self.content_type)

                blob_client.upload_blob(
                    data,
                    overwrite=True,
                    content_settings=content_settings
                )

            # Get URL
            url = blob_client.url

            return {
                "url": url,
                "container": self.container,
                "blob_name": self.blob_name,
                "size": file_size
            }

        except Exception as e:
            raise RuntimeError(f"Azure upload error: {str(e)}")


@register_module(
    module_id='cloud.azure.download',
    version='1.0.0',
    category='cloud',
    subcategory='storage',
    tags=['cloud', 'azure', 'blob', 'storage', 'download'],
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
    timeout=300,  # 5 minutes for large file downloads
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['cloud.storage.read'],

    params_schema={
        'connection_string': {
            'type': 'string',
            'label': 'Connection String',
            'label_key': 'modules.cloud.azure.download.params.connection_string.label',
            'description': 'Azure Storage connection string (use env var AZURE_STORAGE_CONNECTION_STRING)',
            'description_key': 'modules.cloud.azure.download.params.connection_string.description',
            'required': False,
            'sensitive': True
        },
        'container': {
            'type': 'string',
            'label': 'Container',
            'label_key': 'modules.cloud.azure.download.params.container.label',
            'description': 'Azure container name',
            'description_key': 'modules.cloud.azure.download.params.container.description',
            'required': True
        },
        'blob_name': {
            'type': 'string',
            'label': 'Blob Name',
            'label_key': 'modules.cloud.azure.download.params.blob_name.label',
            'description': 'Blob to download',
            'description_key': 'modules.cloud.azure.download.params.blob_name.description',
            'required': True
        },
        'destination_path': {
            'type': 'string',
            'label': 'Destination Path',
            'label_key': 'modules.cloud.azure.download.params.destination_path.label',
            'description': 'Local path to save file',
            'description_key': 'modules.cloud.azure.download.params.destination_path.description',
            'required': True
        }
    },
    output_schema={
        'file_path': {'type': 'string'},
        'size': {'type': 'number'},
        'container': {'type': 'string'},
        'blob_name': {'type': 'string'}
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

    def validate_params(self):
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
        try:
            # Import Azure library
            try:
                from azure.storage.blob import BlobServiceClient
            except ImportError:
                raise ImportError(
                    "Azure Blob Storage library not installed. "
                    "Install with: pip install azure-storage-blob"
                )

            import os

            # Ensure destination directory exists
            dest_dir = os.path.dirname(self.destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            # Initialize client
            blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            container_client = blob_service_client.get_container_client(self.container)
            blob_client = container_client.get_blob_client(self.blob_name)

            # Download file
            with open(self.destination_path, 'wb') as download_file:
                download_file.write(blob_client.download_blob().readall())

            # Get file size
            file_size = os.path.getsize(self.destination_path)

            return {
                "file_path": self.destination_path,
                "size": file_size,
                "container": self.container,
                "blob_name": self.blob_name
            }

        except Exception as e:
            raise RuntimeError(f"Azure download error: {str(e)}")
