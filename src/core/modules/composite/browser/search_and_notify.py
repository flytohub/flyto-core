"""
Web Search and Notify Composite Module

Searches the web and sends results to a notification channel.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.browser.search_and_notify',
    version='1.0.0',
    category='composite',
    subcategory='browser',
    tags=['browser', 'search', 'notification', 'automation'],

    # Display
    label='Web Search and Notify',
    label_key='modules.composite.browser.search_and_notify.label',
    description='Search the web using Google and send results to Slack, Discord, or Telegram',
    description_key='modules.composite.browser.search_and_notify.description',

    # Visual
    icon='Search',
    color='#4285F4',

    # Connection types
    input_types=['text'],
    output_types=['api_response'],

    # Steps definition
    steps=[
        {
            'id': 'launch',
            'module': 'core.browser.launch',
            'params': {
                'headless': True
            }
        },
        {
            'id': 'goto',
            'module': 'core.browser.goto',
            'params': {
                'url': 'https://www.google.com'
            }
        },
        {
            'id': 'search_input',
            'module': 'core.browser.type',
            'params': {
                'selector': 'textarea[name="q"], input[name="q"]',
                'text': '${params.query}'
            }
        },
        {
            'id': 'submit',
            'module': 'core.browser.press',
            'params': {
                'key': 'Enter'
            }
        },
        {
            'id': 'wait_results',
            'module': 'core.browser.wait',
            'params': {
                'selector': '#search',
                'timeout': 10000
            }
        },
        {
            'id': 'extract',
            'module': 'core.browser.extract',
            'params': {
                'selector': '#search .g h3',
                'attribute': 'textContent',
                'multiple': True,
                'limit': 5
            }
        },
        {
            'id': 'notify',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.webhook_url}',
                'text': 'Search results for "${params.query}":\n${steps.extract.results}'
            },
            'on_error': 'continue'
        }
    ],

    # Schema
    params_schema={
        'query': {
            'type': 'string',
            'label': 'Search Query',
            'description': 'The search term to look up',
            'placeholder': 'workflow automation',
            'required': True
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'description': 'Slack, Discord, or Telegram webhook URL',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': True
        },
        'max_results': {
            'type': 'number',
            'label': 'Max Results',
            'description': 'Maximum number of results to return',
            'default': 5,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'query': {'type': 'string'},
        'results': {'type': 'array'},
        'notification_sent': {'type': 'boolean'}
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'Search and notify Slack',
            'description': 'Search for Python tutorials and send to Slack',
            'params': {
                'query': 'python tutorial',
                'webhook_url': '${env.SLACK_WEBHOOK_URL}'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class WebSearchAndNotify(CompositeModule):
    """
    Web Search and Notify Composite Module

    This composite module:
    1. Launches a headless browser
    2. Navigates to Google
    3. Performs a search
    4. Extracts top results
    5. Sends results to notification channel
    """

    def _build_output(self, metadata):
        """Build custom output for this composite"""
        extract_results = self.step_results.get('extract', {})
        notify_results = self.step_results.get('notify', {})

        return {
            'status': 'success',
            'query': self.params.get('query', ''),
            'results': extract_results.get('results', []),
            'notification_sent': notify_results.get('sent', False)
        }
