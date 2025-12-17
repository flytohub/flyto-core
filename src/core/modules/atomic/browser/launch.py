"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.launch',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup'],
    label='Launch Browser',
    label_key='modules.browser.launch.label',
    description='Launch a new browser instance with Playwright',
    description_key='modules.browser.launch.description',
    icon='Monitor',
    color='#4A90E2',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=10,  # Browser launch should complete within 10s
    retryable=True,  # Can retry if browser fails to launch
    max_retries=2,  # Don't retry too many times (resource intensive)
    concurrent_safe=False,  # Browser instances should not launch in parallel

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.launch', 'system.process'],

    params_schema={
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'label_key': 'modules.browser.launch.params.headless.label',
            'description': 'Run browser in headless mode (no UI)',
            'description_key': 'modules.browser.launch.params.headless.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'message': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Launch headless browser',
            'params': {'headless': True}
        },
        {
            'name': 'Launch visible browser',
            'params': {'headless': False}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
@register_module(
    module_id='browser.launch',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup'],
    label='Launch Browser',
    description='Launch a new browser instance with Playwright',
    icon='Monitor',
    color='#4A90E2',
)
class BrowserLaunchModule(BaseModule):
    """Launch Browser Module"""

    module_name = "Launch Browser"
    module_description = "Launch a new browser instance"
    required_permission = "browser.launch"

    def validate_params(self):
        self.headless = self.params.get('headless', False)

    async def execute(self) -> Any:
        from core.browser.driver import BrowserDriver

        driver = BrowserDriver(headless=self.headless)
        await driver.launch()

        # Store in context for later use
        self.context['browser'] = driver

        return {"status": "success", "message": "Browser launched successfully"}


