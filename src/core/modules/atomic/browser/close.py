"""
Browser Close Module

Provides functionality to close browser instances.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='browser.close',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'cleanup', 'ssrf_protected'],
    label='Close Browser',
    label_key='modules.browser.close.label',
    description='Close the browser instance and release resources',
    description_key='modules.browser.close.description',
    icon='X',
    color='#E74C3C',

    # Connection types
    input_types=['browser', 'page'],  # Accept both browser and page
    output_types=[],

    # Connection rules
    can_receive_from=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
    can_connect_to=['notification.*', 'data.*', 'file.*', 'flow.*', 'end'],

    # Execution settings
    timeout_ms=10000,
    retryable=False,
    max_retries=0,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    params_schema={
        '_no_params': {
            'type': 'boolean',
            'label': 'No Parameters',
            'description': 'This module requires no parameters',
            'default': True,
            'hidden': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.close.output.status.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.browser.close.output.message.description'}
    },
    examples=[
        {
            'name': 'Close browser',
            'params': {}
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class BrowserCloseModule(BaseModule):
    """Close Browser Module"""

    module_name = "Close Browser"
    module_description = "Close the browser instance"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        pass

    async def execute(self) -> Any:
        driver = self.context.get('browser')

        if not driver:
            return {"status": "warning", "message": "No browser instance to close"}

        await driver.close()

        # Remove from context
        self.context.pop('browser', None)

        return {"status": "success", "message": "Browser closed successfully"}
