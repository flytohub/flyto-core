"""
Browser Download Module

Download file from browser.
"""
from typing import Any, Dict, Optional
from pathlib import Path
import asyncio
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.download',
    version='1.0.0',
    category='browser',
    tags=['browser', 'download', 'file'],
    label='Download File',
    label_key='modules.browser.download.label',
    description='Download file from browser',
    description_key='modules.browser.download.description',
    icon='Download',
    color='#DC3545',

    # Connection types
    input_types=['page'],
    output_types=['file'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        presets.SELECTOR(required=False, placeholder='a.download-link'),
        presets.DOWNLOAD_SAVE_PATH(),
        presets.TIMEOUT_MS(default=60000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.download.output.status.description'},
        'path': {'type': 'string', 'description': 'File or resource path',
                'description_key': 'modules.browser.download.output.path.description'},
        'filename': {'type': 'string', 'description': 'Name of the file',
                'description_key': 'modules.browser.download.output.filename.description'},
        'size': {'type': 'number', 'description': 'Size in bytes',
                'description_key': 'modules.browser.download.output.size.description'}
    },
    examples=[
        {
            'name': 'Click download button and save',
            'params': {
                'selector': '#download-btn',
                'save_path': '/downloads/report.pdf'
            }
        },
        {
            'name': 'Download with custom timeout',
            'params': {
                'selector': 'a.download',
                'save_path': '/downloads/large-file.zip',
                'timeout': 120000
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserDownloadModule(BaseModule):
    """Download File Module"""

    module_name = "Download File"
    module_description = "Download file from browser"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'save_path' not in self.params:
            raise ValueError("Missing required parameter: save_path")

        self.selector = self.params.get('selector')
        self.save_path = self.params['save_path']
        self.timeout = self.params.get('timeout', 60000)

        # Ensure directory exists
        save_dir = Path(self.save_path).parent
        save_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Wait for download event
        async with page.expect_download(timeout=self.timeout) as download_info:
            if self.selector:
                await page.click(self.selector)
            # If no selector, assume download is already being triggered

        download = await download_info.value

        # Save the file
        await download.save_as(self.save_path)

        # Get file info
        path = Path(self.save_path)
        size = path.stat().st_size if path.exists() else 0

        return {
            "status": "success",
            "path": str(path.absolute()),
            "filename": path.name,
            "size": size,
            "suggested_filename": download.suggested_filename
        }
