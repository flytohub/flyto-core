"""
Browser Type Module - Type text into an input field
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.type',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'input', 'keyboard'],
    label='Type Text',
    label_key='modules.browser.type.label',
    description='Type text into an input field',
    description_key='modules.browser.type.description',
    icon='Keyboard',
    color='#5BC0DE',

    # Connection types
    input_types=['page'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    # Schema-driven params
    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='input[name="email"]'),
        presets.TEXT(key='text', required=True, label='Text Content', placeholder='Text to type'),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.type.output.status.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.type.output.selector.description'}
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


