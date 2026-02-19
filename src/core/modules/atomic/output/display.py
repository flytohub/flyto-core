# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Output Display Module
Display output content (images, PDFs, text, HTML) in the result panel.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


def _detect_type(content: str) -> str:
    """Auto-detect display type from content."""
    if not isinstance(content, str):
        return 'text'
    if content.startswith('data:image/'):
        return 'image'
    if content.startswith('data:application/pdf'):
        return 'pdf'
    if content.strip().startswith(('<html', '<div', '<p', '<table', '<ul', '<ol')):
        return 'html'
    return 'text'


@register_module(
    module_id='output.display',
    version='1.0.0',
    category='output',
    subcategory='display',
    tags=['output', 'display', 'result', 'image', 'pdf', 'text', 'html'],
    label='Display Output',
    label_key='modules.output.display.label',
    description='Display content (images, PDFs, text, HTML) in the result panel after execution',
    description_key='modules.output.display.description',
    icon='Monitor',
    color='#6366F1',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'type': 'object',
        'properties': {
            'type': {
                'type': 'string',
                'enum': ['auto', 'image', 'pdf', 'text', 'html', 'file'],
                'default': 'auto',
                'description': 'Display type (auto-detected if not specified)',
                'description_key': 'modules.output.display.params.type.description',
                'x-ui': {'component': 'select'},
            },
            'content': {
                'type': 'string',
                'description': 'Content to display (data URI, text, or HTML)',
                'description_key': 'modules.output.display.params.content.description',
                'x-ui': {'component': 'textarea'},
            },
            'title': {
                'type': 'string',
                'default': '',
                'description': 'Optional title for the display item',
                'description_key': 'modules.output.display.params.title.description',
            },
        },
        'required': ['content'],
    },
    output_schema={
        'type': {
            'type': 'string',
            'description': 'Resolved display type',
        },
        'title': {
            'type': 'string',
            'description': 'Display title',
        },
        'content': {
            'type': 'string',
            'description': 'Display content',
        },
    },
    examples=[
        {
            'title': 'Display an image',
            'title_key': 'modules.output.display.examples.image.title',
            'params': {
                'type': 'image',
                'content': 'data:image/png;base64,...',
                'title': 'Generated Image',
            },
        },
        {
            'title': 'Display text',
            'title_key': 'modules.output.display.examples.text.title',
            'params': {
                'type': 'text',
                'content': 'Hello World',
                'title': 'Result',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def output_display(context: Dict[str, Any]) -> Dict[str, Any]:
    """Display content in the result panel."""
    params = context['params']
    content = params.get('content', '')
    display_type = params.get('type', 'auto')
    title = params.get('title', '')

    if display_type == 'auto':
        display_type = _detect_type(content)

    # For image/pdf types, content should be a data URI
    if display_type == 'image' and not content.startswith('data:'):
        data_uri = f'data:image/png;base64,{content}'
    elif display_type == 'pdf' and not content.startswith('data:'):
        data_uri = f'data:application/pdf;base64,{content}'
    else:
        data_uri = content

    logger.info(f"Display output: type={display_type}, title={title!r}")

    return {
        'ok': True,
        '__display__': True,
        'type': display_type,
        'title': title or display_type.capitalize(),
        'content': content,
        'data_uri': data_uri,
    }
