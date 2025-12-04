"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.click',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'click'],
    label='Click Element',
    label_key='modules.browser.click.label',
    description='Click an element on the page',
    description_key='modules.browser.click.description',
    icon='MousePointerClick',
    color='#F0AD4E',
    params_schema={
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.browser.click.params.selector.label',
            'placeholder': '#button-id or .button-class',
            'description': 'CSS selector of the element to click',
            'description_key': 'modules.browser.click.params.selector.description',
            'required': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'selector': {'type': 'string'}
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


