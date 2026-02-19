"""
XML Parse Module
Parse XML string or file into Python dict
"""
from typing import Any, Dict
import xml.etree.ElementTree as ET
import os

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup, Visibility
from ...errors import ValidationError, FileNotFoundError, ModuleError


def _element_to_dict(element: ET.Element, preserve_attributes: bool) -> Any:
    """
    Convert an XML element to a nested dict.

    Uses @attributes for attributes and #text for text content.
    """
    result: Dict[str, Any] = {}

    # Add attributes
    if preserve_attributes and element.attrib:
        result['@attributes'] = dict(element.attrib)

    # Group children by tag
    children_by_tag: Dict[str, list] = {}
    for child in element:
        tag = child.tag
        if tag not in children_by_tag:
            children_by_tag[tag] = []
        children_by_tag[tag].append(_element_to_dict(child, preserve_attributes))

    # Add children to result
    for tag, children in children_by_tag.items():
        if len(children) == 1:
            result[tag] = children[0]
        else:
            result[tag] = children

    # Add text content
    text = (element.text or '').strip()
    if text:
        if result:
            result['#text'] = text
        else:
            # Leaf element with only text — return the string directly
            if preserve_attributes and element.attrib:
                result['#text'] = text
            else:
                return text

    # Handle tail text (ignored — tail belongs to parent context)

    # If element has no children, no attributes, and no text, return empty dict
    if not result:
        return None

    return result


@register_module(
    module_id='data.xml.parse',
    version='1.0.0',
    category='data',
    tags=['data', 'xml', 'parse', 'transform', 'path_restricted'],
    label='Parse XML',
    label_key='modules.data.xml.parse.label',
    description='Parse XML string or file into Python dict',
    description_key='modules.data.xml.parse.description',
    icon='FileText',
    color='#10B981',

    # Connection types
    input_types=['text', 'file_path'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        field(
            'content',
            type='text',
            label='XML Content',
            label_key='modules.data.xml.parse.params.content.label',
            description='XML string to parse',
            description_key='modules.data.xml.parse.params.content.description',
            placeholder='<root><item>value</item></root>',
            required=False,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'file_path',
            type='string',
            label='File Path',
            label_key='modules.data.xml.parse.params.file_path.label',
            description='Path to XML file (used if content is empty)',
            description_key='modules.data.xml.parse.params.file_path.description',
            placeholder='/path/to/data.xml',
            required=False,
            format='path',
            group=FieldGroup.BASIC,
        ),
        field(
            'preserve_attributes',
            type='boolean',
            label='Preserve Attributes',
            label_key='modules.data.xml.parse.params.preserve_attributes.label',
            description='Include XML element attributes as @attributes in output',
            description_key='modules.data.xml.parse.params.preserve_attributes.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'object',
            'description': 'Parsed XML as nested dict',
            'description_key': 'modules.data.xml.parse.output.result.description',
        },
        'root_tag': {
            'type': 'string',
            'description': 'Root element tag name',
            'description_key': 'modules.data.xml.parse.output.root_tag.description',
        },
    },
    examples=[
        {
            'name': 'Parse XML string',
            'params': {
                'content': '<users><user id="1"><name>John</name></user></users>',
                'preserve_attributes': True,
            },
            'expected_output': {
                'ok': True,
                'data': {
                    'result': {
                        'user': {
                            '@attributes': {'id': '1'},
                            'name': 'John',
                        }
                    },
                    'root_tag': 'users',
                },
            },
        }
    ],
    author='Flyto Team',
    license='MIT',
)
async def xml_parse(context: Dict[str, Any]) -> Dict[str, Any]:
    """Parse XML string or file into Python dict."""
    params = context['params']
    content = params.get('content')
    file_path = params.get('file_path')
    preserve_attributes = params.get('preserve_attributes', True)

    if not content and not file_path:
        raise ValidationError(
            "Either 'content' or 'file_path' must be provided",
            field='content',
        )

    try:
        if content:
            root = ET.fromstring(content)
        else:
            if not os.path.exists(file_path):
                raise FileNotFoundError(
                    f"File not found: {file_path}", path=file_path
                )
            tree = ET.parse(file_path)
            root = tree.getroot()

        parsed = _element_to_dict(root, preserve_attributes)

        return {
            'ok': True,
            'data': {
                'result': parsed if isinstance(parsed, dict) else {root.tag: parsed},
                'root_tag': root.tag,
            },
        }

    except FileNotFoundError:
        raise
    except ET.ParseError as e:
        raise ModuleError(f"Invalid XML: {str(e)}")
    except Exception as e:
        raise ModuleError(f"Failed to parse XML: {str(e)}")
