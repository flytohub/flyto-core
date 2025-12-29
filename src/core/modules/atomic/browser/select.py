"""
Browser Select Module

Select option from dropdown element.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.select',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'select', 'dropdown', 'form'],
    label='Select Option',
    label_key='modules.browser.select.label',
    description='Select option from dropdown element',
    description_key='modules.browser.select.description',
    icon='ChevronDown',
    color='#20C997',

    # Connection types
    input_types=['page'],
    output_types=['page'],

    params_schema={
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.browser.select.params.selector.label',
            'placeholder': 'select#country',
            'description': 'CSS selector of the select element',
            'description_key': 'modules.browser.select.params.selector.description',
            'required': True
        },
        'value': {
            'type': 'string',
            'label': 'Value',
            'label_key': 'modules.browser.select.params.value.label',
            'description': 'Option value attribute to select',
            'description_key': 'modules.browser.select.params.value.description',
            'required': False
        },
        'label': {
            'type': 'string',
            'label': 'Label',
            'label_key': 'modules.browser.select.params.label.label',
            'description': 'Option text content to select (alternative to value)',
            'description_key': 'modules.browser.select.params.label.description',
            'required': False
        },
        'index': {
            'type': 'number',
            'label': 'Index',
            'label_key': 'modules.browser.select.params.index.label',
            'description': 'Option index to select (0-based)',
            'description_key': 'modules.browser.select.params.index.description',
            'required': False
        },
        'timeout': {
            'type': 'number',
            'label': 'Timeout (ms)',
            'label_key': 'modules.browser.select.params.timeout.label',
            'description': 'Maximum time to wait for element',
            'description_key': 'modules.browser.select.params.timeout.description',
            'default': 30000,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'selected': {'type': 'array'},
        'selector': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Select by value',
            'params': {'selector': 'select#country', 'value': 'us'}
        },
        {
            'name': 'Select by label text',
            'params': {'selector': 'select#country', 'label': 'United States'}
        },
        {
            'name': 'Select by index',
            'params': {'selector': 'select#country', 'index': 2}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserSelectModule(BaseModule):
    """Select Option Module"""

    module_name = "Select Option"
    module_description = "Select option from dropdown"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")

        self.selector = self.params['selector']
        self.value = self.params.get('value')
        self.label = self.params.get('label')
        self.index = self.params.get('index')
        self.timeout = self.params.get('timeout', 30000)

        # At least one selection method must be provided
        if self.value is None and self.label is None and self.index is None:
            raise ValueError("Must provide at least one of: value, label, or index")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Build selection options
        if self.value is not None:
            selected = await page.select_option(
                self.selector,
                value=self.value,
                timeout=self.timeout
            )
        elif self.label is not None:
            selected = await page.select_option(
                self.selector,
                label=self.label,
                timeout=self.timeout
            )
        elif self.index is not None:
            selected = await page.select_option(
                self.selector,
                index=self.index,
                timeout=self.timeout
            )

        return {
            "status": "success",
            "selected": selected,
            "selector": self.selector
        }
