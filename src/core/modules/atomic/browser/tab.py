"""
Browser Tab Module

Create, switch, and close browser tabs.

SECURITY: Includes SSRF protection for new tab URLs.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field
from ....utils import validate_url_with_env_config, SSRFError


@register_module(
    module_id='browser.tab',
    version='1.0.0',
    category='browser',
    tags=['browser', 'tab', 'window', 'page', 'ssrf_protected'],
    label='Manage Tabs',
    label_key='modules.browser.tab.label',
    description='Create, switch, and close browser tabs',
    description_key='modules.browser.tab.description',
    icon='LayoutPanelTop',
    color='#6C757D',

    # Connection types
    input_types=['browser'],
    output_types=['page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.tab.params.action.label',
            description='Tab action to perform',
            required=True,
            options=[
                {'value': 'new', 'label': 'New Tab (create new)'},
                {'value': 'switch', 'label': 'Switch Tab (change focus)'},
                {'value': 'close', 'label': 'Close Tab'},
                {'value': 'list', 'label': 'List All Tabs'},
            ],
        ),
        presets.URL(required=False, placeholder='https://example.com'),
        field(
            'index',
            type='number',
            label='Tab Index',
            label_key='modules.browser.tab.params.index.label',
            description='Tab index to switch to or close (0-based)',
            required=False,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.tab.output.status.description'},
        'tab_count': {'type': 'number', 'description': 'The tab count',
                'description_key': 'modules.browser.tab.output.tab_count.description'},
        'current_index': {'type': 'number', 'description': 'The current index',
                'description_key': 'modules.browser.tab.output.current_index.description'},
        'tabs': {'type': 'array', 'description': 'List of open tabs',
                'description_key': 'modules.browser.tab.output.tabs.description'}
    },
    examples=[
        {
            'name': 'Open new tab with URL',
            'params': {'action': 'new', 'url': 'https://example.com'}
        },
        {
            'name': 'Switch to first tab',
            'params': {'action': 'switch', 'index': 0}
        },
        {
            'name': 'Close current tab',
            'params': {'action': 'close'}
        },
        {
            'name': 'List all tabs',
            'params': {'action': 'list'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserTabModule(BaseModule):
    """Manage Tabs Module"""

    module_name = "Manage Tabs"
    module_description = "Create, switch, and close browser tabs"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['new', 'switch', 'close', 'list']:
            raise ValueError(f"Invalid action: {self.action}")

        self.url = self.params.get('url')
        self.index = self.params.get('index')

        if self.action == 'switch' and self.index is None:
            raise ValueError("switch action requires index")

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

        if self.action == 'list':
            tabs = []
            for i, page in enumerate(pages):
                tabs.append({
                    'index': i,
                    'url': page.url,
                    'title': await page.title(),
                    'is_current': page == current_page
                })
            return {
                "status": "success",
                "tabs": tabs,
                "tab_count": len(tabs),
                "current_index": current_index
            }

        elif self.action == 'new':
            new_page = await context.new_page()
            if self.url:
                # SECURITY: Validate URL for SSRF before navigation
                try:
                    validate_url_with_env_config(self.url)
                except SSRFError as e:
                    await new_page.close()
                    return {
                        "status": "error",
                        "error": str(e),
                        "error_code": "SSRF_BLOCKED"
                    }
                await new_page.goto(self.url)

            # Update browser's current page reference
            browser._page = new_page

            return {
                "status": "success",
                "tab_count": len(context.pages),
                "current_index": len(context.pages) - 1,
                "url": self.url or "about:blank"
            }

        elif self.action == 'switch':
            if self.index < 0 or self.index >= len(pages):
                raise ValueError(f"Invalid tab index: {self.index}. Valid range: 0-{len(pages)-1}")

            # Update browser's current page reference
            browser._page = pages[self.index]
            await browser._page.bring_to_front()

            return {
                "status": "success",
                "tab_count": len(pages),
                "current_index": self.index,
                "url": pages[self.index].url
            }

        elif self.action == 'close':
            if self.index is not None:
                if self.index < 0 or self.index >= len(pages):
                    raise ValueError(f"Invalid tab index: {self.index}")
                page_to_close = pages[self.index]
            else:
                page_to_close = current_page

            await page_to_close.close()

            # Update current page if we closed it
            remaining_pages = context.pages
            if len(remaining_pages) > 0:
                if page_to_close == browser._page:
                    browser._page = remaining_pages[-1]

            return {
                "status": "success",
                "tab_count": len(remaining_pages),
                "current_index": len(remaining_pages) - 1 if remaining_pages else -1
            }
