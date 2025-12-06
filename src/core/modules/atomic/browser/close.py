"""
Browser Close Module

Provides functionality to close browser instances.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.close',
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
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=10,  # Browser close should complete within 10s
    retryable=False,  # Don't retry close operations
    max_retries=0,
    concurrent_safe=False,

    # Phase 2: Security settings
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
@register_module(
    module_id='browser.close',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'cleanup'],
    label='Close Browser',
    description='Close the browser instance and release resources',
    icon='X',
    color='#E74C3C',
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
