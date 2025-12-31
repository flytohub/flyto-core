"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='core.browser.press',
    version='1.0.0',
    category='browser',
    tags=['browser', 'keyboard', 'interaction', 'key'],
    label='Press Key',
    label_key='modules.browser.press.label',
    description='Press a keyboard key',
    description_key='modules.browser.press.description',
    icon='Command',
    color='#34495E',

    # Connection types
    input_types=['page'],
    output_types=['page'],

    params_schema=compose(
        presets.KEYBOARD_KEY(),
    ),
    output_schema={
        'status': {'type': 'string'},
        'key': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Press Enter key',
            'params': {'key': 'Enter'}
        },
        {
            'name': 'Press Escape key',
            'params': {'key': 'Escape'}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserPressModule(BaseModule):
    """Press Key Module"""

    module_name = "Press Key"
    module_description = "Press a keyboard key"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'key' not in self.params:
            raise ValueError("Missing required parameter: key")
        self.key = self.params['key']

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.page.keyboard.press(self.key)
        return {"status": "success", "key": self.key}
