"""
XML Generate Module
Generate XML string from Python dict
"""
from typing import Any, Dict, List, Optional, Union
import xml.etree.ElementTree as ET
from xml.dom import minidom

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup, Visibility
from ...errors import ValidationError, ModuleError


def _dict_to_element(tag: str, data: Any) -> ET.Element:
    """
    Convert a Python dict/value to an XML Element.

    Recognizes @attributes and #text conventions from xml_parse output.
    """
    element = ET.Element(tag)

    if isinstance(data, dict):
        # Handle @attributes
        attributes = data.get('@attributes', {})
        if isinstance(attributes, dict):
            for attr_key, attr_val in attributes.items():
                element.set(str(attr_key), str(attr_val))

        # Handle #text
        text = data.get('#text')
        if text is not None:
            element.text = str(text)

        # Handle child elements
        for key, value in data.items():
            if key in ('@attributes', '#text'):
                continue
            if isinstance(value, list):
                for item in value:
                    child = _dict_to_element(key, item)
                    element.append(child)
            else:
                child = _dict_to_element(key, value)
                element.append(child)

    elif isinstance(data, list):
        # List at root level: wrap each item as a child element
        for item in data:
            child = _dict_to_element('item', item)
            element.append(child)

    elif data is not None:
        element.text = str(data)

    return element


@register_module(
    module_id='data.xml.generate',
    version='1.0.0',
    category='data',
    tags=['data', 'xml', 'generate', 'transform', 'serialize'],
    label='Generate XML',
    label_key='modules.data.xml.generate.label',
    description='Generate XML string from Python dict',
    description_key='modules.data.xml.generate.description',
    icon='FileText',
    color='#10B981',

    # Connection types
    input_types=['object', 'array'],
    output_types=['text'],
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
            'data',
            type='object',
            label='Data',
            label_key='modules.data.xml.generate.params.data.label',
            description='Python dict or object to convert to XML',
            description_key='modules.data.xml.generate.params.data.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'root_tag',
            type='string',
            label='Root Tag',
            label_key='modules.data.xml.generate.params.root_tag.label',
            description='Tag name for the root XML element',
            description_key='modules.data.xml.generate.params.root_tag.description',
            default='root',
            placeholder='root',
            group=FieldGroup.BASIC,
        ),
        field(
            'pretty',
            type='boolean',
            label='Pretty Print',
            label_key='modules.data.xml.generate.params.pretty.label',
            description='Format XML with indentation for readability',
            description_key='modules.data.xml.generate.params.pretty.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'encoding',
            type='string',
            label='Encoding',
            label_key='modules.data.xml.generate.params.encoding.label',
            description='XML encoding declaration value',
            description_key='modules.data.xml.generate.params.encoding.description',
            default='utf-8',
            options=[
                {'value': 'utf-8', 'label': 'UTF-8 (Recommended)'},
                {'value': 'ascii', 'label': 'ASCII'},
                {'value': 'utf-16', 'label': 'UTF-16'},
                {'value': 'iso-8859-1', 'label': 'ISO-8859-1'},
            ],
            advanced=True,
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'declaration',
            type='boolean',
            label='XML Declaration',
            label_key='modules.data.xml.generate.params.declaration.label',
            description='Include <?xml version="1.0"?> declaration at top',
            description_key='modules.data.xml.generate.params.declaration.description',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'xml': {
            'type': 'string',
            'description': 'Generated XML string',
            'description_key': 'modules.data.xml.generate.output.xml.description',
        },
    },
    examples=[
        {
            'name': 'Generate XML from dict',
            'params': {
                'data': {
                    'user': {
                        '@attributes': {'id': '1'},
                        'name': 'John',
                        'age': '30',
                    }
                },
                'root_tag': 'users',
                'pretty': True,
            },
            'expected_output': {
                'ok': True,
                'data': {
                    'xml': '<?xml version="1.0" encoding="utf-8"?>\n<users>\n  <user id="1">\n    <name>John</name>\n    <age>30</age>\n  </user>\n</users>\n',
                },
            },
        }
    ],
    author='Flyto Team',
    license='MIT',
)
async def xml_generate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate XML string from Python dict."""
    params = context['params']
    data = params.get('data')
    root_tag = params.get('root_tag', 'root')
    pretty = params.get('pretty', True)
    encoding = params.get('encoding', 'utf-8')
    declaration = params.get('declaration', True)

    if data is None:
        raise ValidationError(
            "Missing required parameter: data", field='data'
        )

    try:
        root = _dict_to_element(root_tag, data)

        if pretty:
            # Use minidom for pretty printing
            rough_string = ET.tostring(root, encoding='unicode')
            parsed_dom = minidom.parseString(rough_string)
            if declaration:
                xml_string = parsed_dom.toprettyxml(
                    indent='  ', encoding=None
                )
                # toprettyxml adds its own declaration; replace encoding
                xml_string = xml_string.replace(
                    '<?xml version="1.0" ?>',
                    f'<?xml version="1.0" encoding="{encoding}"?>',
                )
            else:
                # Remove the declaration line from toprettyxml output
                lines = parsed_dom.toprettyxml(indent='  ').split('\n')
                xml_string = '\n'.join(lines[1:])  # skip first declaration line
        else:
            if declaration:
                xml_string = f'<?xml version="1.0" encoding="{encoding}"?>'
                xml_string += ET.tostring(root, encoding='unicode')
            else:
                xml_string = ET.tostring(root, encoding='unicode')

        return {
            'ok': True,
            'data': {
                'xml': xml_string,
            },
        }

    except Exception as e:
        raise ModuleError(f"Failed to generate XML: {str(e)}")
