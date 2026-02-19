# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
ZIP Create Module
Create ZIP archives from a list of files.
"""
import logging
import os
import zipfile
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError
from ....utils import validate_path_with_env_config, PathTraversalError

logger = logging.getLogger(__name__)

_COMPRESSION_MAP = {
    'stored': zipfile.ZIP_STORED,
    'deflated': zipfile.ZIP_DEFLATED,
    'bzip2': zipfile.ZIP_BZIP2,
    'lzma': zipfile.ZIP_LZMA,
}


@register_module(
    module_id='archive.zip_create',
    version='1.0.0',
    category='archive',
    tags=['archive', 'zip', 'compress', 'bundle'],
    label='Create ZIP Archive',
    label_key='modules.archive.zip_create.label',
    description='Create a ZIP archive from a list of files',
    description_key='modules.archive.zip_create.description',
    icon='Archive',
    color='#8B5CF6',

    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=60000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        field(
            'output_path',
            type='string',
            label='Output Path',
            label_key='modules.archive.zip_create.params.output_path.label',
            description='Path for the output ZIP file',
            description_key='modules.archive.zip_create.params.output_path.description',
            required=True,
            placeholder='/tmp/archive.zip',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'files',
            type='array',
            label='Files',
            label_key='modules.archive.zip_create.params.files.label',
            description='List of file paths to include in the archive',
            description_key='modules.archive.zip_create.params.files.description',
            required=True,
            group=FieldGroup.BASIC,
            items={'type': 'string'},
        ),
        field(
            'compression',
            type='select',
            label='Compression',
            label_key='modules.archive.zip_create.params.compression.label',
            description='Compression method',
            description_key='modules.archive.zip_create.params.compression.description',
            default='deflated',
            group=FieldGroup.OPTIONS,
            options=[
                {'value': 'stored', 'label': 'Stored (no compression)'},
                {'value': 'deflated', 'label': 'Deflated (default)'},
                {'value': 'bzip2', 'label': 'Bzip2'},
                {'value': 'lzma', 'label': 'LZMA'},
            ],
        ),
        field(
            'password',
            type='string',
            label='Password',
            label_key='modules.archive.zip_create.params.password.label',
            description='Optional password to protect the archive (extraction only, limited support)',
            description_key='modules.archive.zip_create.params.password.description',
            group=FieldGroup.OPTIONS,
            format='password',
        ),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Path to the created ZIP file',
            'description_key': 'modules.archive.zip_create.output.path.description',
        },
        'size': {
            'type': 'number',
            'description': 'Archive size in bytes',
            'description_key': 'modules.archive.zip_create.output.size.description',
        },
        'file_count': {
            'type': 'number',
            'description': 'Number of files in the archive',
            'description_key': 'modules.archive.zip_create.output.file_count.description',
        },
    },
    examples=[
        {
            'title': 'Create ZIP from files',
            'title_key': 'modules.archive.zip_create.examples.basic.title',
            'params': {
                'output_path': '/tmp/archive.zip',
                'files': ['/tmp/file1.txt', '/tmp/file2.txt'],
                'compression': 'deflated',
            },
        }
    ],
)
async def archive_zip_create(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a ZIP archive from a list of files."""
    params = context['params']
    output_path = params.get('output_path')
    files = params.get('files')
    compression = params.get('compression', 'deflated')
    password = params.get('password')

    if not output_path:
        raise ValidationError("Missing required parameter: output_path", field="output_path")
    if not files:
        raise ValidationError("Missing required parameter: files", field="files")
    if not isinstance(files, list):
        raise ValidationError("Parameter 'files' must be a list", field="files")

    # Validate paths
    try:
        safe_output = validate_path_with_env_config(output_path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    # Ensure output directory exists
    parent_dir = os.path.dirname(safe_output)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    compression_type = _COMPRESSION_MAP.get(compression, zipfile.ZIP_DEFLATED)
    file_count = 0

    try:
        with zipfile.ZipFile(safe_output, 'w', compression=compression_type) as zf:
            for file_path in files:
                try:
                    safe_file = validate_path_with_env_config(file_path)
                except PathTraversalError as e:
                    raise ModuleError(str(e), code="PATH_TRAVERSAL")

                if not os.path.exists(safe_file):
                    raise ModuleError(
                        "File not found: {}".format(file_path),
                        code="FILE_NOT_FOUND",
                    )

                arcname = os.path.basename(safe_file)
                zf.write(safe_file, arcname)
                file_count += 1
    except ModuleError:
        raise
    except Exception as e:
        raise ModuleError("Failed to create ZIP archive: {}".format(str(e)))

    archive_size = os.path.getsize(safe_output)

    return {
        'ok': True,
        'data': {
            'path': safe_output,
            'size': archive_size,
            'file_count': file_count,
        },
    }
