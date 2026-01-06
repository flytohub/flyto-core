"""
Text Template Module
Fill text template with variables
"""
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='data.text.template',
    version='1.0.0',
    category='data',
    tags=['data', 'text', 'template', 'string', 'format'],
    label='Text Template',
    label_key='modules.data.text.template.label',
    description='Fill text template with variables',
    description_key='modules.data.text.template.description',
    icon='FileText',
    color='#8B5CF6',

    can_receive_from=['*'],
    can_connect_to=['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],

    # Execution settings
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.TEMPLATE(required=True),
        presets.VARIABLES(required=True),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status'
        },
        'result': {
            'type': 'string',
            'description': 'Filled template'
        }
    },
    examples=[
        {
            'name': 'Fill template',
            'params': {
                'template': 'Hello {name}, you scored {score} points!',
                'variables': {'name': 'Alice', 'score': 95}
            },
            'expected_output': {
                'status': 'success',
                'result': 'Hello Alice, you scored 95 points!'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def text_template(context: Dict[str, Any]) -> Dict[str, Any]:
    """Fill text template with variables."""
    params = context['params']
    template = params.get('template')
    variables = params.get('variables')

    if not template:
        return {
            'ok': False,
            'error': 'Missing required parameter: template',
            'error_code': 'MISSING_PARAM'
        }

    if not isinstance(variables, dict):
        return {
            'ok': False,
            'error': 'variables must be an object',
            'error_code': 'INVALID_TYPE'
        }

    try:
        result = template.format(**variables)
        return {
            'status': 'success',
            'result': result
        }
    except KeyError as e:
        return {
            'status': 'error',
            'message': f'Missing variable in template: {str(e)}'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Template error: {str(e)}'
        }
