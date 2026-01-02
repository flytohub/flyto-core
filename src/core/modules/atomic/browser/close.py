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
    tags=['browser', 'automation', 'cleanup'],
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
    timeout=10,
    retryable=False,
    max_retries=0,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.close'],

    params_schema={},
    output_schema={
        'status': {'type': 'string'},
        'message': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Close browser',
            'params': {}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserCloseModule(BaseModule):
    """Close Browser Module"""

    module_name = "Close Browser"
    module_description = "Close the browser instance"
    required_permission = "browser.close"

    def validate_params(self):
        pass

    async def execute(self) -> Any:
        driver = self.context.get('browser')

        if not driver:
            return {"status": "warning", "message": "No browser instance to close"}

        await driver.close()

        # Remove from context
        self.context.pop('browser', None)

        return {"status": "success", "message": "Browser closed successfully"}
