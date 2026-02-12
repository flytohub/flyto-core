"""
Browser Pagination Module - Auto-paginate and extract data

Automatically handles pagination patterns including:
- Next button clicking
- Infinite scroll
- Page number navigation
- Load more buttons

Extracts data from each page and combines results.
"""
from typing import Any, Dict, List, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


@register_module(
    module_id='browser.pagination',
    version='1.0.0',
    category='browser',
    tags=['browser', 'pagination', 'scrape', 'extract', 'automation', 'ssrf_protected'],
    label='Paginate & Extract',
    label_key='modules.browser.pagination.label',
    description='Auto-paginate through pages and extract data',
    description_key='modules.browser.pagination.description',
    icon='ChevronRight',
    color='#F59E0B',

    input_types=['page'],
    output_types=['page', 'array'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'flow.*', 'data.*', 'array.*'],

    params_schema=compose(
        field(
            'mode',
            type='string',
            label='Pagination Mode',
            label_key='modules.browser.pagination.params.mode.label',
            description='How to navigate between pages',
            default='next_button',
            options=[
                {'value': 'next_button', 'label': 'Next Button (click to advance)'},
                {'value': 'infinite_scroll', 'label': 'Infinite Scroll (scroll to load)'},
                {'value': 'page_numbers', 'label': 'Page Numbers (numbered links)'},
                {'value': 'load_more', 'label': 'Load More (click button to append)'},
            ],
        ),
        field(
            'item_selector',
            type='string',
            label='Item Selector',
            label_key='modules.browser.pagination.params.item_selector.label',
            description='CSS selector for items to extract on each page',
            placeholder='.product-card, .list-item, tr.data-row',
            required=True,
        ),
        field(
            'fields',
            type='object',
            label='Fields to Extract',
            label_key='modules.browser.pagination.params.fields.label',
            description='Field definitions {name: {selector, attribute?}}',
            required=False,
        ),
        field(
            'next_selector',
            type='string',
            label='Next Button Selector',
            label_key='modules.browser.pagination.params.next_selector.label',
            description='CSS selector for next page button',
            placeholder='.next, a[rel="next"], .pagination-next',
            required=False,
        ),
        field(
            'load_more_selector',
            type='string',
            label='Load More Selector',
            label_key='modules.browser.pagination.params.load_more_selector.label',
            description='CSS selector for load more button',
            placeholder='.load-more, button.show-more',
            required=False,
        ),
        field(
            'max_pages',
            type='integer',
            label='Max Pages',
            label_key='modules.browser.pagination.params.max_pages.label',
            description='Maximum number of pages to process (0 = unlimited)',
            default=10,
            min=0,
            max=1000,
        ),
        field(
            'max_items',
            type='integer',
            label='Max Items',
            label_key='modules.browser.pagination.params.max_items.label',
            description='Stop after collecting this many items (0 = unlimited)',
            default=0,
            min=0,
        ),
        field(
            'wait_between_pages_ms',
            type='integer',
            label='Wait Between Pages (ms)',
            label_key='modules.browser.pagination.params.wait_between_pages_ms.label',
            description='Wait time between page navigations',
            default=1000,
            min=0,
            max=10000,
        ),
        field(
            'wait_for_selector',
            type='string',
            label='Wait For Selector',
            label_key='modules.browser.pagination.params.wait_for_selector.label',
            description='Wait for this element after page change',
            required=False,
            placeholder='#element or .class',
        ),
        field(
            'scroll_amount',
            type='integer',
            label='Scroll Amount (px)',
            label_key='modules.browser.pagination.params.scroll_amount.label',
            description='Pixels to scroll for infinite scroll mode',
            default=1000,
            min=100,
            max=5000,
        ),
        field(
            'no_more_indicator',
            type='string',
            label='End Indicator Selector',
            label_key='modules.browser.pagination.params.no_more_indicator.label',
            description='Selector that appears when no more pages (stops pagination)',
            placeholder='.no-more-results, .end-of-list',
            required=False,
        ),
    ),
    output_schema={
        'items': {
            'type': 'array',
            'description': 'All extracted items from all pages',
            'description_key': 'modules.browser.pagination.output.items.description'
        },
        'total_items': {
            'type': 'integer',
            'description': 'Total number of items extracted',
            'description_key': 'modules.browser.pagination.output.total_items.description'
        },
        'pages_processed': {
            'type': 'integer',
            'description': 'Number of pages processed',
            'description_key': 'modules.browser.pagination.output.pages_processed.description'
        },
        'stopped_reason': {
            'type': 'string',
            'description': 'Why pagination stopped (max_pages, max_items, no_more, error)',
            'description_key': 'modules.browser.pagination.output.stopped_reason.description'
        }
    },
    examples=[
        {
            'name': 'Paginate product list',
            'params': {
                'mode': 'next_button',
                'item_selector': '.product-card',
                'fields': {
                    'title': {'selector': '.title'},
                    'price': {'selector': '.price'},
                    'link': {'selector': 'a', 'attribute': 'href'}
                },
                'next_selector': '.pagination .next',
                'max_pages': 5
            }
        },
        {
            'name': 'Infinite scroll feed',
            'params': {
                'mode': 'infinite_scroll',
                'item_selector': '.feed-item',
                'fields': {
                    'content': {'selector': '.content'},
                    'author': {'selector': '.author'}
                },
                'max_items': 100,
                'no_more_indicator': '.end-of-feed'
            }
        },
        {
            'name': 'Load more button',
            'params': {
                'mode': 'load_more',
                'item_selector': '.list-item',
                'load_more_selector': 'button.load-more',
                'max_pages': 10
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,  # 5 minutes for multi-page operations
    required_permissions=['browser.automation'],
)
class BrowserPaginationModule(BaseModule):
    """
    Auto-pagination and data extraction module.

    Handles various pagination patterns and extracts data
    from each page, combining all results.
    """

    module_name = "Paginate & Extract"
    module_description = "Auto-paginate through pages and extract data"
    required_permission = "browser.automation"

    NEXT_BUTTON_SELECTORS = [
        'a[rel="next"]',
        '.pagination .next',
        '.pagination-next',
        'button.next',
        'a.next',
        '[aria-label="Next"]',
        '.pager-next',
    ]

    def validate_params(self) -> None:
        self.mode = self.params.get('mode', 'next_button')
        self.item_selector = self.params.get('item_selector')
        self.fields = self.params.get('fields', {})
        self.next_selector = self.params.get('next_selector')
        self.load_more_selector = self.params.get('load_more_selector')
        self.max_pages = self.params.get('max_pages', 10)
        self.max_items = self.params.get('max_items', 0)
        self.wait_between_pages_ms = self.params.get('wait_between_pages_ms', 1000)
        self.wait_for_selector = self.params.get('wait_for_selector')
        self.scroll_amount = self.params.get('scroll_amount', 1000)
        self.no_more_indicator = self.params.get('no_more_indicator')

        if not self.item_selector:
            raise ValueError("item_selector is required")

        valid_modes = ['next_button', 'infinite_scroll', 'page_numbers', 'load_more']
        if self.mode not in valid_modes:
            raise ValueError(f"mode must be one of: {valid_modes}")

    async def execute(self) -> Dict[str, Any]:
        import asyncio

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        all_items = []
        pages_processed = 0
        stopped_reason = 'completed'

        try:
            while True:
                # Check max pages
                if self.max_pages > 0 and pages_processed >= self.max_pages:
                    stopped_reason = 'max_pages'
                    break

                # Extract items from current page
                items = await self._extract_items(browser)
                all_items.extend(items)
                pages_processed += 1

                # Check max items
                if self.max_items > 0 and len(all_items) >= self.max_items:
                    all_items = all_items[:self.max_items]
                    stopped_reason = 'max_items'
                    break

                # Check for end indicator
                if self.no_more_indicator:
                    end_reached = await browser.evaluate(f'''
                        document.querySelector("{self.no_more_indicator}") !== null
                    ''')
                    if end_reached:
                        stopped_reason = 'no_more'
                        break

                # Navigate to next page based on mode
                has_next = await self._navigate_next(browser)
                if not has_next:
                    stopped_reason = 'no_more'
                    break

                # Wait between pages
                if self.wait_between_pages_ms > 0:
                    await asyncio.sleep(self.wait_between_pages_ms / 1000)

                # Wait for content to load
                if self.wait_for_selector:
                    try:
                        await browser.wait(self.wait_for_selector, timeout_ms=10000)
                    except Exception:
                        pass

        except Exception as e:
            stopped_reason = f'error: {str(e)}'

        return {
            'ok': True,
            'data': {
                'items': all_items,
                'total_items': len(all_items),
                'pages_processed': pages_processed,
                'stopped_reason': stopped_reason
            }
        }

    async def _extract_items(self, browser) -> List[Dict[str, Any]]:
        """Extract items from current page."""
        if self.fields:
            # Extract with field definitions
            return await self._extract_with_fields(browser)
        else:
            # Extract raw elements
            return await self._extract_raw(browser)

    async def _extract_with_fields(self, browser) -> List[Dict[str, Any]]:
        """Extract items using field definitions."""
        field_configs = []
        for name, config in self.fields.items():
            if isinstance(config, str):
                field_configs.append({'name': name, 'selector': config, 'attribute': None})
            else:
                field_configs.append({
                    'name': name,
                    'selector': config.get('selector', ''),
                    'attribute': config.get('attribute')
                })

        script = f'''
            (() => {{
                const items = document.querySelectorAll("{self.item_selector}");
                const fields = {field_configs};
                const results = [];

                items.forEach((item, idx) => {{
                    const data = {{}};
                    fields.forEach(field => {{
                        const el = item.querySelector(field.selector);
                        if (el) {{
                            if (field.attribute) {{
                                data[field.name] = el.getAttribute(field.attribute);
                            }} else {{
                                data[field.name] = el.textContent.trim();
                            }}
                        }} else {{
                            data[field.name] = null;
                        }}
                    }});
                    data.__index = idx;
                    results.push(data);
                }});

                return results;
            }})()
        '''

        return await browser.evaluate(script)

    async def _extract_raw(self, browser) -> List[Dict[str, Any]]:
        """Extract raw text content from items."""
        script = f'''
            (() => {{
                const items = document.querySelectorAll("{self.item_selector}");
                return Array.from(items).map((item, idx) => ({{
                    __index: idx,
                    text: item.textContent.trim(),
                    html: item.innerHTML
                }}));
            }})()
        '''
        return await browser.evaluate(script)

    async def _navigate_next(self, browser) -> bool:
        """Navigate to next page based on mode."""
        if self.mode == 'next_button':
            return await self._click_next_button(browser)
        elif self.mode == 'infinite_scroll':
            return await self._infinite_scroll(browser)
        elif self.mode == 'load_more':
            return await self._click_load_more(browser)
        elif self.mode == 'page_numbers':
            return await self._click_next_page_number(browser)
        return False

    async def _click_next_button(self, browser) -> bool:
        """Click next page button."""
        selectors = [self.next_selector] if self.next_selector else []
        selectors.extend(self.NEXT_BUTTON_SELECTORS)

        for selector in selectors:
            if not selector:
                continue
            try:
                # Check if button exists and is not disabled
                can_click = await browser.evaluate(f'''
                    (() => {{
                        const el = document.querySelector("{selector}");
                        if (!el) return false;
                        if (el.disabled) return false;
                        if (el.classList.contains('disabled')) return false;
                        if (el.getAttribute('aria-disabled') === 'true') return false;
                        return true;
                    }})()
                ''')
                if can_click:
                    await browser.click(selector)
                    return True
            except Exception:
                continue

        return False

    async def _infinite_scroll(self, browser) -> bool:
        """Scroll down for infinite scroll pagination."""
        # Get current scroll position and document height
        before_height = await browser.evaluate('document.body.scrollHeight')

        # Scroll down
        await browser.evaluate(f'window.scrollBy(0, {self.scroll_amount})')

        # Wait a bit for content to load
        import asyncio
        await asyncio.sleep(1)

        # Check if new content loaded
        after_height = await browser.evaluate('document.body.scrollHeight')

        return after_height > before_height

    async def _click_load_more(self, browser) -> bool:
        """Click load more button."""
        selector = self.load_more_selector or 'button.load-more, .load-more-btn, [data-action="load-more"]'

        try:
            exists = await browser.evaluate(f'''
                (() => {{
                    const el = document.querySelector("{selector}");
                    return el && !el.disabled && el.offsetParent !== null;
                }})()
            ''')
            if exists:
                await browser.click(selector)
                return True
        except Exception:
            pass

        return False

    async def _click_next_page_number(self, browser) -> bool:
        """Click next page number in pagination."""
        # Find current page and click next number
        script = '''
            (() => {
                const current = document.querySelector('.pagination .active, .pagination .current');
                if (!current) return null;

                const next = current.nextElementSibling;
                if (next && next.tagName === 'A' || next.tagName === 'BUTTON') {
                    return next;
                }

                const nextLink = next?.querySelector('a, button');
                return nextLink;
            })()
        '''
        next_el = await browser.evaluate(script)

        if next_el:
            try:
                await browser.evaluate('''
                    (() => {
                        const current = document.querySelector('.pagination .active, .pagination .current');
                        const next = current?.nextElementSibling;
                        const link = next?.querySelector('a, button') || next;
                        if (link) link.click();
                    })()
                ''')
                return True
            except Exception:
                pass

        return False
