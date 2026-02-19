# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
YAML Generate Module
Generate YAML string from Python object
"""
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup, Visibility
from ...errors import ValidationError, ModuleError


@register_module(
    module_id='data.yaml.generate',
    version='1.0.0',
    category='data',
    tags=['data', 'yaml', 'generate', 'transform', 'serialize'],
    label='Generate YAML',
    label_key='modules.data.yaml.generate.label',
    description='Generate YAML string from Python object',
    description_key='modules.data.yaml.generate.description',
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
            type='any',
            label='Data',
            label_key='modules.data.yaml.generate.params.data.label',
            description='Python object, array, or value to convert to YAML',
            description_key='modules.data.yaml.generate.params.data.description',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'default_flow_style',
            type='boolean',
            label='Flow Style',
            label_key='modules.data.yaml.generate.params.default_flow_style.label',
            description='Use inline/flow style (JSON-like) instead of block style',
            description_key='modules.data.yaml.generate.params.default_flow_style.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'sort_keys',
            type='boolean',
            label='Sort Keys',
            label_key='modules.data.yaml.generate.params.sort_keys.label',
            description='Sort dictionary keys alphabetically',
            description_key='modules.data.yaml.generate.params.sort_keys.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'indent',
            type='number',
            label='Indent Size',
            label_key='modules.data.yaml.generate.params.indent.label',
            description='Number of spaces for indentation',
            description_key='modules.data.yaml.generate.params.indent.description',
            default=2,
            min=1,
            max=8,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'allow_unicode',
            type='boolean',
            label='Allow Unicode',
            label_key='modules.data.yaml.generate.params.allow_unicode.label',
            description='Allow unicode characters in output without escaping',
            description_key='modules.data.yaml.generate.params.allow_unicode.description',
            default=True,
            advanced=True,
            visibility=Visibility.EXPERT,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'yaml': {
            'type': 'string',
            'description': 'Generated YAML string',
            'description_key': 'modules.data.yaml.generate.output.yaml.description',
        },
    },
    examples=[
        {
            'name': 'Generate YAML from dict',
            'params': {
                'data': {
                    'name': 'John',
                    'age': 30,
                    'cities': ['NYC', 'LA'],
                },
                'sort_keys': False,
                'indent': 2,
            },
            'expected_output': {
                'ok': True,
                'data': {
                    'yaml': 'name: John\nage: 30\ncities:\n- NYC\n- LA\n',
                },
            },
        }
    ],
    author='Flyto Team',
    license='MIT',
)
async def yaml_generate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate YAML string from Python object."""
    if yaml is None:
        raise ModuleError(
            "PyYAML is not installed. Install it with: pip install pyyaml"
        )

    params = context['params']
    data = params.get('data')
    default_flow_style = params.get('default_flow_style', False)
    sort_keys = params.get('sort_keys', False)
    indent = params.get('indent', 2)
    allow_unicode = params.get('allow_unicode', True)

    if data is None:
        raise ValidationError(
            "Missing required parameter: data", field='data'
        )

    try:
        yaml_string = yaml.dump(
            data,
            default_flow_style=default_flow_style,
            sort_keys=sort_keys,
            indent=indent,
            allow_unicode=allow_unicode,
        )

        return {
            'ok': True,
            'data': {
                'yaml': yaml_string,
            },
        }

    except yaml.YAMLError as e:
        raise ModuleError(f"Failed to serialize to YAML: {str(e)}")
    except Exception as e:
        raise ModuleError(f"Failed to generate YAML: {str(e)}")
