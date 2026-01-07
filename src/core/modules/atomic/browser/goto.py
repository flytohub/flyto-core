"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.

Example of schema presets usage - compare before/after:
    BEFORE (36 lines for params_schema):
        params_schema={
            'url': {'type': 'string', 'label': 'URL', ...},
            'wait_until': {'type': 'select', 'options': [...], ...}
        }

    AFTER (4 lines with presets):
        params_schema=compose(
            presets.URL(required=True),
            presets.WAIT_CONDITION(),
            presets.TIMEOUT_MS(),
        )
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_url_with_env_config, SSRFError


@register_module(
    module_id='browser.goto',
    version='1.0.0',
    category='browser',
    tags=['browser', 'navigation', 'url'],
    label='Go to URL',
    label_key='modules.browser.goto.label',
    description='Navigate to a specific URL',
    description_key='modules.browser.goto.description',
    icon='Globe',
    color='#5CB85C',

    # Connection types
    input_types=['browser'],
    output_types=['page'],

    # Connection rules
    can_receive_from=['browser.launch', 'browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'data.*', 'flow.*', 'file.*'],

    # Schema-driven params
    params_schema=compose(
        presets.URL(required=True, placeholder='https://example.com'),
        presets.WAIT_CONDITION(default='domcontentloaded'),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.goto.output.status.description'},
        'url': {'type': 'string', 'description': 'URL address',
                'description_key': 'modules.browser.goto.output.url.description'}
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
class BrowserGotoModule(BaseModule):
    """Navigate to URL Module"""

    module_name = "Go to URL"
    module_description = "Navigate to a specific URL"
    required_permission = "browser.navigate"

    def validate_params(self):
        if 'url' not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params['url']

        # SECURITY: Validate URL against SSRF attacks
        try:
            validate_url_with_env_config(self.url)
        except SSRFError as e:
            raise ValueError(f"SSRF protection: {e}")

        # Default to 'domcontentloaded' for faster page loads (was 'networkidle' which hangs on many sites)
        self.wait_until = self.params.get('wait_until', 'domcontentloaded')
        self.timeout_ms = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.goto(self.url, wait_until=self.wait_until, timeout_ms=self.timeout_ms)
        return {"status": "success", "url": self.url}


