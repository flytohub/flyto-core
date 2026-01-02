"""
JSON Transform and Notify Composite Module

Transforms JSON data and sends notification with results.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.data.json_transform_notify',
    label='JSON Transform and Notify',
    icon='Braces',
    color='#8B5CF6',

    steps=[
        {
            'id': 'parse',
            'module': 'data.json.parse',
            'params': {'json_string': '${params.json_input}'}
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
                'text': 'Data Transform Results\n\n${steps.stringify.result}'
            },
            'on_error': 'continue'
        }
    ],

    params_schema={
        'json_input': {
            'type': 'string',
            'label': 'JSON Input',
            'required': True,
            'placeholder': '[{"name": "John", "age": 30}]'
        },
        'filter_expression': {
            'type': 'string',
            'label': 'Filter Expression',
            'default': 'true',
            'placeholder': 'item.age > 25'
        },
        'map_expression': {
            'type': 'string',
            'label': 'Map Expression',
            'default': 'item',
            'placeholder': 'item'
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'placeholder': '${env.SLACK_WEBHOOK_URL}'
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'original_count': {'type': 'number'},
        'result_count': {'type': 'number'},
        'data': {'type': 'array'},
        'notification_sent': {'type': 'boolean'}
    },

    timeout=30,
    retryable=True,
    max_retries=2,
)
class JsonTransformNotify(CompositeModule):
    """JSON Transform and Notify - filter, transform, and notify"""

    def _build_output(self, metadata):
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
