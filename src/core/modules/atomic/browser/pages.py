"""
Browser Pages Module - List all browser pages/tabs

Lists all open browser pages with detailed information:
- URL and title
- Viewport dimensions
- Whether it's the current active page

Works across all browsers (Chromium, Firefox, WebKit).
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


@register_module(
    module_id='browser.pages',
    version='1.0.0',
    category='browser',
    tags=['browser', 'pages', 'tabs', 'list', 'debug'],
    label='List Pages',
    label_key='modules.browser.pages.label',
    description='List all open browser pages/tabs with details',
    description_key='modules.browser.pages.description',
    icon='Layers',
    color='#64748B',

    # Connection types
    input_types=['browser'],
    output_types=['array', 'json'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],

    params_schema=compose(
        field(
            'include_details',
            type='boolean',
            label='Include Details',
            label_key='modules.browser.pages.params.include_details.label',
            description='Include URL, title, and viewport info for each page',
            required=False,
            default=True,
        ),
        field(
            'include_content_info',
            type='boolean',
            label='Include Content Info',
            label_key='modules.browser.pages.params.include_content_info.label',
            description='Include page load state and frame count (slower)',
            required=False,
            default=False,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.pages.output.status.description'
        },
        'pages': {
            'type': 'array',
            'description': 'List of page information',
            'description_key': 'modules.browser.pages.output.pages.description'
        },
        'count': {
            'type': 'number',
            'description': 'Number of open pages',
            'description_key': 'modules.browser.pages.output.count.description'
        },
        'current_index': {
            'type': 'number',
            'description': 'Index of the current active page',
            'description_key': 'modules.browser.pages.output.current_index.description'
        },
    },
    examples=[
        {
            'name': 'List all pages with details',
            'params': {'include_details': True}
        },
        {
            'name': 'Quick page count',
            'params': {'include_details': False}
        },
        {
            'name': 'Full page info including content state',
            'params': {'include_details': True, 'include_content_info': True}
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=10000,
    required_permissions=['browser.automation'],
)
class BrowserPagesModule(BaseModule):
    """List Pages Module"""

    module_name = "List Pages"
    module_description = "List all open browser pages"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.include_details = self.params.get('include_details', True)
        self.include_content_info = self.params.get('include_content_info', False)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context
        pages = context.pages
        current_page = browser.page

        # Find current page index
        current_index = -1
        for i, page in enumerate(pages):
            if page == current_page:
                current_index = i
                break

        # Build page list
        page_list: List[Dict[str, Any]] = []

        for i, page in enumerate(pages):
            page_info: Dict[str, Any] = {
                'index': i,
                'is_current': page == current_page,
            }

            if self.include_details:
                page_info['url'] = page.url
                page_info['title'] = await page.title()

                viewport = page.viewport_size
                if viewport:
                    page_info['viewport'] = viewport
                else:
                    page_info['viewport'] = None

            if self.include_content_info:
                # Get additional content info
                try:
                    # Check if page is loaded
                    page_info['is_closed'] = page.is_closed()

                    # Frame count
                    page_info['frame_count'] = len(page.frames)

                    # Main frame URL (might differ from page.url for iframes)
                    page_info['main_frame_url'] = page.main_frame.url

                except Exception:
                    page_info['is_closed'] = True

            page_list.append(page_info)

        return {
            "status": "success",
            "pages": page_list,
            "count": len(page_list),
            "current_index": current_index,
        }
