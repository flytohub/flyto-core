# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Gzip Compress Module
Compress a single file using gzip.
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
    module_id='archive.gzip',
    version='1.0.0',
    category='archive',
    tags=['archive', 'gzip', 'compress', 'gz'],
    label='Gzip Compress',
    label_key='modules.archive.gzip.label',
    description='Compress a single file using gzip',
    description_key='modules.archive.gzip.description',
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
            label_key='modules.archive.gzip.params.input_path.label',
            description='Path to the file to compress',
            description_key='modules.archive.gzip.params.input_path.description',
            required=True,
            placeholder='/tmp/data.txt',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'output_path',
            type='string',
            label='Output Path',
            label_key='modules.archive.gzip.params.output_path.label',
            description='Path for the compressed file (defaults to input_path + .gz)',
            description_key='modules.archive.gzip.params.output_path.description',
            group=FieldGroup.OPTIONS,
            format='path',
        ),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'Path to the compressed file',
            'description_key': 'modules.archive.gzip.output.path.description',
        },
        'original_size': {
            'type': 'number',
            'description': 'Original file size in bytes',
            'description_key': 'modules.archive.gzip.output.original_size.description',
        },
        'compressed_size': {
            'type': 'number',
            'description': 'Compressed file size in bytes',
            'description_key': 'modules.archive.gzip.output.compressed_size.description',
        },
        'ratio': {
            'type': 'number',
            'description': 'Compression ratio (compressed / original)',
            'description_key': 'modules.archive.gzip.output.ratio.description',
        },
    },
    examples=[
        {
            'title': 'Compress a file with gzip',
            'title_key': 'modules.archive.gzip.examples.basic.title',
            'params': {
                'input_path': '/tmp/data.txt',
            },
        }
    ],
)
async def archive_gzip(context: Dict[str, Any]) -> Dict[str, Any]:
    """Compress a single file using gzip."""
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

    if not os.path.isfile(safe_input):
        raise ModuleError(
            "Path is not a file: {}".format(input_path),
            code="INVALID_PARAM_VALUE",
        )

    # Determine output path
    if output_path:
        try:
            safe_output = validate_path_with_env_config(output_path)
        except PathTraversalError as e:
            raise ModuleError(str(e), code="PATH_TRAVERSAL")
    else:
        safe_output = safe_input + '.gz'

    # Ensure output directory exists
    parent_dir = os.path.dirname(safe_output)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    original_size = os.path.getsize(safe_input)

    try:
        with open(safe_input, 'rb') as f_in:
            with gzip_lib.open(safe_output, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    except Exception as e:
        raise ModuleError("Failed to gzip compress: {}".format(str(e)))

    compressed_size = os.path.getsize(safe_output)
    ratio = compressed_size / original_size if original_size > 0 else 0.0

    return {
        'ok': True,
        'data': {
            'path': safe_output,
            'original_size': original_size,
            'compressed_size': compressed_size,
            'ratio': round(ratio, 4),
        },
    }
