"""
Browser Automation Modules

Provides browser automation capabilities using Playwright.
All modules use i18n keys for multi-language support.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.screenshot',
    version='1.0.0',
    category='browser',
    tags=['browser', 'screenshot', 'capture', 'image'],
    label='Take Screenshot',
    label_key='modules.browser.screenshot.label',
    description='Take a screenshot of the current page',
    description_key='modules.browser.screenshot.description',
    icon='Camera',
    color='#9B59B6',
    params_schema={
        'path': {
            'type': 'string',
            'label': 'File Path',
            'label_key': 'modules.browser.screenshot.params.path.label',
            'placeholder': 'screenshot.png',
            'description': 'Path to save the screenshot',
            'description_key': 'modules.browser.screenshot.params.path.description',
            'default': 'screenshot.png',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'filepath': {'type': 'string'}
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


