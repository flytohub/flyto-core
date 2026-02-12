"""
File Diff Module
Generate unified diff between original and modified content.
"""

from typing import Any, Dict
from ...registry import register_module
from ...schema import compose, field


@register_module(
    module_id='file.diff',
    version='1.0.0',
    category='atomic',
    subcategory='file',
    tags=['file', 'diff', 'compare', 'atomic'],
    label='Diff Content',
    label_key='modules.file.diff.label',
    description='Generate unified diff between original and modified content',
    description_key='modules.file.diff.description',
    icon='FileDiff',
    color='#F59E0B',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],
    timeout_ms=10000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,

    params_schema=compose(
        field('original', type='string', label='Original Content', required=True, format='multiline',
              description='Original content for comparison',
              placeholder='Enter Original...'),
        field('modified', type='string', label='Modified Content', required=True, format='multiline',
              description='Modified content for comparison',
              placeholder='Enter Modified...'),
        field('context_lines', type='number', label='Context Lines', default=3,
              description='Number of context lines around changes'),
        field('filename', type='string', label='Filename', default='file',
              description='Name of the file',
              placeholder='my-name'),
    ),
    output_schema={
        'diff': {
            'type': 'string',
            'description': 'Unified diff output',
            'description_key': 'modules.file.diff.output.diff.description',
        },
        'changed': {
            'type': 'boolean',
            'description': 'Whether content differs',
            'description_key': 'modules.file.diff.output.changed.description',
        },
        'additions': {
            'type': 'number',
            'description': 'Number of added lines',
            'description_key': 'modules.file.diff.output.additions.description',
        },
        'deletions': {
            'type': 'number',
            'description': 'Number of deleted lines',
            'description_key': 'modules.file.diff.output.deletions.description',
        },
    },
    examples=[
        {
            'title': 'Diff two strings',
            'title_key': 'modules.file.diff.examples.basic.title',
            'params': {
                'original': 'hello\nworld',
                'modified': 'hello\nworld!',
                'filename': 'test.txt',
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
)
async def file_diff(context):
    """Generate unified diff between original and modified content."""
    import difflib

    params = context['params']
    original = params['original']
    modified = params['modified']
    context_lines = params.get('context_lines', 3)
    filename = params.get('filename', 'file')

    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile="a/{}".format(filename),
        tofile="b/{}".format(filename),
        n=context_lines,
    ))

    additions = sum(1 for l in diff if l.startswith('+') and not l.startswith('+++'))
    deletions = sum(1 for l in diff if l.startswith('-') and not l.startswith('---'))

    return {
        'ok': True,
        'data': {
            'diff': ''.join(diff),
            'changed': len(diff) > 0,
            'additions': additions,
            'deletions': deletions,
        }
    }
