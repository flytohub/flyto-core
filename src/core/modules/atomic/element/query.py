"""
element.query - Find child elements within element
"""
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ..element_registry import get_element_registry


@register_module(
    module_id='element.query',
    version='1.0.0',
    category='element',
    subcategory='element',
    tags=['element', 'query', 'find'],
    label='Query Element',
    label_key='modules.element.query.label',
    description='Find child elements within element',
    description_key='modules.element.query.description',
    icon='Search',
    color='#8B5CF6',

    # Connection types
    input_types=['element'],
    output_types=['element', 'array'],
    can_receive_from=['browser.find', 'element.query'],
    can_connect_to=['element.*', 'data.*'],

    # Phase 2: Execution settings
    timeout_ms=5000,  # Element query should be quick
    retryable=True,  # Can retry if element not ready
    max_retries=2,
    concurrent_safe=True,  # Stateless element operations

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'element_id': {
            'type': 'string',
            'label': 'Element ID',
            'label_key': 'modules.element.query.params.element_id.label',
            'description': 'Parent element ID (UUID)',
            'description_key': 'modules.element.query.params.element_id.description',
            'required': True,
            'placeholder': 'example-id',
        },
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.element.query.params.selector.label',
            'description': 'CSS selector to find child elements',
            'description_key': 'modules.element.query.params.selector.description',
            'required': True,
            'placeholder': 'Enter Selector...',
        },
        'all': {
            'type': 'boolean',
            'label': 'Find All',
            'label_key': 'modules.element.query.params.all.label',
            'description': 'Whether to find all matching elements (default: false, find first only)',
            'description_key': 'modules.element.query.params.all.description',
            'default': False,
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.element.query.output.status.description'},
        'element_id': {'type': 'string', 'optional': True, 'description': 'Found element ID (single mode)',
                'description_key': 'modules.element.query.output.element_id.description'},
        'element_ids': {'type': 'array', 'optional': True, 'description': 'List of found element IDs (all mode)',
                'description_key': 'modules.element.query.output.element_ids.description'},
        'count': {'type': 'number', 'optional': True, 'description': 'Number of elements found',
                'description_key': 'modules.element.query.output.count.description'}
    },
    examples=[{
        'title': 'Find child element',
        'params': {
            'element_id': '${result_item}',
            'selector': 'h3'
        }
    }],
    author='Flyto Team',
    license='MIT'
)
class ElementQueryModule(BaseModule):
    """
    Find child elements within element

    Parameters:
        element_id: element ID (UUID)
        selector: CSS Selector
        all: Whether to find all (Default False, find first only)

    Return:
        element_id: child element ID (single) or element_ids: child element ID list (multiple)
        Return null if not found

    Example:
        {
            "module": "core.element.query",
            "params": {
                "element_id": "${result_item}",
                "selector": "h3"
            },
            "output": "title_element"
        }
    """

    module_name = "Element Query"
    module_description = "Find child elements within element"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        if 'element_id' not in self.params:
            raise ValueError("Missing parameter: element_id")
        if 'selector' not in self.params:
            raise ValueError("Missing parameter: selector")

        self.element_id = self.params['element_id']
        self.selector = self.params['selector']
        self.find_all = self.params.get('all', False)

    async def execute(self) -> Any:
        # Get element registry from context (context-aware, not global singleton)
        registry = get_element_registry(self.context)

        # Get element
        element = registry.get(self.element_id)
        if not element:
            return {"status": "error", "message": "Element does not exist", "result": None}

        try:
            if self.find_all:
                # Find all child elements
                sub_elements = await element.query_selector_all(self.selector)
                if not sub_elements:
                    return {"status": "success", "count": 0, "element_ids": []}

                element_ids = registry.register_many(sub_elements)
                return {"status": "success", "count": len(element_ids), "element_ids": element_ids}
            else:
                # Find first only
                sub_element = await element.query_selector(self.selector)
                if not sub_element:
                    return {"status": "success", "element_id": None}

                element_id = registry.register(sub_element)
                return {"status": "success", "element_id": element_id}

        except Exception as e:
            return {"status": "error", "message": str(e), "result": None}
