# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

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
    tags=['browser', 'screenshot', 'capture', 'image', 'ssrf_protected', 'path_restricted'],
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
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*'],    # Schema-driven params
    params_schema=compose(
        presets.OUTPUT_PATH(default='screenshot.png', placeholder='screenshot.png'),
        presets.SCREENSHOT_OPTIONS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.screenshot.output.status.description'},
        'filepath': {'type': 'string', 'description': 'Path to the file',
                'description_key': 'modules.browser.screenshot.output.filepath.description'}
    },
    examples=[
        {
            'name': 'Take screenshot',
            'params': {'path': 'output/page.png'}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserScreenshotModule(BaseModule):
    """Screenshot Module"""

    module_name = "Take Screenshot"
    module_description = "Take a screenshot of the current page"
    required_permission = "browser.screenshot"

    def validate_params(self) -> None:
        self.path = self.params.get('path', 'screenshot.png')
        self.full_page = self.params.get('full_page', False)
        self.format = self.params.get('format', 'png')
        self.quality = self.params.get('quality', None)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Build screenshot kwargs
        kwargs = {
            'full_page': self.full_page,
        }
        if self.format and self.format != 'png':
            kwargs['type'] = self.format
        if self.quality is not None and self.format in ('jpeg', 'webp'):
            kwargs['quality'] = self.quality

        result = await browser.screenshot(self.path, **kwargs)
        if isinstance(result, dict):
            out = {"status": "success", "filepath": result.get('path', self.path)}
            if 'base64' in result:
                out['_images'] = [{'base64': result['base64'], 'media_type': result.get('media_type', 'image/png')}]
            return out
        else:
            return {"status": "success", "filepath": result}


