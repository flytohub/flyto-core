"""
API to Notification Composite Module

Fetches data from any API and sends it to a notification channel.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.developer.api_to_notification',
    label='API to Notification',
    icon='Zap',
    color='#F59E0B',

    steps=[
        {
            'id': 'fetch',
            'module': 'api.http_get',
            'params': {
                'url': '${params.api_url}',
                'headers': '${params.api_headers}'
            }
        },
        {
            'id': 'parse',
            'module': 'data.json.parse',
            'params': {'json_string': '${steps.fetch.body}'},
            'on_error': 'continue'
        },
        {
            'id': 'format',
            'module': 'data.text.template',
            'params': {
                'template': '${params.message_template}',
                'data': '${steps.parse.data}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'notify',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.webhook_url}',
                'text': '${steps.format.result}'
            }
        }
    ],

    params_schema={
        'api_url': {
            'type': 'string',
            'label': 'API URL',
            'required': True,
            'placeholder': 'https://api.example.com/data'
        },
        'api_headers': {
            'type': 'object',
            'label': 'API Headers',
            'default': {}
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'required': True,
            'placeholder': 'https://hooks.slack.com/...'
        },
        'message_template': {
            'type': 'string',
            'label': 'Message Template',
            'default': 'API Response:\n${data}',
            'placeholder': 'API Response: ${data.status}'
        }
    },

    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'api_response': {'type': 'object', 'description': 'The api response'},
        'notification_sent': {'type': 'boolean', 'description': 'The notification sent'}
    },

    timeout=60,
    retryable=True,
    max_retries=2,
)
class ApiToNotification(CompositeModule):
    """API to Notification - fetch API and send to Slack/Discord/Telegram"""

    def _build_output(self, metadata):
        fetch_result = self.step_results.get('fetch', {})
        parse_result = self.step_results.get('parse', {})
        notify_result = self.step_results.get('notify', {})

        return {
            'status': 'success',
            'api_response': parse_result.get('data', fetch_result),
            'notification_sent': notify_result.get('sent', False)
        }
