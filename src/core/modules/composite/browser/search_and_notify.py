"""
Web Search and Notify Composite Module

Searches the web and sends results to a notification channel.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.browser.search_and_notify',
    version='1.0.0',
    category='browser',
    subcategory='search',
    tags=['browser', 'search', 'notification', 'automation'],

    # Context requirements
    requires_context=None,
    provides_context=['data', 'api_response'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='Web Search and Notify',
    ui_label_key='composite.search_and_notify.label',
    ui_description='Search the web using Google and send results to Slack, Discord, or Telegram',
    ui_description_key='composite.search_and_notify.desc',
    ui_group='Browser / Search',
    ui_icon='Search',
    ui_color='#4285F4',

    # UI form generation
    ui_params_schema={
        'query': {
            'type': 'string',
            'label': 'Search Query',
            'label_key': 'composite.search_and_notify.query.label',
            'description': 'The search term to look up',
            'description_key': 'composite.search_and_notify.query.desc',
            'placeholder': 'workflow automation',
            'required': True,
            'ui_component': 'input',
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'label_key': 'composite.search_and_notify.webhook_url.label',
            'description': 'Slack, Discord, or Telegram webhook URL',
            'description_key': 'composite.search_and_notify.webhook_url.desc',
            'placeholder': 'https://hooks.slack.com/...',
            'required': True,
            'ui_component': 'input',
        },
        'max_results': {
            'type': 'number',
            'label': 'Max Results',
            'label_key': 'composite.search_and_notify.max_results.label',
            'description': 'Maximum number of results to return',
            'description_key': 'composite.search_and_notify.max_results.desc',
            'default': 5,
            'required': False,
            'ui_component': 'number',
        }
    },

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

    # Output schema
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
