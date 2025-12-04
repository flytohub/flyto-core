"""
JSON Transform and Notify Composite Module

Transforms JSON data and sends notification with results.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.data.json_transform_notify',
    version='1.0.0',
    category='composite',
    subcategory='data',
    tags=['data', 'json', 'transform', 'notification'],

    # Display
    label='JSON Transform and Notify',
    label_key='modules.composite.data.json_transform_notify.label',
    description='Transform JSON data using JMESPath and send notification with results',
    description_key='modules.composite.data.json_transform_notify.description',

    # Visual
    icon='Braces',
    color='#8B5CF6',

    # Connection types
    input_types=['json'],
    output_types=['json', 'api_response'],

    # Steps definition
    steps=[
        {
            'id': 'parse',
            'module': 'data.json.parse',
            'params': {
                'json_string': '${params.json_input}'
            }
        },
        {
            'id': 'filter',
            'module': 'array.filter',
            'params': {
                'array': '${steps.parse.data}',
                'expression': '${params.filter_expression}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'map',
            'module': 'array.map',
            'params': {
                'array': '${steps.filter.result}',
                'expression': '${params.map_expression}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'stringify',
            'module': 'data.json.stringify',
            'params': {
                'data': '${steps.map.result}',
                'indent': 2
            }
        },
        {
            'id': 'notify',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.webhook_url}',
                'text': '📊 *Data Transform Results*\n\n```${steps.stringify.result}```'
            },
            'on_error': 'continue'
        }
    ],

    # Schema
    params_schema={
        'json_input': {
            'type': 'string',
            'label': 'JSON Input',
            'description': 'JSON string to transform',
            'placeholder': '[{"name": "John", "age": 30}]',
            'required': True,
            'multiline': True
        },
        'filter_expression': {
            'type': 'string',
            'label': 'Filter Expression',
            'description': 'Expression to filter data (e.g., item.age > 25)',
            'placeholder': 'true',
            'default': 'true',
            'required': False
        },
        'map_expression': {
            'type': 'string',
            'label': 'Map Expression',
            'description': 'Expression to transform each item',
            'placeholder': 'item',
            'default': 'item',
            'required': False
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'description': 'Slack webhook URL to send results',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'original_count': {'type': 'number'},
        'result_count': {'type': 'number'},
        'data': {'type': 'array'},
        'notification_sent': {'type': 'boolean'}
    },

    # Execution settings
    timeout=30,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Filter and notify',
            'description': 'Filter users over 25 and notify',
            'params': {
                'json_input': '[{"name": "John", "age": 30}, {"name": "Jane", "age": 20}]',
                'filter_expression': 'item.age > 25',
                'webhook_url': '${env.SLACK_WEBHOOK_URL}'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class JsonTransformNotify(CompositeModule):
    """
    JSON Transform and Notify Composite Module

    This composite module:
    1. Parses JSON input
    2. Filters data based on expression
    3. Maps/transforms each item
    4. Sends notification with results
    """

    def _build_output(self, metadata):
        """Build output with transformation results"""
        parse_result = self.step_results.get('parse', {})
        filter_result = self.step_results.get('filter', {})
        map_result = self.step_results.get('map', {})
        notify_result = self.step_results.get('notify', {})

        original_data = parse_result.get('data', [])
        result_data = map_result.get('result', filter_result.get('result', original_data))

        return {
            'status': 'success',
            'original_count': len(original_data) if isinstance(original_data, list) else 0,
            'result_count': len(result_data) if isinstance(result_data, list) else 0,
            'data': result_data,
            'notification_sent': notify_result.get('sent', False)
        }
