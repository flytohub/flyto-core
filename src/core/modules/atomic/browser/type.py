"""
Browser Type Module - Type text into an input field
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='browser.type',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'input', 'keyboard', 'ssrf_protected'],
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
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],    # Schema-driven params
    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='input[name="email"]'),
        presets.TEXT(key='text', required=True, label='Text Content', placeholder='Text to type'),
        field('delay', type='number', label='Typing Delay (ms)',
              label_key='modules.browser.type.param.delay.label',
              description='Delay between keystrokes in milliseconds',
              description_key='modules.browser.type.param.delay.description',
              default=0, min=0),
        field('clear', type='boolean', label='Clear Field First',
              label_key='modules.browser.type.param.clear.label',
              description='Clear the input field before typing',
              description_key='modules.browser.type.param.clear.description',
              default=False),
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
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserTypeModule(BaseModule):
    """Type Text Module"""

    module_name = "Type Text"
    module_description = "Type text into an input field"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        if 'text' not in self.params:
            raise ValueError("Missing required parameter: text")

        self.selector = self.params['selector']
        self.text = self.params['text']
        self.delay = self.params.get('delay', 0)
        self.clear = self.params.get('clear', False)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Clear field first if requested
        if self.clear:
            await browser.fill(self.selector, '')

        await browser.type(self.selector, self.text, delay_ms=self.delay)

        # Mask sensitive text in return value
        is_sensitive = any(kw in self.selector.lower() for kw in ['password', 'passwd', 'secret', 'token', 'key', 'credential'])
        return {
            "status": "success",
            "selector": self.selector,
            "text": '***' if is_sensitive else self.text,
            "text_length": len(self.text),
        }


