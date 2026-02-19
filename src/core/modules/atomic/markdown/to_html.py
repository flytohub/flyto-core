# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Markdown to HTML Module
Convert Markdown text to HTML.
Uses the `markdown` library if available, otherwise falls back to basic regex conversion.
"""
import logging
import re
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


def _basic_markdown_to_html(text: str) -> str:
    """
    Basic Markdown to HTML conversion using regex.
    Handles: headers, bold, italic, code blocks, inline code, links, unordered lists, paragraphs.
    """
    html = text

    # Fenced code blocks (``` ... ```) - process first to protect content
    code_blocks = []

    def _store_code_block(match):
        lang = match.group(1) or ''
        code = match.group(2)
        # Escape HTML inside code blocks
        code = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        idx = len(code_blocks)
        if lang:
            placeholder = '<!--CODE_BLOCK_{}-->'.format(idx)
            code_blocks.append('<pre><code class="language-{}">{}</code></pre>'.format(lang, code))
        else:
            placeholder = '<!--CODE_BLOCK_{}-->'.format(idx)
            code_blocks.append('<pre><code>{}</code></pre>'.format(code))
        return placeholder

    html = re.sub(r'```(\w*)\n(.*?)```', _store_code_block, html, flags=re.DOTALL)

    # Inline code
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

    # Headers (h1 through h6)
    html = re.sub(r'^######\s+(.+)$', r'<h6>\1</h6>', html, flags=re.MULTILINE)
    html = re.sub(r'^#####\s+(.+)$', r'<h5>\1</h5>', html, flags=re.MULTILINE)
    html = re.sub(r'^####\s+(.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^##\s+(.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^#\s+(.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

    # Bold and italic (order matters: bold first)
    html = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', html)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # Links: [text](url)
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

    # Images: ![alt](url)
    html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" />', html)

    # Horizontal rules
    html = re.sub(r'^---+$', '<hr />', html, flags=re.MULTILINE)

    # Unordered lists (lines starting with - or *)
    lines = html.split('\n')
    result_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        is_list_item = bool(re.match(r'^[-*]\s+', stripped))
        if is_list_item:
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            item_text = re.sub(r'^[-*]\s+', '', stripped)
            result_lines.append('<li>{}</li>'.format(item_text))
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            result_lines.append(line)
    if in_list:
        result_lines.append('</ul>')
    html = '\n'.join(result_lines)

    # Wrap loose text in paragraphs (lines not already wrapped in HTML tags)
    paragraphs = html.split('\n\n')
    processed = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # Skip if already an HTML block element
        if re.match(r'^<(h[1-6]|ul|ol|li|pre|hr|blockquote|div|table|p)', para):
            processed.append(para)
        elif para.startswith('<!--CODE_BLOCK_'):
            processed.append(para)
        else:
            processed.append('<p>{}</p>'.format(para))
    html = '\n'.join(processed)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        html = html.replace('<!--CODE_BLOCK_{}-->'.format(i), block)

    return html


@register_module(
    module_id='markdown.to_html',
    version='1.0.0',
    category='markdown',
    tags=['markdown', 'html', 'convert', 'render', 'text'],
    label='Markdown to HTML',
    label_key='modules.markdown.to_html.label',
    description='Convert Markdown text to HTML',
    description_key='modules.markdown.to_html.description',
    icon='FileText',
    color='#6B7280',

    input_types=['string'],
    output_types=['string'],

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
            label_key='modules.markdown.to_html.params.text.label',
            description='Markdown content to convert',
            description_key='modules.markdown.to_html.params.text.description',
            required=True,
            placeholder='# Hello World',
            group=FieldGroup.BASIC,
            format='multiline',
        ),
        field(
            'extensions',
            type='array',
            label='Extensions',
            label_key='modules.markdown.to_html.params.extensions.label',
            description='Markdown extensions to enable (only used with the markdown library)',
            description_key='modules.markdown.to_html.params.extensions.description',
            group=FieldGroup.OPTIONS,
            items={'type': 'string'},
        ),
    ),
    output_schema={
        'html': {
            'type': 'string',
            'description': 'Converted HTML content',
            'description_key': 'modules.markdown.to_html.output.html.description',
        },
        'word_count': {
            'type': 'number',
            'description': 'Word count of the input text',
            'description_key': 'modules.markdown.to_html.output.word_count.description',
        },
    },
    examples=[
        {
            'title': 'Convert markdown to HTML',
            'title_key': 'modules.markdown.to_html.examples.basic.title',
            'params': {
                'text': '# Hello\n\nThis is **bold** and *italic*.',
            },
        }
    ],
)
async def markdown_to_html(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Markdown text to HTML."""
    params = context['params']
    text = params.get('text')
    extensions = params.get('extensions') or []

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    # Count words (strip markdown syntax for a rough count)
    plain = re.sub(r'[#*`\[\]\(\)!]', '', text)
    words = plain.split()
    word_count = len(words)

    # Try the markdown library first, fall back to basic regex
    html = None
    try:
        import markdown as md_lib
        ext_list = []
        ext_map = {
            'tables': 'tables',
            'fenced_code': 'fenced_code',
            'footnotes': 'footnotes',
            'toc': 'toc',
            'codehilite': 'codehilite',
        }
        for ext in extensions:
            mapped = ext_map.get(ext, ext)
            ext_list.append(mapped)
        html = md_lib.markdown(text, extensions=ext_list)
    except ImportError:
        logger.debug("markdown library not available, using basic regex conversion")
    except Exception as e:
        logger.warning("markdown library failed, falling back to regex: %s", str(e))

    if html is None:
        html = _basic_markdown_to_html(text)

    return {
        'ok': True,
        'data': {
            'html': html,
            'word_count': word_count,
        },
    }
