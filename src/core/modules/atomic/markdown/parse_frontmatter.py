"""
Markdown Parse Frontmatter Module
Extract YAML frontmatter from Markdown content.
Uses `yaml.safe_load` if available, otherwise falls back to basic key: value parsing.
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


def _basic_yaml_parse(text: str) -> Dict[str, Any]:
    """
    Basic YAML-like parser for simple key: value frontmatter.
    Handles strings, numbers, booleans, and simple lists.
    Does NOT handle nested objects or complex YAML features.
    """
    result = {}

    current_key = None
    current_list = None

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            continue

        # Check for list item (continuation of previous key)
        if stripped.startswith('- ') and current_key is not None:
            item = stripped[2:].strip()
            if current_list is None:
                current_list = []
            current_list.append(_parse_value(item))
            result[current_key] = current_list
            continue

        # Reset list tracking
        if current_list is not None:
            current_list = None

        # Key: value pair
        if ':' in stripped:
            colon_idx = stripped.index(':')
            key = stripped[:colon_idx].strip()
            raw_value = stripped[colon_idx + 1:].strip()

            current_key = key

            if not raw_value:
                # Value might be a list on subsequent lines
                result[key] = None
                current_list = []
                continue

            result[key] = _parse_value(raw_value)
            current_list = None

    return result


def _parse_value(raw: str) -> Any:
    """Parse a raw string value into an appropriate Python type."""
    # Strip quotes
    if len(raw) >= 2:
        if (raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'"):
            return raw[1:-1]

    # Booleans
    lower = raw.lower()
    if lower in ('true', 'yes', 'on'):
        return True
    if lower in ('false', 'no', 'off'):
        return False

    # Null
    if lower in ('null', 'none', '~'):
        return None

    # Numbers
    try:
        if '.' in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass

    # Inline list: [a, b, c]
    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1]
        if not inner.strip():
            return []
        items = [_parse_value(item.strip()) for item in inner.split(',')]
        return items

    return raw


@register_module(
    module_id='markdown.parse_frontmatter',
    version='1.0.0',
    category='markdown',
    tags=['markdown', 'frontmatter', 'yaml', 'metadata', 'parse'],
    label='Parse Frontmatter',
    label_key='modules.markdown.parse_frontmatter.label',
    description='Extract YAML frontmatter from Markdown content',
    description_key='modules.markdown.parse_frontmatter.description',
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
            label_key='modules.markdown.parse_frontmatter.params.text.label',
            description='Markdown content with frontmatter',
            description_key='modules.markdown.parse_frontmatter.params.text.description',
            required=True,
            placeholder='---\ntitle: My Post\n---\n\n# Content here',
            group=FieldGroup.BASIC,
            format='multiline',
        ),
    ),
    output_schema={
        'frontmatter': {
            'type': 'object',
            'description': 'Parsed frontmatter as a dictionary',
            'description_key': 'modules.markdown.parse_frontmatter.output.frontmatter.description',
        },
        'content': {
            'type': 'string',
            'description': 'Markdown content without frontmatter',
            'description_key': 'modules.markdown.parse_frontmatter.output.content.description',
        },
    },
    examples=[
        {
            'title': 'Parse YAML frontmatter',
            'title_key': 'modules.markdown.parse_frontmatter.examples.basic.title',
            'params': {
                'text': '---\ntitle: Hello World\ndate: 2024-01-01\ntags:\n  - python\n  - markdown\n---\n\n# Hello World\n\nContent here.',
            },
        }
    ],
)
async def markdown_parse_frontmatter(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract YAML frontmatter from Markdown content."""
    params = context['params']
    text = params.get('text')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    # Match frontmatter block: starts with --- on first line, ends with ---
    frontmatter_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.DOTALL)
    match = frontmatter_pattern.match(text)

    if not match:
        # No frontmatter found
        return {
            'ok': True,
            'data': {
                'frontmatter': {},
                'content': text,
            },
        }

    raw_frontmatter = match.group(1)
    content = text[match.end():]

    # Parse the frontmatter YAML
    frontmatter = {}
    try:
        import yaml
        parsed = yaml.safe_load(raw_frontmatter)
        if isinstance(parsed, dict):
            frontmatter = parsed
        elif parsed is not None:
            frontmatter = {'value': parsed}
    except ImportError:
        logger.debug("PyYAML not available, using basic parser")
        frontmatter = _basic_yaml_parse(raw_frontmatter)
    except Exception as e:
        logger.warning("YAML parsing failed, falling back to basic parser: %s", str(e))
        frontmatter = _basic_yaml_parse(raw_frontmatter)

    return {
        'ok': True,
        'data': {
            'frontmatter': frontmatter,
            'content': content,
        },
    }
