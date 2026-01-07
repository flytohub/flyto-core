"""
element.attribute - Get element attribute value
"""
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ..element_registry import get_element_registry


@register_module(
    module_id='element.attribute',
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
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.element.attribute.output.status.description'},
        'value': {'type': 'string', 'description': 'The returned value',
                'description_key': 'modules.element.attribute.output.value.description'}
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
        # Get element registry from context (context-aware, not global singleton)
        registry = get_element_registry(self.context)
        element = registry.get(self.element_id)
        if not element:
            return {"status": "error", "message": "Element does not exist", "value": None}

        try:
            value = await element.get_attribute(self.attribute_name)
            return {"status": "success", "value": value}
        except Exception as e:
            return {"status": "error", "message": str(e), "value": None}
