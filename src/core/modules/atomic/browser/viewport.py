"""
Browser Viewport Module - Resize browser viewport

Simple, focused module for viewport resizing.
Uses Playwright's page.set_viewport_size().

Works across all browsers (Chromium, Firefox, WebKit).
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


@register_module(
    module_id='browser.viewport',
    version='1.0.0',
    category='browser',
    tags=['browser', 'viewport', 'resize', 'responsive'],
    label='Resize Viewport',
    label_key='modules.browser.viewport.label',
    description='Resize browser viewport to specific dimensions',
    description_key='modules.browser.viewport.description',
    icon='Maximize2',
    color='#6366F1',

    # Connection types
    input_types=['page'],
    output_types=['page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],

    params_schema=compose(
        field(
            'width',
            type='number',
            label='Width',
            label_key='modules.browser.viewport.params.width.label',
            description='Viewport width in pixels',
            required=True,
            min=320,
            max=3840,
            default=1280,
        ),
        field(
            'height',
            type='number',
            label='Height',
            label_key='modules.browser.viewport.params.height.label',
            description='Viewport height in pixels',
            required=True,
            min=240,
            max=2160,
            default=720,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.viewport.output.status.description'
        },
        'viewport': {
            'type': 'object',
            'description': 'Applied viewport dimensions',
            'description_key': 'modules.browser.viewport.output.viewport.description'
        },
        'previous_viewport': {
            'type': 'object',
            'description': 'Previous viewport dimensions',
            'description_key': 'modules.browser.viewport.output.previous_viewport.description'
        },
    },
    examples=[
        {
            'name': 'Mobile viewport',
            'params': {'width': 375, 'height': 667}
        },
        {
            'name': 'Tablet viewport',
            'params': {'width': 768, 'height': 1024}
        },
        {
            'name': 'Desktop viewport',
            'params': {'width': 1920, 'height': 1080}
        },
        {
            'name': 'Laptop viewport',
            'params': {'width': 1366, 'height': 768}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=10000,
    required_permissions=['browser.automation'],
)
class BrowserViewportModule(BaseModule):
    """Resize Viewport Module"""

    module_name = "Resize Viewport"
    module_description = "Resize browser viewport"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.width = self.params.get('width')
        self.height = self.params.get('height')

        if not self.width:
            raise ValueError("Missing required parameter: width")
        if not self.height:
            raise ValueError("Missing required parameter: height")

        # Validate ranges
        if not 320 <= self.width <= 3840:
            raise ValueError(f"Width must be between 320 and 3840, got: {self.width}")
        if not 240 <= self.height <= 2160:
            raise ValueError(f"Height must be between 240 and 2160, got: {self.height}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Get current viewport
        current_viewport = page.viewport_size or {'width': 0, 'height': 0}

        # Set new viewport
        await page.set_viewport_size({
            'width': int(self.width),
            'height': int(self.height)
        })

        return {
            "status": "success",
            "viewport": {
                "width": int(self.width),
                "height": int(self.height)
            },
            "previous_viewport": current_viewport,
        }
