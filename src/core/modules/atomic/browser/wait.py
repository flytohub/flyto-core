"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.wait',
    version='1.0.0',
    category='browser',
    tags=['browser', 'wait', 'delay', 'selector'],
    label='Wait',
    label_key='modules.browser.wait.label',
    description='Wait for a duration or until an element appears',
    description_key='modules.browser.wait.description',
    icon='Clock',
    color='#95A5A6',
    params_schema={
        'duration': {
            'type': 'number',
            'label': 'Duration (seconds)',
            'label_key': 'modules.browser.wait.params.duration.label',
            'placeholder': '1',
            'description': 'Time to wait in seconds',
            'description_key': 'modules.browser.wait.params.duration.description',
            'default': 1,
            'required': False
        },
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.browser.wait.params.selector.label',
            'placeholder': '.element-to-wait-for',
            'description': 'Wait for this element to appear (overrides duration)',
            'description_key': 'modules.browser.wait.params.selector.description',
            'required': False
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (ms)',
            'description': 'Maximum time to wait in milliseconds',
            'default': 30000,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'selector': {'type': 'string', 'optional': True},
        'duration': {'type': 'number', 'optional': True}
    },
    examples=[
        {
            'name': 'Wait 2 seconds',
            'params': {'duration': 2}
        },
        {
            'name': 'Wait for element',
            'params': {'selector': '#loading-complete'}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
@register_module(
    module_id='browser.wait',
    version='1.0.0',
    category='browser',
    tags=['browser', 'wait', 'delay', 'selector'],
    label='Wait',
    description='Wait for a duration or until an element appears',
    icon='Clock',
    color='#95A5A6',
)
class BrowserWaitModule(BaseModule):
    """Wait Module"""

    module_name = "Wait"
    module_description = "Wait for a duration or element to appear"
    required_permission = "browser.interact"

    def validate_params(self):
        self.duration = self.params.get('duration', 1)
        self.selector = self.params.get('selector')
        self.timeout = self.params.get('timeout', 30000)

    async def execute(self) -> Any:
        import asyncio

        browser = self.context.get('browser')

        if self.selector:
            # Wait for element to appear
            if not browser:
                raise RuntimeError("Browser not launched. Please run browser.launch first")
            await browser.wait(self.selector, timeout_ms=self.timeout)
            return {"status": "success", "selector": self.selector}
        elif self.timeout and not self.selector and 'duration' not in self.params:
            # If only timeout is provided (used as simple delay in ms)
            await asyncio.sleep(self.timeout / 1000)
            return {"status": "success", "duration": self.timeout / 1000}
        else:
            # Wait for specified duration in seconds
            await asyncio.sleep(self.duration)
            return {"status": "success", "duration": self.duration}


