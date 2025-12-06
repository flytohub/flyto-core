"""
API to Notification Composite Module

Fetches data from any API and sends it to a notification channel.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.developer.api_to_notification',
    version='1.0.0',
    category='developer',
    subcategory='api',
    tags=['api', 'notification', 'webhook', 'integration'],

    # Context requirements
    requires_context=None,
    provides_context=['data', 'api_response'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='API to Notification',
    ui_label_key='composite.api_to_notification.label',
    ui_description='Fetch data from an API endpoint and send results to Slack, Discord, or Telegram',
    ui_description_key='composite.api_to_notification.desc',
    ui_group='Developer / Integration',
    ui_icon='Zap',
    ui_color='#F59E0B',

    # UI form generation
    ui_params_schema={
        'api_url': {
            'type': 'string',
            'label': 'API URL',
            'label_key': 'composite.api_to_notification.api_url.label',
            'description': 'The API endpoint to fetch data from',
            'description_key': 'composite.api_to_notification.api_url.desc',
            'placeholder': 'https://api.example.com/data',
            'required': True,
            'ui_component': 'input',
        },
        'api_headers': {
            'type': 'object',
            'label': 'API Headers',
            'label_key': 'composite.api_to_notification.api_headers.label',
            'description': 'Headers to send with the API request',
            'description_key': 'composite.api_to_notification.api_headers.desc',
            'default': {},
            'required': False,
            'ui_component': 'json',
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'label_key': 'composite.api_to_notification.webhook_url.label',
            'description': 'Slack, Discord, or Telegram webhook URL',
            'description_key': 'composite.api_to_notification.webhook_url.desc',
            'placeholder': 'https://hooks.slack.com/...',
            'required': True,
            'ui_component': 'input',
        },
        'message_template': {
            'type': 'string',
            'label': 'Message Template',
            'label_key': 'composite.api_to_notification.message_template.label',
            'description': 'Template for the notification message',
            'description_key': 'composite.api_to_notification.message_template.desc',
            'placeholder': 'API Response: ${data.status}',
            'default': 'API Response:\n${data}',
            'required': False,
            'ui_component': 'textarea',
        }
    },

    # Connection types
    input_types=['url', 'json'],
    output_types=['api_response'],

    # Steps definition
    steps=[
        {
            'id': 'fetch',
            'module': 'core.api.http_get',
            'params': {
                'url': '${params.api_url}',
                'headers': '${params.api_headers}'
            }
        },
        {
            'id': 'parse',
            'module': 'data.json.parse',
            'params': {
                'json_string': '${steps.fetch.body}'
            },
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

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'api_response': {'type': 'object'},
        'notification_sent': {'type': 'boolean'}
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Weather API to Slack',
            'description': 'Fetch weather and send to Slack',
            'params': {
                'api_url': 'https://api.weather.gov/stations/KORD/observations/latest',
                'webhook_url': '${env.SLACK_WEBHOOK_URL}',
                'message_template': 'Current weather: ${data.properties.textDescription}'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class ApiToNotification(CompositeModule):
    """
    API to Notification Composite Module

    This composite module:
    1. Fetches data from an API endpoint
    2. Parses the JSON response
    3. Formats a message using a template
    4. Sends notification to the specified channel
    """

    def _build_output(self, metadata):
        """Build output with API response and notification status"""
        fetch_result = self.step_results.get('fetch', {})
        parse_result = self.step_results.get('parse', {})
        notify_result = self.step_results.get('notify', {})

        return {
            'status': 'success',
            'api_response': parse_result.get('data', fetch_result),
            'notification_sent': notify_result.get('sent', False)
        }
