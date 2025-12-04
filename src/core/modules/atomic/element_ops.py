"""
element.* - Atomic modules for element operations

Provides basic element operations
- element.query: Find child elements within element
- element.text: Get element text
- element.attribute: Get element attribute
"""
from typing import Any, Optional
from ..base import BaseModule
from ..registry import register_module
from .element_registry import ElementRegistry


@register_module(
    module_id='core.element.query',
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
    timeout=5,  # Element query should be quick
    retryable=True,  # Can retry if element not ready
    max_retries=2,
    concurrent_safe=True,  # Stateless element operations

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    params_schema={
        'element_id': {
            'type': 'string',
            'label': 'Element ID',
            'label_key': 'modules.element.query.params.element_id.label',
            'description': 'Parent element ID (UUID)',
            'description_key': 'modules.element.query.params.element_id.description',
            'required': True
        },
        'selector': {
            'type': 'string',
            'label': 'CSS Selector',
            'label_key': 'modules.element.query.params.selector.label',
            'description': 'CSS selector to find child elements',
            'description_key': 'modules.element.query.params.selector.description',
            'required': True
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
        'status': {'type': 'string'},
        'element_id': {'type': 'string', 'optional': True},
        'element_ids': {'type': 'array', 'optional': True},
        'count': {'type': 'number', 'optional': True}
    },
    examples=[{
        'title': 'Find child element',
        'params': {
            'element_id': '${result_item}',
            'selector': 'h3'
        }
    }],
    author='Flyto2 Team',
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

    def validate_params(self):
        if 'element_id' not in self.params:
            raise ValueError("Missing parameter: element_id")
        if 'selector' not in self.params:
            raise ValueError("Missing parameter: selector")

        self.element_id = self.params['element_id']
        self.selector = self.params['selector']
        self.find_all = self.params.get('all', False)

    async def execute(self) -> Any:
        # Get element
        element = ElementRegistry.get(self.element_id)
        if not element:
            return {"status": "error", "message": "Element does not exist", "result": None}

        try:
            if self.find_all:
                # Find all child elements
                sub_elements = await element.query_selector_all(self.selector)
                if not sub_elements:
                    return {"status": "success", "count": 0, "element_ids": []}

                element_ids = ElementRegistry.register_many(sub_elements)
                return {"status": "success", "count": len(element_ids), "element_ids": element_ids}
            else:
                # Find first only
                sub_element = await element.query_selector(self.selector)
                if not sub_element:
                    return {"status": "success", "element_id": None}

                element_id = ElementRegistry.register(sub_element)
                return {"status": "success", "element_id": element_id}

        except Exception as e:
            return {"status": "error", "message": str(e), "result": None}


@register_module(
    module_id='core.element.text',
    version='1.0.0',
    category='element',
    subcategory='element',
    tags=['element', 'text', 'content'],
    label='Get Text',
    label_key='modules.element.text.label',
    description="Get element's text content",
    description_key='modules.element.text.description',
    icon='FileText',
    color='#8B5CF6',

    # Connection types
    input_types=['element'],
    output_types=['text', 'string'],
    can_receive_from=['browser.find', 'element.*'],
    can_connect_to=['data.*', 'string.*', 'notification.*'],

    # Phase 2: Execution settings
    timeout=5,  # Text extraction should be quick
    retryable=True,  # Can retry if element not ready
    max_retries=2,
    concurrent_safe=True,  # Stateless element operations

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    params_schema={
        'element_id': {
            'type': 'string',
            'label': 'Element ID',
            'label_key': 'modules.element.text.params.element_id.label',
            'description': 'Element ID (UUID)',
            'description_key': 'modules.element.text.params.element_id.description',
            'required': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'text': {'type': 'string'}
    },
    examples=[{
        'title': 'Get element text',
        'params': {
            'element_id': '${title_element}'
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class ElementTextModule(BaseModule):
    """
    Get element text content

    Parameters:
        element_id: element ID (UUID)

    Return:
        text: Text content String

    Example:
        {
            "module": "core.element.text",
            "params": {
                "element_id": "${title_element}"
            },
            "output": "title"
        }
    """

    module_name = "Get Text"
    module_description = "Get element's text content"
    required_permission = "browser.read"

    def validate_params(self):
        if 'element_id' not in self.params:
            raise ValueError("Missing parameter: element_id")

        self.element_id = self.params['element_id']

    async def execute(self) -> Any:
        element = ElementRegistry.get(self.element_id)
        if not element:
            return {"status": "error", "message": "Element does not exist", "text": None}

        try:
            text = await element.inner_text()
            return {"status": "success", "text": text}
        except Exception as e:
            return {"status": "error", "message": str(e), "text": None}


@register_module(
    module_id='core.element.attribute',
    version='1.0.0',
    category='element',
    subcategory='element',
    tags=['element', 'attribute', 'property'],
    label='Get Attribute',
    label_key='modules.element.attribute.label',
    description="Get element's attribute value",
    description_key='modules.element.attribute.description',
    icon='Tag',
    color='#8B5CF6',

    # Connection types
    input_types=['element'],
    output_types=['text', 'string'],
    can_receive_from=['browser.find', 'element.*'],
    can_connect_to=['data.*', 'string.*'],

    # Phase 2: Execution settings
    timeout=5,  # Attribute extraction should be quick
    retryable=True,  # Can retry if element not ready
    max_retries=2,
    concurrent_safe=True,  # Stateless element operations

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read'],

    params_schema={
        'element_id': {
            'type': 'string',
            'label': 'Element ID',
            'label_key': 'modules.element.attribute.params.element_id.label',
            'description': 'Element ID (UUID)',
            'description_key': 'modules.element.attribute.params.element_id.description',
            'required': True
        },
        'name': {
            'type': 'string',
            'label': 'Attribute Name',
            'label_key': 'modules.element.attribute.params.name.label',
            'description': 'Attribute name (e.g. href, src, class)',
            'description_key': 'modules.element.attribute.params.name.description',
            'placeholder': 'href',
            'required': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'value': {'type': 'string'}
    },
    examples=[{
        'title': 'Get href attribute',
        'params': {
            'element_id': '${link_element}',
            'name': 'href'
        }
    }],
    author='Flyto2 Team',
    license='MIT'
)
class ElementAttributeModule(BaseModule):
    """
    Get element attribute

    Parameters:
        element_id: element ID (UUID)
        name: Attribute name, e.g. 'href', 'src', 'class'

    Return:
        value: Attribute value

    Example:
        {
            "module": "core.element.attribute",
            "params": {
                "element_id": "${link_element}",
                "name": "href"
            },
            "output": "url"
        }
    """

    module_name = "Get Attribute"
    module_description = "Get element's attribute value"
    required_permission = "browser.read"

    def validate_params(self):
        if 'element_id' not in self.params:
            raise ValueError("Missing parameter: element_id")
        if 'name' not in self.params:
            raise ValueError("Missing parameter: name")

        self.element_id = self.params['element_id']
        self.attribute_name = self.params['name']

    async def execute(self) -> Any:
        element = ElementRegistry.get(self.element_id)
        if not element:
            return {"status": "error", "message": "Element does not exist", "value": None}

        try:
            value = await element.get_attribute(self.attribute_name)
            return {"status": "success", "value": value}
        except Exception as e:
            return {"status": "error", "message": str(e), "value": None}
