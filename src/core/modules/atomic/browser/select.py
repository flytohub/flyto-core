"""
Browser Select Module

Select option from dropdown element.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.select',
    version='1.0.0',
    category='browser',
    tags=['browser', 'interaction', 'select', 'dropdown', 'form', 'ssrf_protected'],
    label='Select Option',
    label_key='modules.browser.select.label',
    description='Select option from dropdown element',
    description_key='modules.browser.select.description',
    icon='ChevronDown',
    color='#20C997',

    # Connection types
    input_types=['page'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='select#country'),
        presets.SELECT_VALUE(),
        presets.SELECT_LABEL(),
        presets.SELECT_INDEX(),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.select.output.status.description'},
        'selected': {'type': 'array', 'description': 'The selected',
                'description_key': 'modules.browser.select.output.selected.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.select.output.selector.description'}
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
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserSelectModule(BaseModule):
    """Select Option Module"""

    module_name = "Select Option"
    module_description = "Select option from dropdown"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
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
