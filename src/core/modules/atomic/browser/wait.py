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
class BrowserWaitModule(BaseModule):
    """Wait Module"""

    module_name = "Wait"
    module_description = "Wait for a duration or element to appear"
    required_permission = "browser.interact"

    def validate_params(self):
        self.duration = self.params.get('duration', 1)
        self.selector = self.params.get('selector')

    async def execute(self) -> Any:
        import asyncio

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        if self.selector:
            # Wait for element to appear
            await browser.wait_for_selector(self.selector)
            return {"status": "success", "selector": self.selector}
        else:
            # Wait for specified duration
            await asyncio.sleep(self.duration)
            return {"status": "success", "duration": self.duration}


