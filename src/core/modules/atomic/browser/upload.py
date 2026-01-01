"""
Browser Upload Module

Upload file to file input element.
"""
from typing import Any, Dict, List
from pathlib import Path
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='core.browser.upload',
    version='1.0.0',
    category='browser',
    tags=['browser', 'upload', 'file', 'input'],
    label='Upload File',
    label_key='modules.browser.upload.label',
    description='Upload file to file input element',
    description_key='modules.browser.upload.description',
    icon='Upload',
    color='#28A745',

    # Connection types
    input_types=['page'],
    output_types=['object'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='input[type="file"]'),
        presets.UPLOAD_FILE_PATH(),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string'},
        'filename': {'type': 'string'},
        'size': {'type': 'number'},
        'selector': {'type': 'string'}
    },
    examples=[
        {
            'name': 'Upload image',
            'params': {
                'selector': 'input[type="file"]',
                'file_path': '/path/to/image.png'
            }
        },
        {
            'name': 'Upload document',
            'params': {
                'selector': '#file-upload',
                'file_path': '/path/to/document.pdf'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserUploadModule(BaseModule):
    """Upload File Module"""

    module_name = "Upload File"
    module_description = "Upload file to file input element"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        if 'file_path' not in self.params:
            raise ValueError("Missing required parameter: file_path")

        self.selector = self.params['selector']
        self.file_path = self.params['file_path']
        self.timeout = self.params.get('timeout', 30000)

        # Verify file exists
        path = Path(self.file_path)
        if not path.exists():
            raise ValueError(f"File not found: {self.file_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {self.file_path}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        path = Path(self.file_path)

        # Set file on the input element
        await page.set_input_files(
            self.selector,
            self.file_path,
            timeout=self.timeout
        )

        return {
            "status": "success",
            "filename": path.name,
            "size": path.stat().st_size,
            "selector": self.selector
        }
