# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
TAR Extract Module
Extract files from a TAR archive (auto-detects compression).
"""
import logging
import os
import tarfile
from typing import Any, Dict

from ....utils import PathTraversalError, validate_path_with_env_config
from ...errors import ModuleError, ValidationError
from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


@register_module(
    module_id='archive.tar_extract',
    version='1.0.0',
    category='archive',
    tags=['archive', 'tar', 'extract', 'decompress', 'untar'],
    label='Extract TAR Archive',
    label_key='modules.archive.tar_extract.label',
    description='Extract files from a TAR archive (auto-detects compression)',
    description_key='modules.archive.tar_extract.description',
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
            'archive_path',
            type='string',
            label='Archive Path',
            label_key='modules.archive.tar_extract.params.archive_path.label',
            description='Path to the TAR archive to extract',
            description_key='modules.archive.tar_extract.params.archive_path.description',
            required=True,
            placeholder='/tmp/archive.tar.gz',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'output_dir',
            type='string',
            label='Output Directory',
            label_key='modules.archive.tar_extract.params.output_dir.label',
            description='Directory to extract files into',
            description_key='modules.archive.tar_extract.params.output_dir.description',
            required=True,
            placeholder='/tmp/extracted/',
            group=FieldGroup.BASIC,
            format='path',
        ),
    ),
    output_schema={
        'extracted_files': {
            'type': 'array',
            'description': 'List of extracted file paths',
            'description_key': 'modules.archive.tar_extract.output.extracted_files.description',
        },
        'total_size': {
            'type': 'number',
            'description': 'Total size of extracted files in bytes',
            'description_key': 'modules.archive.tar_extract.output.total_size.description',
        },
    },
    examples=[
        {
            'title': 'Extract TAR.GZ archive',
            'title_key': 'modules.archive.tar_extract.examples.basic.title',
            'params': {
                'archive_path': '/tmp/archive.tar.gz',
                'output_dir': '/tmp/extracted/',
            },
        }
    ],
)
async def archive_tar_extract(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract files from a TAR archive."""
    params = context['params']
    archive_path = params.get('archive_path')
    output_dir = params.get('output_dir')

    if not archive_path:
        raise ValidationError("Missing required parameter: archive_path", field="archive_path")
    if not output_dir:
        raise ValidationError("Missing required parameter: output_dir", field="output_dir")

    # Validate paths
    try:
        safe_archive = validate_path_with_env_config(archive_path)
        safe_output = validate_path_with_env_config(output_dir)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    if not os.path.exists(safe_archive):
        raise ModuleError(
            "Archive not found: {}".format(archive_path),
            code="FILE_NOT_FOUND",
        )

    # Ensure output directory exists
    os.makedirs(safe_output, exist_ok=True)

    extracted_files = []
    total_size = 0

    try:
        # Auto-detect compression via 'r:*'
        with tarfile.open(safe_archive, 'r:*') as tf:
            base = os.path.realpath(safe_output)
            for member in tf.getmembers():
                # Security: reject symlink/hardlink/special members outright.
                # This is version-independent and closes the Tar Slip where a
                # symlink member points outside the sandbox and a following
                # regular member is written *through* it. Without this, the
                # extractall fallback on Python < 3.12 (no filter= support)
                # follows the symlink and escapes safe_output.
                if member.issym() or member.islnk() or not (
                    member.isfile() or member.isdir()
                ):
                    raise ModuleError(
                        "Tar entry with link/special type is not allowed: {}".format(
                            member.name
                        ),
                        code="PATH_TRAVERSAL",
                    )
                # Security: resolve the destination and require it to stay within
                # safe_output using an os.sep boundary (a lexical startswith would
                # accept e.g. /tmp/out_evil for a /tmp/out sandbox).
                resolved = os.path.realpath(os.path.join(safe_output, member.name))
                if not (resolved == base or resolved.startswith(base + os.sep)):
                    raise ModuleError(
                        "Tar entry attempts path traversal: {}".format(member.name),
                        code="PATH_TRAVERSAL",
                    )

            # Use data_filter if available (Python 3.12+); on older runtimes the
            # fallback is now safe because link/special members are rejected above.
            try:
                tf.extractall(path=safe_output, filter='data')
            except TypeError:
                # Python < 3.12 does not support filter parameter
                tf.extractall(path=safe_output)

            for member in tf.getmembers():
                if member.isfile():
                    full_path = os.path.join(safe_output, member.name)
                    extracted_files.append(full_path)
                    total_size += member.size
    except ModuleError:
        raise
    except tarfile.TarError as e:
        raise ModuleError("Invalid or corrupted TAR file: {}".format(str(e)))
    except (OSError, PermissionError) as e:
        raise ModuleError("Failed to extract TAR archive: {}".format(str(e)))

    return {
        'ok': True,
        'data': {
            'extracted_files': extracted_files,
            'total_size': total_size,
        },
    }
