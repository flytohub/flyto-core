"""
browser.find - Find elements in page

This is an atomic operation. Only responsible for finding and returning element ID list
"""
from typing import Any
from ..base import BaseModule
from ..registry import register_module
from .element_registry import ElementRegistry


@register_module(
    module_id='core.browser.find',
    version='1.0.0',
    category='browser',
    subcategory='browser',
    tags=['browser', 'find', 'element', 'selector'],
    label='Find Elements',
    label_key='modules.browser.find.label',
    description='Find elements in page and return element ID list',
    description_key='modules.browser.find.description',
    icon='Search',
    color='#8B5CF6',

    # Connection types
    input_types=['browser_instance', 'page_instance'],
    output_types=['element', 'array'],
    can_receive_from=['browser.page.*'],
    can_connect_to=['element.*', 'data.*'],

    # Phase 2: Execution settings
    timeout=10,  # Finding elements should complete within 10s
    retryable=True,  # Can retry if elements not ready
    max_retries=2,
    concurrent_safe=True,  # Stateless find operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    params_schema={
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.browser.find.params.selector.label',
            'description': 'CSS selector to find elements',
            'description_key': 'modules.browser.find.params.selector.description',
            'placeholder': 'div.result-item',
            'required': True
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.browser.find.params.limit.label',
            'description': 'Limit count (optional)',
            'description_key': 'modules.browser.find.params.limit.description',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'count': {'type': 'number'},
        'element_ids': {'type': 'array'}
    },
    examples=[{
        'title': 'Find search results',
        'params': {
            'selector': 'div.tF2Cxc',
            'limit': 10
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserFindModule(BaseModule):
    """
    Find elements in page

    Parameters:
        selector: CSS Selector
        limit: Limit count (optional)

    Return:
        element_ids: element ID list (list of UUID strings)

    Example:
        {
            "module": "core.browser.find",
            "params": {
                "selector": "div.tF2Cxc",
                "limit": 10
            },
            "output": "search_results"
        }
        # search_results = ['uuid-1', 'uuid-2', ...]
    """

    module_name = "Find Elements"
    module_description = "Find elements in page and return element ID list"
    required_permission = "browser.read"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing parameter: selector")

        self.selector = self.params['selector']
        self.limit = self.params.get('limit', None)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser or not browser.page:
            raise RuntimeError("Browser not started")

        # Use Playwright to find elements
        elements = await browser.page.query_selector_all(self.selector)

        # Limit count
        if self.limit is not None:
            elements = elements[:self.limit]

        # Register elements and return ID list
        element_ids = ElementRegistry.register_many(elements)

        return {
            "status": "success",
            "count": len(element_ids),
            "element_ids": element_ids
        }
