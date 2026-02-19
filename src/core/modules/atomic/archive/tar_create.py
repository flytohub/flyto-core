# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
TAR Create Module
Create TAR archives with optional compression (gzip, bz2, xz).
"""
import logging
import os
import tarfile
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError
from ....utils import validate_path_with_env_config, PathTraversalError

logger = logging.getLogger(__name__)

_COMPRESSION_MODES = {
    'none': 'w',
    'gzip': 'w:gz',
    'bz2': 'w:bz2',
    'xz': 'w:xz',
}


@register_module(
    module_id='archive.tar_create',
    version='1.0.0',
    category='archive',
    tags=['archive', 'tar', 'compress', 'gzip', 'bundle'],
    label='Create TAR Archive',
    label_key='modules.archive.tar_create.label',
    description='Create a TAR archive with optional gzip/bz2/xz compression',
    description_key='modules.archive.tar_create.description',
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
            label_key='modules.archive.tar_create.params.output_path.label',
            description='Path for the output TAR file',
            description_key='modules.archive.tar_create.params.output_path.description',
            required=True,
            placeholder='/tmp/archive.tar.gz',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'files',
            type='array',
            label='Files',
            label_key='modules.archive.tar_create.params.files.label',
            description='List of file paths to include in the archive',
            description_key='modules.archive.tar_create.params.files.description',
            required=True,
            group=FieldGroup.BASIC,
            items={'type': 'string'},
        ),
        field(
            'compression',
            type='select',
            label='Compression',
            label_key='modules.archive.tar_create.params.compression.label',
            description='Compression method',
            description_key='modules.archive.tar_create.params.compression.description',
            default='gzip',
            group=FieldGroup.OPTIONS,
            options=[
                {'value': 'none', 'label': 'None (plain tar)'},
                {'value': 'gzip', 'label': 'Gzip (.tar.gz)'},
                {'value': 'bz2', 'label': 'Bzip2 (.tar.bz2)'},
                {'value': 'xz', 'label': 'XZ (.tar.xz)'},
            ],
        ),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Path to the created TAR file',
            'description_key': 'modules.archive.tar_create.output.path.description',
        },
        'size': {
            'type': 'number',
            'description': 'Archive size in bytes',
            'description_key': 'modules.archive.tar_create.output.size.description',
        },
        'file_count': {
            'type': 'number',
            'description': 'Number of files in the archive',
            'description_key': 'modules.archive.tar_create.output.file_count.description',
        },
    },
    examples=[
        {
            'title': 'Create gzipped TAR archive',
            'title_key': 'modules.archive.tar_create.examples.basic.title',
            'params': {
                'output_path': '/tmp/archive.tar.gz',
                'files': ['/tmp/file1.txt', '/tmp/file2.txt'],
                'compression': 'gzip',
            },
        }
    ],
)
async def archive_tar_create(context: Dict[str, Any]) -> Dict[str, Any]:
    """Create a TAR archive with optional compression."""
    params = context['params']
    output_path = params.get('output_path')
    files = params.get('files')
    compression = params.get('compression', 'gzip')

    if not output_path:
        raise ValidationError("Missing required parameter: output_path", field="output_path")
    if not files:
        raise ValidationError("Missing required parameter: files", field="files")
    if not isinstance(files, list):
        raise ValidationError("Parameter 'files' must be a list", field="files")

    # Validate output path
    try:
        safe_output = validate_path_with_env_config(output_path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    # Ensure output directory exists
    parent_dir = os.path.dirname(safe_output)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    mode = _COMPRESSION_MODES.get(compression, 'w:gz')
    file_count = 0

    try:
        with tarfile.open(safe_output, mode) as tf:
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
                tf.add(safe_file, arcname=arcname)
                file_count += 1
    except ModuleError:
        raise
    except Exception as e:
        raise ModuleError("Failed to create TAR archive: {}".format(str(e)))

    archive_size = os.path.getsize(safe_output)

    return {
        'ok': True,
        'data': {
            'path': safe_output,
            'size': archive_size,
            'file_count': file_count,
        },
    }
