"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.type',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'input', 'keyboard'],
    label='Type Text',
    label_key='modules.browser.type.label',
    description='Type text into an input field',
    description_key='modules.browser.type.description',
    icon='Keyboard',
    color='#5BC0DE',
    params_schema={
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.browser.type.params.selector.label',
            'placeholder': 'input[name="email"]',
            'description': 'CSS selector of the input field',
            'description_key': 'modules.browser.type.params.selector.description',
            'required': True
        },
        'text': {
            'type': 'string',
            'label': 'Text Content',
            'label_key': 'modules.browser.type.params.text.label',
            'placeholder': 'Text to type',
            'description': 'The text to type into the field',
            'description_key': 'modules.browser.type.params.text.description',
            'required': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'selector': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Type email address',
            'params': {
                'selector': 'input[type="email"]',
                'text': 'user@example.com'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserTypeModule(BaseModule):
    """Type Text Module"""

    module_name = "Type Text"
    module_description = "Type text into an input field"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        if 'text' not in self.params:
            raise ValueError("Missing required parameter: text")

        self.selector = self.params['selector']
        self.text = self.params['text']

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.type(self.selector, self.text)
        return {
            "ok": True,
            "output": {
                "selector": self.selector,
                "text": self.text
            },
            "error": None,
            "meta": {}
        }


