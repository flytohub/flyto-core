"""
Browser Hover Module

Hover mouse over an element.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.hover',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'hover', 'mouse'],
    label='Hover Element',
    label_key='modules.browser.hover.label',
    description='Hover mouse over an element',
    description_key='modules.browser.hover.description',
    icon='MousePointer',
    color='#6F42C1',

    # Connection types
    input_types=['page'],
    output_types=['page'],

    params_schema={
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.browser.hover.params.selector.label',
            'placeholder': '#element-id or .element-class',
            'description': 'CSS selector of the element to hover over',
            'description_key': 'modules.browser.hover.params.selector.description',
            'required': True
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (ms)',
            'label_key': 'modules.browser.hover.params.timeout.label',
            'description': 'Maximum time to wait for element in milliseconds',
            'description_key': 'modules.browser.hover.params.timeout.description',
            'default': 30000,
            'required': False
        },
        'position': {
            'type': 'object',
            'label': 'Position',
            'label_key': 'modules.browser.hover.params.position.label',
            'description': 'Relative position within element {x, y} as percentages (0-1)',
            'description_key': 'modules.browser.hover.params.position.description',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'selector': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Hover over menu item',
            'params': {'selector': '.menu-item'}
        },
        {
            'name': 'Hover with timeout',
            'params': {'selector': '#dropdown-trigger', 'timeout': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserHoverModule(BaseModule):
    """Hover Element Module"""

    module_name = "Hover Element"
    module_description = "Hover mouse over an element"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        self.selector = self.params['selector']
        self.timeout = self.params.get('timeout', 30000)
        self.position = self.params.get('position')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        hover_options = {'timeout': self.timeout}
        if self.position:
            hover_options['position'] = {
                'x': self.position.get('x', 0.5),
                'y': self.position.get('y', 0.5)
            }

        await page.hover(self.selector, **hover_options)

        return {
            "status": "success",
            "selector": self.selector
        }
