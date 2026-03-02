# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
YAML Parse Module
Parse YAML string or file into Python object
"""
from typing import Any, Dict
import os

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup, Visibility
from ...errors import ValidationError, FileNotFoundError, ModuleError


def _classify_type(data: Any) -> str:
    """Classify the parsed YAML result type."""
    if isinstance(data, dict):
        return 'object'
    elif isinstance(data, list):
        return 'array'
    else:
        return 'scalar'


@register_module(
    module_id='data.yaml.parse',
    version='1.0.0',
    category='data',
    tags=['data', 'yaml', 'parse', 'transform', 'path_restricted'],
    label='Parse YAML',
    label_key='modules.data.yaml.parse.label',
    description='Parse YAML string or file into Python object',
    description_key='modules.data.yaml.parse.description',
    icon='FileText',
    color='#10B981',

    # Connection types
    input_types=['text', 'file_path'],
    output_types=['object', 'array'],
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
            type='string',
            label='YAML Content',
            label_key='modules.data.yaml.parse.params.content.label',
            description='YAML string to parse',
            description_key='modules.data.yaml.parse.params.content.description',
            placeholder='name: John\nage: 30',
            required=False,
            format='multiline',
            group=FieldGroup.BASIC,
        ),
        field(
            'file_path',
            type='string',
            label='File Path',
            label_key='modules.data.yaml.parse.params.file_path.label',
            description='Path to YAML file (used if content is empty)',
            description_key='modules.data.yaml.parse.params.file_path.description',
            placeholder='/path/to/config.yaml',
            required=False,
            format='path',
            group=FieldGroup.BASIC,
        ),
        field(
            'multi_document',
            type='boolean',
            label='Multi-Document',
            label_key='modules.data.yaml.parse.params.multi_document.label',
            description='Parse multiple YAML documents separated by --- (uses safe_load_all)',
            description_key='modules.data.yaml.parse.params.multi_document.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'any',
            'description': 'Parsed YAML data (object, array, or scalar)',
            'description_key': 'modules.data.yaml.parse.output.result.description',
        },
        'type': {
            'type': 'string',
            'description': 'Type of parsed result: object, array, or scalar',
            'description_key': 'modules.data.yaml.parse.output.type.description',
        },
    },
    examples=[
        {
            'name': 'Parse YAML string',
            'params': {
                'content': 'name: John\nage: 30\ncities:\n  - NYC\n  - LA',
                'multi_document': False,
            },
            'expected_output': {
                'ok': True,
                'data': {
                    'result': {
                        'name': 'John',
                        'age': 30,
                        'cities': ['NYC', 'LA'],
                    },
                    'type': 'object',
                },
            },
        },
        {
            'name': 'Parse multi-document YAML',
            'params': {
                'content': '---\nname: John\n---\nname: Jane',
                'multi_document': True,
            },
            'expected_output': {
                'ok': True,
                'data': {
                    'result': [
                        {'name': 'John'},
                        {'name': 'Jane'},
                    ],
                    'type': 'array',
                },
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def yaml_parse(context: Dict[str, Any]) -> Dict[str, Any]:
    """Parse YAML string or file into Python object."""
    if yaml is None:
        raise ModuleError(
            "PyYAML is not installed. Install it with: pip install pyyaml"
        )

    params = context['params']
    content = params.get('content')
    file_path = params.get('file_path')
    multi_document = params.get('multi_document', False)

    if not content and not file_path:
        raise ValidationError(
            "Either 'content' or 'file_path' must be provided",
            field='content',
        )

    try:
        if content:
            raw = content
        else:
            if not os.path.exists(file_path):
                raise FileNotFoundError(
                    f"File not found: {file_path}", path=file_path
                )
            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()

        if multi_document:
            result = list(yaml.safe_load_all(raw))
            result_type = 'array'
        else:
            result = yaml.safe_load(raw)
            result_type = _classify_type(result)

        return {
            'ok': True,
            'data': {
                'result': result,
                'type': result_type,
            },
        }

    except FileNotFoundError:
        raise
    except yaml.YAMLError as e:
        raise ModuleError(f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise ModuleError(f"Failed to parse YAML: {str(e)}")
