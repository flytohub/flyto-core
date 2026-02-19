"""
Gunzip Decompress Module
Decompress a gzip-compressed file.
"""
import gzip as gzip_lib
import logging
import os
import shutil
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError
from ....utils import validate_path_with_env_config, PathTraversalError

logger = logging.getLogger(__name__)


@register_module(
    module_id='archive.gunzip',
    version='1.0.0',
    category='archive',
    tags=['archive', 'gzip', 'decompress', 'gunzip', 'gz'],
    label='Gunzip Decompress',
    label_key='modules.archive.gunzip.label',
    description='Decompress a gzip-compressed file',
    description_key='modules.archive.gunzip.description',
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
            'input_path',
            type='string',
            label='Input Path',
            label_key='modules.archive.gunzip.params.input_path.label',
            description='Path to the gzip-compressed file',
            description_key='modules.archive.gunzip.params.input_path.description',
            required=True,
            placeholder='/tmp/data.txt.gz',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'output_path',
            type='string',
            label='Output Path',
            label_key='modules.archive.gunzip.params.output_path.label',
            description='Path for the decompressed file (defaults to input without .gz extension)',
            description_key='modules.archive.gunzip.params.output_path.description',
            group=FieldGroup.OPTIONS,
            format='path',
        ),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Path to the decompressed file',
            'description_key': 'modules.archive.gunzip.output.path.description',
        },
        'size': {
            'type': 'number',
            'description': 'Decompressed file size in bytes',
            'description_key': 'modules.archive.gunzip.output.size.description',
        },
    },
    examples=[
        {
            'title': 'Decompress a gzip file',
            'title_key': 'modules.archive.gunzip.examples.basic.title',
            'params': {
                'input_path': '/tmp/data.txt.gz',
            },
        }
    ],
)
async def archive_gunzip(context: Dict[str, Any]) -> Dict[str, Any]:
    """Decompress a gzip-compressed file."""
    params = context['params']
    input_path = params.get('input_path')
    output_path = params.get('output_path')

    if not input_path:
        raise ValidationError("Missing required parameter: input_path", field="input_path")

    # Validate input path
    try:
        safe_input = validate_path_with_env_config(input_path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    if not os.path.exists(safe_input):
        raise ModuleError(
            "File not found: {}".format(input_path),
            code="FILE_NOT_FOUND",
        )

    # Determine output path
    if output_path:
        try:
            safe_output = validate_path_with_env_config(output_path)
        except PathTraversalError as e:
            raise ModuleError(str(e), code="PATH_TRAVERSAL")
    else:
        # Strip .gz extension if present, otherwise append .decompressed
        if safe_input.endswith('.gz'):
            safe_output = safe_input[:-3]
        else:
            safe_output = safe_input + '.decompressed'

    # Ensure output directory exists
    parent_dir = os.path.dirname(safe_output)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    try:
        with gzip_lib.open(safe_input, 'rb') as f_in:
            with open(safe_output, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    except gzip_lib.BadGzipFile:
        raise ModuleError("Invalid or corrupted gzip file: {}".format(input_path))
    except Exception as e:
        raise ModuleError("Failed to decompress gzip file: {}".format(str(e)))

    size = os.path.getsize(safe_output)

    return {
        'ok': True,
        'data': {
            'path': safe_output,
            'size': size,
        },
    }
