"""
Browser Click Module - Click an element on the page
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.click',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'click'],
    label='Click Element',
    label_key='modules.browser.click.label',
    description='Click an element on the page',
    description_key='modules.browser.click.description',
    icon='MousePointerClick',
    color='#F0AD4E',

    # Connection types
    input_types=['page'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    # Schema-driven params
    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='#button-id or .button-class'),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.click.output.status.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.click.output.selector.description'}
    },
    examples=[
        {
            'name': 'Click submit button',
            'params': {'selector': '#submit-button'}
        },
        {
            'name': 'Click first link',
            'params': {'selector': 'a.link-class'}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserClickModule(BaseModule):
    """Click Element Module"""

    module_name = "Click Element"
    module_description = "Click an element on the page"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        self.selector = self.params['selector']

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.click(self.selector)
        return {"status": "success", "selector": self.selector}


