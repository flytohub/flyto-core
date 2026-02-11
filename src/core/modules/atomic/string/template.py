"""
String Template Module
Render a template with variable substitution.
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError


@register_module(
    module_id='string.template',
    version='1.0.0',
    category='string',
    tags=['string', 'template', 'interpolate', 'format', 'variables'],
    label='Template',
    label_key='modules.string.template.label',
    description='Render a template with variable substitution',
    description_key='modules.string.template.description',
    icon='FileCode',
    color='#6366F1',
    input_types=['string', 'object'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['string.*', 'data.*', 'flow.*', 'notification.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'template',
            type='text',
            label='Template',
            label_key='modules.string.template.params.template.label',
            description='Template string with {{variable}} placeholders',
            description_key='modules.string.template.params.template.description',
            required=True,
            placeholder='Hello, {{name}}! You have {{count}} messages.',
            group=FieldGroup.BASIC,
        ),
        field(
            'variables',
            type='object',
            label='Variables',
            label_key='modules.string.template.params.variables.label',
            description='Variables to substitute',
            description_key='modules.string.template.params.variables.description',
            required=True,
            placeholder='{"name": "John", "count": 5}',
            group=FieldGroup.BASIC,
        ),
        field(
            'missing_value',
            type='string',
            label='Missing Value',
            label_key='modules.string.template.params.missing_value.label',
            description='Value for undefined variables',
            description_key='modules.string.template.params.missing_value.description',
            default='',
            group=FieldGroup.OPTIONS,
            placeholder='value',
        ),
        field(
            'preserve_missing',
            type='boolean',
            label='Preserve Missing',
            label_key='modules.string.template.params.preserve_missing.label',
            description='Keep placeholder if variable is missing',
            description_key='modules.string.template.params.preserve_missing.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'result': {
            'type': 'string',
            'description': 'Rendered template',
            'description_key': 'modules.string.template.output.result.description'
        },
        'replaced': {
            'type': 'number',
            'description': 'Number of replacements made',
            'description_key': 'modules.string.template.output.replaced.description'
        },
        'missing': {
            'type': 'array',
            'description': 'Missing variable names',
            'description_key': 'modules.string.template.output.missing.description'
        }
    },
    timeout_ms=5000,
)
async def string_template(context: Dict[str, Any]) -> Dict[str, Any]:
    """Render a template with variable substitution."""
    params = context['params']
    template = params.get('template')
    variables = params.get('variables')
    missing_value = params.get('missing_value', '')
    preserve_missing = params.get('preserve_missing', False)

    if template is None:
        raise ValidationError("Missing required parameter: template", field="template")

    if variables is None:
        raise ValidationError("Missing required parameter: variables", field="variables")

    if not isinstance(variables, dict):
        raise ValidationError("Variables must be an object", field="variables")

    template = str(template)
    result = template
    replaced = 0
    missing = []

    # Find all placeholders
    pattern = r'\{\{(\s*[\w.]+\s*)\}\}'

    def replace_var(match):
        nonlocal replaced, missing
        var_name = match.group(1).strip()

        # Support nested keys with dot notation
        value = variables
        for key in var_name.split('.'):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                missing.append(var_name)
                if preserve_missing:
                    return match.group(0)
                return str(missing_value)

        replaced += 1
        return str(value)

    result = re.sub(pattern, replace_var, template)

    return {
        'ok': True,
        'data': {
            'result': result,
            'replaced': replaced,
            'missing': list(set(missing))  # Remove duplicates
        }
    }
