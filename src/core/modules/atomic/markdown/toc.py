# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Markdown Table of Contents Module
Generate a table of contents from Markdown headings.
"""
import logging
import re
from typing import Any, Dict, List

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """
    Convert heading text to a URL-friendly slug.
    Matches GitHub-style heading anchors.
    """
    slug = text.lower()
    # Remove markdown formatting
    slug = re.sub(r'[*_`\[\]()]', '', slug)
    # Replace spaces and non-alphanumeric with hyphens
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    return slug


def _extract_headings(text: str, max_depth: int) -> List[Dict[str, Any]]:
    """
    Extract headings from Markdown text.
    Returns a list of dicts with level, title, and slug.
    """
    headings = []

    # Match ATX-style headings: # Title, ## Title, etc.
    # Skip lines inside code blocks
    in_code_block = False

    for line in text.splitlines():
        stripped = line.strip()

        # Track fenced code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if match:
            level = len(match.group(1))
            if level <= max_depth:
                title = match.group(2).strip()
                # Remove trailing # characters (closing ATX style)
                title = re.sub(r'\s+#+\s*$', '', title)
                slug = _slugify(title)
                headings.append({
                    'level': level,
                    'title': title,
                    'slug': slug,
                })

    return headings


def _format_toc_markdown(headings: List[Dict[str, Any]]) -> str:
    """
    Format headings into a Markdown table of contents.
    Uses indentation based on heading level.
    """
    if not headings:
        return ''

    # Find the minimum level to normalize indentation
    min_level = min(h['level'] for h in headings)
    lines = []

    for heading in headings:
        indent = '  ' * (heading['level'] - min_level)
        line = '{}- [{}](#{})'.format(indent, heading['title'], heading['slug'])
        lines.append(line)

    return '\n'.join(lines)


@register_module(
    module_id='markdown.toc',
    version='1.0.0',
    category='markdown',
    tags=['markdown', 'toc', 'table-of-contents', 'headings', 'navigation'],
    label='Generate Table of Contents',
    label_key='modules.markdown.toc.label',
    description='Generate a table of contents from Markdown headings',
    description_key='modules.markdown.toc.description',
    icon='FileText',
    color='#6B7280',

    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=10000,
    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'text',
            type='text',
            label='Markdown Text',
            label_key='modules.markdown.toc.params.text.label',
            description='Markdown content to extract headings from',
            description_key='modules.markdown.toc.params.text.description',
            required=True,
            placeholder='# Title\n## Section 1\n## Section 2',
            group=FieldGroup.BASIC,
            format='multiline',
        ),
        field(
            'max_depth',
            type='number',
            label='Max Depth',
            label_key='modules.markdown.toc.params.max_depth.label',
            description='Maximum heading depth to include (1-6)',
            description_key='modules.markdown.toc.params.max_depth.description',
            default=3,
            group=FieldGroup.OPTIONS,
            min=1,
            max=6,
            step=1,
        ),
    ),
    output_schema={
        'toc': {
            'type': 'array',
            'description': 'List of headings with level, title, and slug',
            'description_key': 'modules.markdown.toc.output.toc.description',
        },
        'toc_markdown': {
            'type': 'string',
            'description': 'Formatted Markdown table of contents',
            'description_key': 'modules.markdown.toc.output.toc_markdown.description',
        },
    },
    examples=[
        {
            'title': 'Generate TOC from markdown',
            'title_key': 'modules.markdown.toc.examples.basic.title',
            'params': {
                'text': '# Introduction\n\n## Getting Started\n\n### Installation\n\n### Configuration\n\n## Usage\n\n## API Reference',
                'max_depth': 3,
            },
        }
    ],
)
async def markdown_toc(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a table of contents from Markdown headings."""
    params = context['params']
    text = params.get('text')
    max_depth = params.get('max_depth', 3)

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)
    max_depth = int(max_depth)

    if max_depth < 1 or max_depth > 6:
        raise ValidationError(
            "max_depth must be between 1 and 6",
            field="max_depth",
        )

    headings = _extract_headings(text, max_depth)
    toc_markdown = _format_toc_markdown(headings)

    return {
        'ok': True,
        'data': {
            'toc': headings,
            'toc_markdown': toc_markdown,
        },
    }
