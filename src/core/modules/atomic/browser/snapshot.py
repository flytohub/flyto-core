"""
Browser Snapshot Module - DOM snapshot capture

Capture DOM snapshots in various formats:
- HTML: Full page HTML source
- MHTML: Single-file archive (Chromium only)
- Text: Plain text content

Works across all browsers, with MHTML limited to Chromium.
"""
from typing import Any, Dict, Optional
from pathlib import Path
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


@register_module(
    module_id='browser.snapshot',
    version='1.0.0',
    category='browser',
    tags=['browser', 'snapshot', 'dom', 'html', 'mhtml', 'debug'],
    label='DOM Snapshot',
    label_key='modules.browser.snapshot.label',
    description='Capture DOM snapshot in HTML, MHTML, or text format',
    description_key='modules.browser.snapshot.description',
    icon='FileCode',
    color='#0EA5E9',

    # Connection types
    input_types=['page'],
    output_types=['string', 'file'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],

    params_schema=compose(
        field(
            'format',
            type='string',
            label='Format',
            label_key='modules.browser.snapshot.params.format.label',
            description='Snapshot format',
            required=False,
            default='html',
            options=[
                {'value': 'html', 'label': 'HTML (page source)'},
                {'value': 'mhtml', 'label': 'MHTML (single file archive, Chromium only)'},
                {'value': 'text', 'label': 'Text (plain text content)'},
            ],
        ),
        presets.SELECTOR(
            key='selector',
            required=False,
            label='Element Selector',
            placeholder='#content, .main-article',
        ),
        presets.OUTPUT_PATH(
            key='path',
            required=False,
            placeholder='/tmp/snapshot.html',
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.snapshot.output.status.description'
        },
        'format': {
            'type': 'string',
            'description': 'Snapshot format used',
            'description_key': 'modules.browser.snapshot.output.format.description'
        },
        'content': {
            'type': 'string',
            'description': 'Snapshot content (if no path specified)',
            'description_key': 'modules.browser.snapshot.output.content.description'
        },
        'path': {
            'type': 'string',
            'description': 'Path to saved file',
            'description_key': 'modules.browser.snapshot.output.path.description'
        },
        'size_bytes': {
            'type': 'number',
            'description': 'Content size in bytes',
            'description_key': 'modules.browser.snapshot.output.size_bytes.description'
        },
    },
    examples=[
        {
            'name': 'Get page HTML',
            'params': {'format': 'html'}
        },
        {
            'name': 'Save page as MHTML archive',
            'params': {'format': 'mhtml', 'path': '/tmp/page.mhtml'}
        },
        {
            'name': 'Extract text from specific element',
            'params': {'format': 'text', 'selector': 'article.main-content'}
        },
        {
            'name': 'Save HTML of specific section',
            'params': {'format': 'html', 'selector': '#main', 'path': '/tmp/section.html'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.automation'],
)
class BrowserSnapshotModule(BaseModule):
    """DOM Snapshot Module"""

    module_name = "DOM Snapshot"
    module_description = "Capture DOM snapshot"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.format = self.params.get('format', 'html')
        self.selector = self.params.get('selector')
        self.output_path = self.params.get('path', '')

        if self.format not in ['html', 'mhtml', 'text']:
            raise ValueError(f"Invalid format: {self.format}. Must be html, mhtml, or text")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # MHTML requires Chromium
        if self.format == 'mhtml' and browser.browser_type != 'chromium':
            return {
                "status": "error",
                "error": f"MHTML format only supported on Chromium, got: {browser.browser_type}",
                "error_code": "CHROMIUM_ONLY"
            }

        # Capture content based on format
        if self.format == 'html':
            content = await self._capture_html(page)
        elif self.format == 'mhtml':
            content = await self._capture_mhtml(page)
        else:  # text
            content = await self._capture_text(page)

        # Build result
        result = {
            "status": "success",
            "format": self.format,
            "size_bytes": len(content.encode('utf-8') if isinstance(content, str) else content),
            "url": page.url,
        }

        # Save to file or return content
        if self.output_path:
            path = Path(self.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding='utf-8')

            result["path"] = str(path.absolute())
        else:
            # For MHTML (bytes), encode to base64 for JSON compatibility
            if isinstance(content, bytes):
                import base64
                result["content_base64"] = base64.b64encode(content).decode('utf-8')
            else:
                # Truncate large content in response
                if len(content) > 100000:
                    result["content"] = content[:100000]
                    result["truncated"] = True
                    result["full_size_chars"] = len(content)
                else:
                    result["content"] = content

        return result

    async def _capture_html(self, page) -> str:
        """Capture HTML content"""
        if self.selector:
            # Get HTML of specific element
            element = await page.query_selector(self.selector)
            if not element:
                raise ValueError(f"Element not found: {self.selector}")
            return await element.evaluate("el => el.outerHTML")
        else:
            # Get full page HTML
            return await page.content()

    async def _capture_mhtml(self, page) -> bytes:
        """Capture MHTML archive using CDP"""
        # MHTML always captures full page, selector is ignored
        cdp_session = await page.context.new_cdp_session(page)
        try:
            result = await cdp_session.send('Page.captureSnapshot', {'format': 'mhtml'})
            return result['data'].encode('utf-8')
        finally:
            await cdp_session.detach()

    async def _capture_text(self, page) -> str:
        """Capture text content"""
        if self.selector:
            # Get text of specific element
            element = await page.query_selector(self.selector)
            if not element:
                raise ValueError(f"Element not found: {self.selector}")
            return await element.inner_text()
        else:
            # Get full page text
            return await page.inner_text('body')
