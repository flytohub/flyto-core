"""
File Edit Module
Targeted string replacement in files (not full overwrite).
"""

from typing import Any, Dict
from ...registry import register_module
from ...schema import compose, field, presets
from ....utils import validate_path_with_env_config, PathTraversalError
from ...errors import ValidationError, FileNotFoundError, ModuleError
import os


@register_module(
    module_id='file.edit',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'edit', 'replace', 'atomic', 'path_restricted'],
    label='Edit File',
    label_key='modules.file.edit.label',
    description='Replace a string in a file (targeted edit, not full overwrite)',
    description_key='modules.file.edit.description',
    icon='FileEdit',
    color='#3B82F6',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],
    timeout_ms=30000,
    retryable=False,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.write'],

    params_schema=compose(
        presets.FILE_PATH(key='path', required=True, placeholder='/path/to/file.txt'),
        field('old_string', type='string', label='Old String', required=True, format='multiline',
              description='Text to find and replace',
              placeholder='Enter Old String...'),
        field('new_string', type='string', label='New String', required=True, format='multiline',
              description='Replacement text',
              placeholder='Enter New String...'),
        field('replace_all', type='boolean', label='Replace All', default=False,
              description='Whether to replace all occurrences'),
        presets.ENCODING(default='utf-8'),
    ),
    output_schema={
        'path': {
            'type': 'string',
            'description': 'File path that was edited',
            'description_key': 'modules.file.edit.output.path.description',
        },
        'replacements': {
            'type': 'number',
            'description': 'Number of replacements made',
            'description_key': 'modules.file.edit.output.replacements.description',
        },
        'diff': {
            'type': 'string',
            'description': 'Unified diff of changes',
            'description_key': 'modules.file.edit.output.diff.description',
        },
    },
    examples=[
        {
            'title': 'Replace string in file',
            'title_key': 'modules.file.edit.examples.replace.title',
            'params': {
                'path': '/tmp/example.py',
                'old_string': 'def hello():',
                'new_string': 'def hello_world():',
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
)
async def file_edit(context):
    """Replace string in file (targeted edit, not full overwrite)."""
    import difflib

    params = context['params']
    path = params['path']
    old_string = params['old_string']
    new_string = params['new_string']
    replace_all = params.get('replace_all', False)
    encoding = params.get('encoding', 'utf-8')

    # SECURITY: Validate path to prevent path traversal attacks
    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    if not os.path.exists(safe_path):
        raise FileNotFoundError("File not found: {}".format(path), path=path)

    with open(safe_path, 'r', encoding=encoding) as f:
        original = f.read()

    if old_string not in original:
        return {'ok': False, 'error': 'old_string not found in {}'.format(path)}

    if replace_all:
        modified = original.replace(old_string, new_string)
        count = original.count(old_string)
    else:
        modified = original.replace(old_string, new_string, 1)
        count = 1

    with open(safe_path, 'w', encoding=encoding) as f:
        f.write(modified)

    # Generate diff
    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile="a/{}".format(os.path.basename(path)),
        tofile="b/{}".format(os.path.basename(path)),
        n=3,
    ))

    return {
        'ok': True,
        'data': {
            'path': path,
            'replacements': count,
            'diff': ''.join(diff_lines),
        }
    }
