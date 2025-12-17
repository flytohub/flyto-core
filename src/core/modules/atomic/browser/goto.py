"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.goto',
    version='1.0.0',
    category='browser',
    tags=['browser', 'navigation', 'url'],
    label='Go to URL',
    label_key='modules.browser.goto.label',
    description='Navigate to a specific URL',
    description_key='modules.browser.goto.description',
    icon='Globe',
    color='#5CB85C',
    params_schema={
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'modules.browser.goto.params.url.label',
            'placeholder': 'https://example.com',
            'description': 'The URL to navigate to',
            'description_key': 'modules.browser.goto.params.url.description',
            'required': True
        },
        'wait_until': {
            'type': 'select',
            'label': 'Wait Condition',
            'label_key': 'modules.browser.goto.params.wait_until.label',
            'options': [
                {
                    'value': 'load',
                    'label': 'Page Load Complete',
                    'label_key': 'modules.browser.goto.params.wait_until.options.load'
                },
                {
                    'value': 'networkidle',
                    'label': 'Network Idle',
                    'label_key': 'modules.browser.goto.params.wait_until.options.networkidle'
                },
                {
                    'value': 'domcontentloaded',
                    'label': 'DOM Content Loaded',
                    'label_key': 'modules.browser.goto.params.wait_until.options.domcontentloaded'
                }
            ],
            'default': 'domcontentloaded',
            'description': 'Condition to wait for page loading',
            'description_key': 'modules.browser.goto.params.wait_until.description',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'url': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Navigate to Google',
            'params': {
                'url': 'https://www.google.com',
                'wait_until': 'domcontentloaded'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
@register_module(
    module_id='browser.goto',
    version='1.0.0',
    category='browser',
    tags=['browser', 'navigation', 'url'],
    label='Go to URL',
    description='Navigate to a specific URL',
    icon='Globe',
    color='#5CB85C',
)
class BrowserGotoModule(BaseModule):
    """Navigate to URL Module"""

    module_name = "Go to URL"
    module_description = "Navigate to a specific URL"
    required_permission = "browser.navigate"

    def validate_params(self):
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params['url']
        # Default to 'domcontentloaded' for faster page loads (was 'networkidle' which hangs on many sites)
        self.wait_until = self.params.get('wait_until', 'domcontentloaded')
        self.timeout_ms = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.goto(self.url, wait_until=self.wait_until, timeout_ms=self.timeout_ms)
        return {"status": "success", "url": self.url}


