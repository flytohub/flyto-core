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
    module_id='browser.press',
    version='1.0.0',
    category='browser',
    tags=['browser', 'keyboard', 'interaction', 'key', 'ssrf_protected'],
    label='Press Key',
    label_key='modules.browser.press.label',
    description='Press a keyboard key',
    description_key='modules.browser.press.description',
    icon='Command',
    color='#34495E',

    # Connection types
    input_types=['page'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.KEYBOARD_KEY(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.press.output.status.description'},
        'key': {'type': 'string', 'description': 'Key identifier',
                'description_key': 'modules.browser.press.output.key.description'}
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
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserPressModule(BaseModule):
    """Press Key Module"""

    module_name = "Press Key"
    module_description = "Press a keyboard key"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'key' not in self.params:
            raise ValueError("Missing required parameter: key")
        self.key = self.params['key']

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.page.keyboard.press(self.key)
        return {"status": "success", "key": self.key}
