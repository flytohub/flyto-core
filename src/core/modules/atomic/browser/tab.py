"""
Browser Tab Module

Create, switch, and close browser tabs.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='core.browser.tab',
    version='1.0.0',
    category='browser',
    tags=['browser', 'tab', 'window', 'page'],
    label='Manage Tabs',
    label_key='modules.browser.tab.label',
    description='Create, switch, and close browser tabs',
    description_key='modules.browser.tab.description',
    icon='LayoutPanelTop',
    color='#6C757D',

    # Connection types
    input_types=['browser'],
    output_types=['page'],

    params_schema={
        'action': {
            'type': 'string',
            'label': 'Action',
            'label_key': 'modules.browser.tab.params.action.label',
            'description': 'Tab action to perform',
            'description_key': 'modules.browser.tab.params.action.description',
            'required': True,
            'enum': ['new', 'switch', 'close', 'list']
        },
        'url': {
            'type': 'string',
            'label': 'URL',
            'label_key': 'modules.browser.tab.params.url.label',
            'placeholder': 'https://example.com',
            'description': 'URL to open in new tab (for new action)',
            'description_key': 'modules.browser.tab.params.url.description',
            'required': False
        },
        'index': {
            'type': 'number',
            'label': 'Tab Index',
            'label_key': 'modules.browser.tab.params.index.label',
            'description': 'Tab index to switch to or close (0-based)',
            'description_key': 'modules.browser.tab.params.index.description',
            'required': False
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'tab_count': {'type': 'number'},
        'current_index': {'type': 'number'},
        'tabs': {'type': 'array'}
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
    license='MIT'
)
class BrowserTabModule(BaseModule):
    """Manage Tabs Module"""

    module_name = "Manage Tabs"
    module_description = "Create, switch, and close browser tabs"
    required_permission = "browser.interact"

    def validate_params(self):
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
