"""
element.text - Get element text content
"""
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ..element_registry import get_element_registry


@register_module(
    module_id='element.text',
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
        # Get element registry from context (context-aware, not global singleton)
        registry = get_element_registry(self.context)
        element = registry.get(self.element_id)
        if not element:
            return {"status": "error", "message": "Element does not exist", "text": None}

        try:
            text = await element.inner_text()
            return {"status": "success", "text": text}
        except Exception as e:
            return {"status": "error", "message": str(e), "text": None}
