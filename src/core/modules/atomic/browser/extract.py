"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.extract',
    version='1.0.0',
    category='browser',
    tags=['browser', 'scraping', 'data', 'extract'],
    label='Extract Data',
    label_key='modules.browser.extract.label',
    description='Extract structured data from the page',
    description_key='modules.browser.extract.description',
    icon='Database',
    color='#E74C3C',
    params_schema={
        'selector': {
            'type': 'string',
            'label': 'Container Selector',
            'label_key': 'modules.browser.extract.params.selector.label',
            'placeholder': '.result-item',
            'description': 'CSS selector for container elements',
            'description_key': 'modules.browser.extract.params.selector.description',
            'required': True
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.browser.extract.params.limit.label',
            'placeholder': '10',
            'description': 'Maximum number of items to extract',
            'description_key': 'modules.browser.extract.params.limit.description',
            'required': False
        },
        'fields': {
            'type': 'object',
            'label': 'Fields to Extract',
            'label_key': 'modules.browser.extract.params.fields.label',
            'description': 'Define fields to extract from each item',
            'description_key': 'modules.browser.extract.params.fields.description',
            'required': False
        }
    },
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


