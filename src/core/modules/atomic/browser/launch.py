"""
Browser Launch Module - Launch a new browser instance with Playwright
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.launch',
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
    input_types=[],
    output_types=['browser', 'page'],  # Browser launch also creates a default page

    # Connection rules
    can_connect_to=['browser.*', 'element.*', 'page.*'],  # Can connect to browser modules
    can_receive_from=['start', 'flow.*'],

    # Execution settings
    timeout=10,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.launch', 'system.process'],

    # Schema-driven params
    params_schema=compose(
        presets.BROWSER_HEADLESS(default=False),
        presets.VIEWPORT(),
    ),
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


