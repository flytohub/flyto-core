"""
ZIP Extract Module
Extract files from a ZIP archive.
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


@register_module(
    module_id='archive.zip_extract',
    version='1.0.0',
    category='archive',
    tags=['archive', 'zip', 'extract', 'decompress', 'unzip'],
    label='Extract ZIP Archive',
    label_key='modules.archive.zip_extract.label',
    description='Extract files from a ZIP archive',
    description_key='modules.archive.zip_extract.description',
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
            label_key='modules.archive.zip_extract.params.archive_path.label',
            description='Path to the ZIP archive to extract',
            description_key='modules.archive.zip_extract.params.archive_path.description',
            required=True,
            placeholder='/tmp/archive.zip',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'output_dir',
            type='string',
            label='Output Directory',
            label_key='modules.archive.zip_extract.params.output_dir.label',
            description='Directory to extract files into',
            description_key='modules.archive.zip_extract.params.output_dir.description',
            required=True,
            placeholder='/tmp/extracted/',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'password',
            type='string',
            label='Password',
            label_key='modules.archive.zip_extract.params.password.label',
            description='Password for encrypted archives',
            description_key='modules.archive.zip_extract.params.password.description',
            group=FieldGroup.OPTIONS,
            format='password',
        ),
    ),
    output_schema={
        'extracted_files': {
            'type': 'array',
            'description': 'List of extracted file paths',
            'description_key': 'modules.archive.zip_extract.output.extracted_files.description',
        },
        'total_size': {
            'type': 'number',
            'description': 'Total size of extracted files in bytes',
            'description_key': 'modules.archive.zip_extract.output.total_size.description',
        },
    },
    examples=[
        {
            'title': 'Extract ZIP archive',
            'title_key': 'modules.archive.zip_extract.examples.basic.title',
            'params': {
                'archive_path': '/tmp/archive.zip',
                'output_dir': '/tmp/extracted/',
            },
        }
    ],
)
async def archive_zip_extract(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract files from a ZIP archive."""
    params = context['params']
    archive_path = params.get('archive_path')
    output_dir = params.get('output_dir')
    password = params.get('password')

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

    pwd = password.encode('utf-8') if password else None
    extracted_files = []
    total_size = 0

    try:
        with zipfile.ZipFile(safe_archive, 'r') as zf:
            # Security: check for path traversal in archive entries (zip slip)
            for info in zf.infolist():
                target_path = os.path.normpath(os.path.join(safe_output, info.filename))
                if not target_path.startswith(os.path.normpath(safe_output)):
                    raise ModuleError(
                        "Zip entry attempts path traversal: {}".format(info.filename),
                        code="PATH_TRAVERSAL",
                    )

            zf.extractall(path=safe_output, pwd=pwd)

            for info in zf.infolist():
                if not info.is_dir():
                    full_path = os.path.join(safe_output, info.filename)
                    extracted_files.append(full_path)
                    total_size += info.file_size
    except ModuleError:
        raise
    except zipfile.BadZipFile:
        raise ModuleError("Invalid or corrupted ZIP file: {}".format(archive_path))
    except RuntimeError as e:
        # zipfile raises RuntimeError for password-related issues
        raise ModuleError("Failed to extract ZIP: {}".format(str(e)))
    except Exception as e:
        raise ModuleError("Failed to extract ZIP archive: {}".format(str(e)))

    return {
        'ok': True,
        'data': {
            'extracted_files': extracted_files,
            'total_size': total_size,
        },
    }
