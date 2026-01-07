"""
Browser Screenshot Module - Take a screenshot of the current page
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.screenshot',
    version='1.0.0',
    category='browser',
    tags=['browser', 'screenshot', 'capture', 'image'],
    label='Take Screenshot',
    label_key='modules.browser.screenshot.label',
    description='Take a screenshot of the current page',
    description_key='modules.browser.screenshot.description',
    icon='Camera',
    color='#9B59B6',

    # Connection types
    input_types=['page'],
    output_types=['image', 'file'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    # Schema-driven params
    params_schema=compose(
        presets.OUTPUT_PATH(default='screenshot.png', placeholder='screenshot.png'),
        presets.SCREENSHOT_OPTIONS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'filepath': {'type': 'string', 'description': 'Path to the file'}
    },
    examples=[
        {
            'name': 'Take screenshot',
            'params': {'path': 'output/page.png'}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserScreenshotModule(BaseModule):
    """Screenshot Module"""

    module_name = "Take Screenshot"
    module_description = "Take a screenshot of the current page"
    required_permission = "browser.screenshot"

    def validate_params(self):
        self.path = self.params.get('path', 'screenshot.png')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        filepath = await browser.screenshot(self.path)
        return {"status": "success", "filepath": filepath}


