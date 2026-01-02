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
    module_id='browser.extract',
    version='1.0.0',
    category='browser',
    tags=['browser', 'scraping', 'data', 'extract'],
    label='Extract Data',
    label_key='modules.browser.extract.label',
    description='Extract structured data from the page',
    description_key='modules.browser.extract.description',
    icon='Database',
    color='#E74C3C',

    # Connection types
    input_types=['page'],
    output_types=['json', 'array'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='.result-item'),
        presets.EXTRACT_LIMIT(),
        presets.EXTRACT_FIELDS(),
    ),
    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'array'},
        'count': {'type': 'number'}
    },
    examples=[
        {
            'name': 'Extract Google search results',
            'params': {
                'selector': '.g',
                'limit': 10,
                'fields': {
                    'title': {'selector': 'h3', 'type': 'text'},
                    'url': {'selector': 'a', 'type': 'attribute', 'attribute': 'href'}
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserExtractModule(BaseModule):
    """Extract Data Module"""

    module_name = "Extract Data"
    module_description = "Extract structured data from the page"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")

        self.selector = self.params['selector']

        # Handle limit parameter - convert string to integer
        limit_param = self.params.get('limit', None)
        if limit_param is not None:
            self.limit = int(limit_param) if isinstance(limit_param, str) else limit_param
        else:
            self.limit = None

        self.fields = self.params.get('fields', {})

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Use playwright to extract data
        elements = await browser.page.query_selector_all(self.selector)

        if self.limit:
            elements = elements[:self.limit]

        # Simple mode: if 'attribute' param is provided without 'fields', extract directly
        # This supports composite modules that pass {'selector': 'a', 'attribute': 'href'}
        simple_attribute = self.params.get('attribute')
        if simple_attribute and not self.fields:
            results = []
            for element in elements:
                try:
                    if simple_attribute == 'textContent' or simple_attribute == 'text':
                        value = await element.inner_text()
                    elif simple_attribute == 'innerHTML' or simple_attribute == 'html':
                        value = await element.inner_html()
                    else:
                        value = await element.get_attribute(simple_attribute)
                    results.append(value)
                except Exception:
                    results.append(None)
            return {"status": "success", "data": results, "count": len(results)}

        # Complex mode: extract multiple fields per element
        results = []
        for element in elements:
            item = {}
            for field_name, field_config in self.fields.items():
                try:
                    # Support new format: {'selector': 'h3', 'type': 'text', 'attribute': 'href'}
                    # Or old format: 'h3'
                    if isinstance(field_config, dict):
                        field_selector = field_config.get('selector', '')
                        field_type = field_config.get('type', 'text')
                        attribute_name = field_config.get('attribute', 'href')
                    else:
                        field_selector = field_config
                        field_type = 'text'
                        attribute_name = 'href'

                    # Support comma-separated multiple selectors (fallback mechanism)
                    selectors = [s.strip() for s in field_selector.split(',')]
                    field_value = None

                    for selector in selectors:
                        field_element = await element.query_selector(selector)
                        if field_element:
                            if field_type == 'attribute':
                                field_value = await field_element.get_attribute(attribute_name)
                            else:  # type == 'text'
                                field_value = await field_element.inner_text()
                            break  # Stop when found

                    item[field_name] = field_value
                except Exception:
                    item[field_name] = None
            results.append(item)

        return {"status": "success", "data": results, "count": len(results)}


