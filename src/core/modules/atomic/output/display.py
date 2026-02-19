# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Output Display Module
Universal inspect/display/IO node:
- Debug inspector (like console.log) — place anywhere to see data
- Display output — type-aware rendering (image/text/json/html/pdf/file)
- Workflow I/O — use as output (template composition) or input receiver
"""
import json
import logging
from typing import Any, Dict, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


def _detect_type(content: Any) -> str:
    """Auto-detect display type from content."""
    if isinstance(content, (dict, list)):
        return 'json'

    if not isinstance(content, str):
        return 'text'

    if content.startswith('data:image/'):
        return 'image'
    if content.startswith('data:application/pdf'):
        return 'pdf'

    stripped = content.strip()
    if stripped.startswith(('<html', '<div', '<p', '<table', '<ul', '<ol')):
        return 'html'

    # Try JSON detection
    if stripped and stripped[0] in ('{', '['):
        try:
            json.loads(stripped)
            return 'json'
        except (json.JSONDecodeError, ValueError):
            pass

    return 'text'


def _validate_content(content: Any, display_type: str) -> Optional[str]:
    """Validate content matches the declared type. Returns warning or None."""
    if display_type == 'image':
        if isinstance(content, str):
            if content.startswith('data:image/'):
                return None
            # Might be raw base64 — check if long enough
            if len(content) > 100:
                return None
            return 'Content does not appear to be a valid image (expected data URI or base64)'
        return 'Image content should be a string (data URI or base64)'

    if display_type == 'json':
        if isinstance(content, (dict, list)):
            return None
        if isinstance(content, str):
            try:
                json.loads(content)
                return None
            except (json.JSONDecodeError, ValueError):
                return 'Content is not valid JSON'
        return 'JSON content should be a dict, list, or JSON string'

    return None


def _format_json(content: Any) -> Any:
    """Normalize content for JSON display."""
    if isinstance(content, (dict, list)):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return content
    return content


@register_module(
    module_id='output.display',
    version='2.0.0',
    category='output',
    subcategory='display',
    tags=['output', 'display', 'result', 'image', 'pdf', 'text', 'html', 'json', 'debug', 'inspect'],
    label='Display Output',
    label_key='modules.output.display.label',
    description='Universal inspect/display/IO node — debug data, render output, or define workflow I/O',
    description_key='modules.output.display.description',
    icon='Monitor',
    color='#6366F1',

    input_types=['any'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=5000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        presets.DISPLAY_TYPE(),
        presets.DISPLAY_CONTENT(),
        presets.DISPLAY_TITLE(),
        presets.DISPLAY_MODE(),
        presets.DISPLAY_OUTPUT_KEY(),
    ),
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
            'type': ['string', 'object', 'array'],
            'description': 'Display content',
        },
        'mode': {
            'type': 'string',
            'description': 'Node mode (display/output/input)',
        },
        'validation_warning': {
            'type': 'string',
            'description': 'Content validation warning (if any)',
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
        {
            'title': 'Display JSON data',
            'title_key': 'modules.output.display.examples.json.title',
            'params': {
                'type': 'json',
                'content': '{"name": "test", "value": 42}',
                'title': 'API Response',
            },
        },
        {
            'title': 'Workflow output',
            'title_key': 'modules.output.display.examples.output.title',
            'params': {
                'type': 'auto',
                'content': '${step.output}',
                'mode': 'output',
                'output_key': 'result',
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
    mode = params.get('mode', 'display')
    output_key = params.get('output_key', 'result')

    # Auto-detect type
    if display_type == 'auto':
        display_type = _detect_type(content)

    # Validate content
    validation_warning = _validate_content(content, display_type) or ''

    # Format JSON content
    if display_type == 'json':
        content = _format_json(content)

    # Build data_uri for image/pdf types
    data_uri = ''
    if display_type == 'image':
        if isinstance(content, str):
            if content.startswith('data:'):
                data_uri = content
            else:
                data_uri = f'data:image/png;base64,{content}'
    elif display_type == 'pdf':
        if isinstance(content, str):
            if content.startswith('data:'):
                data_uri = content
            else:
                data_uri = f'data:application/pdf;base64,{content}'

    logger.info(f"Display output: type={display_type}, mode={mode}, title={title!r}")

    result = {
        'ok': True,
        '__display__': True,
        'type': display_type,
        'title': title or display_type.capitalize(),
        'content': content,
        'data_uri': data_uri,
        'mode': mode,
        'validation_warning': validation_warning,
    }

    # Workflow output mode
    if mode == 'output':
        result['__workflow_output__'] = True
        result['__output_key__'] = output_key

    return result
