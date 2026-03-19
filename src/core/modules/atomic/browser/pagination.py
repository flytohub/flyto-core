# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Pagination Module - Auto-paginate and extract data

Single responsibility: navigate pages + extract items.
For rate limiting → browser.throttle (place before this node in workflow)
For proxy rotation → browser.proxy_rotate
For concurrent scraping → browser.pool + flow.loop
"""
import asyncio
import logging
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


@register_module(
    module_id='browser.pagination',
    version='2.0.0',
    category='browser',
    tags=['browser', 'pagination', 'scrape', 'extract', 'automation', 'ssrf_protected'],
    label='Paginate & Extract',
    label_key='modules.browser.pagination.label',
    description='Auto-paginate through pages and extract data. Supports retry and checkpoint resume.',
    description_key='modules.browser.pagination.description',
    icon='ChevronRight',
    color='#F59E0B',

    input_types=['page'],
    output_types=['browser', 'page', 'array'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'array.*', 'string.*', 'object.*', 'file.*'],

    params_schema=compose(
        # ── Basic ────────────────────────────────────────────────
        field(
            'mode',
            type='select',
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
            group=FieldGroup.BASIC,
        ),
        field(
            'item_selector',
            type='string',
            label='Item Selector',
            label_key='modules.browser.pagination.params.item_selector.label',
            description='CSS selector for items to extract on each page',
            placeholder='.product-card, .list-item, tr.data-row',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'next_selector',
            type='string',
            label='Next Button Selector',
            label_key='modules.browser.pagination.params.next_selector.label',
            description='CSS selector for next page button',
            placeholder='.next, a[rel="next"], .pagination-next',
            required=False,
            showIf={"mode": {"$in": ["next_button", "page_numbers"]}},
            group=FieldGroup.BASIC,
        ),
        field(
            'load_more_selector',
            type='string',
            label='Load More Selector',
            label_key='modules.browser.pagination.params.load_more_selector.label',
            description='CSS selector for load more button',
            placeholder='.load-more, button.show-more',
            required=False,
            showIf={"mode": {"$in": ["load_more"]}},
            group=FieldGroup.BASIC,
        ),
        field(
            'fields',
            type='object',
            label='Fields to Extract',
            label_key='modules.browser.pagination.params.fields.label',
            description='Field definitions {name: {selector, attribute?}}',
            required=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'max_pages',
            type='number',
            label='Max Pages',
            label_key='modules.browser.pagination.params.max_pages.label',
            description='Maximum number of pages to process (0 = unlimited)',
            default=10,
            min=0,
            max=1000,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'max_items',
            type='number',
            label='Max Items',
            label_key='modules.browser.pagination.params.max_items.label',
            description='Stop after collecting this many items (0 = unlimited)',
            default=0,
            min=0,
            max=10000,
            step=1,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'wait_between_pages_ms',
            type='number',
            label='Wait Between Pages (ms)',
            label_key='modules.browser.pagination.params.wait_between_pages_ms.label',
            description='Fixed wait time between page navigations. For adaptive/human-like delays, use browser.throttle before this node.',
            default=1000,
            min=0,
            max=30000,
            group=FieldGroup.OPTIONS,
        ),

        # ── Retry ────────────────────────────────────────────────
        field(
            'retry_on_error',
            type='boolean',
            label='Retry on Error',
            description='Retry failed page extractions before giving up',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'max_retries',
            type='number',
            label='Max Retries Per Page',
            description='Maximum retry attempts per failed page',
            default=3,
            min=1,
            max=10,
            showIf={"retry_on_error": {"$in": [True]}},
            group=FieldGroup.ADVANCED,
        ),

        # ── Checkpoint ───────────────────────────────────────────
        field(
            'checkpoint_path',
            type='string',
            label='Checkpoint File',
            description='Save progress to disk. Resumes from checkpoint on restart. Cleared on successful completion.',
            placeholder='/tmp/flyto_scrape_checkpoint.json',
            format='path',
            required=False,
            group=FieldGroup.ADVANCED,
        ),

        # ── Other ────────────────────────────────────────────────
        field(
            'wait_for_selector',
            type='string',
            label='Wait For Selector',
            label_key='modules.browser.pagination.params.wait_for_selector.label',
            description='Wait for this element after page change',
            required=False,
            placeholder='#element or .class',
            group=FieldGroup.ADVANCED,
        ),
        field(
            'scroll_amount',
            type='number',
            label='Scroll Amount (px)',
            label_key='modules.browser.pagination.params.scroll_amount.label',
            description='Pixels to scroll for infinite scroll mode',
            default=1000,
            min=100,
            max=5000,
            showIf={"mode": {"$in": ["infinite_scroll"]}},
            group=FieldGroup.ADVANCED,
        ),
        field(
            'no_more_indicator',
            type='string',
            label='End Indicator Selector',
            label_key='modules.browser.pagination.params.no_more_indicator.label',
            description='Selector that appears when no more pages (stops pagination)',
            placeholder='.no-more-results, .end-of-list',
            required=False,
            group=FieldGroup.ADVANCED,
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
        },
        'retries_used': {
            'type': 'integer',
            'description': 'Total number of retries across all pages',
        },
        'resumed': {
            'type': 'boolean',
            'description': 'Whether execution resumed from a checkpoint',
        },
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
            'name': 'Infinite scroll with checkpoint',
            'params': {
                'mode': 'infinite_scroll',
                'item_selector': '.feed-item',
                'max_items': 100,
                'no_more_indicator': '.end-of-feed',
                'checkpoint_path': '/tmp/feed_checkpoint.json',
            }
        },
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=600000,  # 10 minutes for large multi-page operations
    required_permissions=['browser.automation'],
)
class BrowserPaginationModule(BaseModule):
    """
    Auto-pagination and data extraction module.

    Single responsibility: navigate pages + extract items.
    Includes retry (tightly coupled with extraction loop)
    and checkpoint (tightly coupled with pagination state).
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
        self.retry_on_error = self.params.get('retry_on_error', True)
        self.max_retries = self.params.get('max_retries', 3)
        self.checkpoint_path = self.params.get('checkpoint_path')

        if not self.item_selector:
            raise ValueError("item_selector is required")

        valid_modes = ['next_button', 'infinite_scroll', 'page_numbers', 'load_more']
        if self.mode not in valid_modes:
            raise ValueError(f"mode must be one of: {valid_modes}")

    async def execute(self) -> Dict[str, Any]:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # ── Load checkpoint if available ─────────────────────────
        checkpoint = None
        all_items = []
        pages_processed = 0
        total_retries = 0
        resumed = False

        if self.checkpoint_path:
            from core.browser.checkpoint import PaginationCheckpoint
            checkpoint = PaginationCheckpoint(
                self.checkpoint_path, self.item_selector, self.mode,
            )
            if checkpoint.exists():
                state = checkpoint.load()
                all_items = checkpoint.load_items()
                pages_processed = state.get('pages_processed', 0)
                total_retries = state.get('retries_used', 0)
                resumed = True
                logger.info(
                    f"Resuming from checkpoint: page {pages_processed}, "
                    f"{len(all_items)} items"
                )
                # Resume: goto saved URL directly (avoids re-navigating N pages)
                last_url = state.get('last_url')
                if last_url and last_url != 'about:blank':
                    try:
                        await browser.goto(last_url)
                        if self.wait_for_selector:
                            try:
                                await browser.wait(self.wait_for_selector, timeout_ms=10000)
                            except Exception:
                                pass
                        logger.info(f"Resumed directly to: {last_url}")
                    except Exception as e:
                        logger.warning(f"Direct resume failed, falling back to sequential: {e}")
                        # Fallback: navigate page by page (for sites without stable URLs)
                        for _ in range(pages_processed):
                            has_next = await self._navigate_next(browser)
                            if not has_next:
                                break
                            if self.wait_between_pages_ms > 0:
                                await asyncio.sleep(self.wait_between_pages_ms / 1000)

        stopped_reason = 'completed'

        try:
            while True:
                # Check max pages
                if self.max_pages > 0 and pages_processed >= self.max_pages:
                    stopped_reason = 'max_pages'
                    break

                # Extract items with retry
                items, retries = await self._extract_with_retry(browser)
                total_retries += retries

                if items is not None:
                    all_items.extend(items)
                    pages_processed += 1

                    # Save checkpoint after each page
                    if checkpoint:
                        checkpoint.save(
                            items=all_items,
                            pages_processed=pages_processed,
                            last_url=browser.page.url if hasattr(browser, 'page') else None,
                            retries_used=total_retries,
                        )
                else:
                    stopped_reason = 'error: extraction failed after retries'
                    if checkpoint:
                        checkpoint.save(
                            items=all_items,
                            pages_processed=pages_processed,
                            stopped_reason=stopped_reason,
                            retries_used=total_retries,
                        )
                    break

                # Check max items
                if self.max_items > 0 and len(all_items) >= self.max_items:
                    all_items = all_items[:self.max_items]
                    stopped_reason = 'max_items'
                    break

                # Check for end indicator
                if self.no_more_indicator:
                    end_reached = await browser.evaluate(
                        '(selector) => document.querySelector(selector) !== null',
                        self.no_more_indicator,
                    )
                    if end_reached:
                        stopped_reason = 'no_more'
                        break

                # Navigate to next page
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
            if checkpoint:
                checkpoint.save(
                    items=all_items,
                    pages_processed=pages_processed,
                    stopped_reason=stopped_reason,
                    retries_used=total_retries,
                )

        # Clear checkpoint on successful completion
        if checkpoint and not stopped_reason.startswith('error:'):
            checkpoint.clear()

        is_error = stopped_reason.startswith('error:')
        return {
            'status': 'error' if is_error and pages_processed == 0 else 'success',
            'items': all_items,
            'total_items': len(all_items),
            'pages_processed': pages_processed,
            'stopped_reason': stopped_reason,
            'retries_used': total_retries,
            'resumed': resumed,
        }

    # ── Extraction with Retry ────────────────────────────────────

    async def _extract_with_retry(self, browser):
        """Extract items with retry on failure.

        Returns:
            (items, retries_used) or (None, retries_used) if all retries failed.
        """
        last_error = None
        for attempt in range(1 + (self.max_retries if self.retry_on_error else 0)):
            try:
                items = await self._extract_items(browser)
                return items, attempt
            except Exception as e:
                last_error = e
                logger.warning(f"Extraction attempt {attempt + 1} failed: {e}")

                if not self.retry_on_error:
                    break

                # Brief delay before retry (exponential backoff, capped at 10s)
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))

        logger.error(f"All extraction retries exhausted: {last_error}")
        return None, self.max_retries if self.retry_on_error else 0

    # ── Item Extraction ──────────────────────────────────────────

    async def _extract_items(self, browser) -> List[Dict[str, Any]]:
        if self.fields:
            return await self._extract_with_fields(browser)
        else:
            return await self._extract_raw(browser)

    async def _extract_with_fields(self, browser) -> List[Dict[str, Any]]:
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

        script = '''
            ([itemSelector, fields]) => {
                const items = document.querySelectorAll(itemSelector);
                const results = [];
                items.forEach((item, idx) => {
                    const data = {};
                    fields.forEach(field => {
                        const el = item.querySelector(field.selector);
                        if (el) {
                            data[field.name] = field.attribute
                                ? el.getAttribute(field.attribute)
                                : el.textContent.trim();
                        } else {
                            data[field.name] = null;
                        }
                    });
                    data.__index = idx;
                    results.push(data);
                });
                return results;
            }
        '''
        return await browser.evaluate(script, [self.item_selector, field_configs])

    async def _extract_raw(self, browser) -> List[Dict[str, Any]]:
        script = '''
            (itemSelector) => {
                const items = document.querySelectorAll(itemSelector);
                return Array.from(items).map((item, idx) => ({
                    __index: idx,
                    text: item.textContent.trim(),
                    html: item.innerHTML
                }));
            }
        '''
        return await browser.evaluate(script, self.item_selector)

    # ── Navigation ───────────────────────────────────────────────

    async def _navigate_next(self, browser) -> bool:
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
        selectors = [self.next_selector] if self.next_selector else []
        selectors.extend(self.NEXT_BUTTON_SELECTORS)

        for selector in selectors:
            if not selector:
                continue
            try:
                can_click = await browser.evaluate('''
                    (selector) => {
                        const el = document.querySelector(selector);
                        if (!el) return false;
                        if (el.disabled) return false;
                        if (el.classList.contains('disabled')) return false;
                        if (el.getAttribute('aria-disabled') === 'true') return false;
                        return true;
                    }
                ''', selector)
                if can_click:
                    await browser.click(selector)
                    return True
            except Exception:
                continue
        return False

    async def _infinite_scroll(self, browser) -> bool:
        before_height = await browser.evaluate('document.body.scrollHeight')
        await browser.evaluate('(amount) => window.scrollBy(0, amount)', self.scroll_amount)
        await asyncio.sleep(1)
        after_height = await browser.evaluate('document.body.scrollHeight')
        return after_height > before_height

    async def _click_load_more(self, browser) -> bool:
        selector = self.load_more_selector or 'button.load-more, .load-more-btn, [data-action="load-more"]'
        try:
            exists = await browser.evaluate('''
                (selector) => {
                    const el = document.querySelector(selector);
                    return el && !el.disabled && el.offsetParent !== null;
                }
            ''', selector)
            if exists:
                await browser.click(selector)
                return True
        except Exception:
            pass
        return False

    async def _click_next_page_number(self, browser) -> bool:
        script = '''
            (() => {
                const current = document.querySelector('.pagination .active, .pagination .current');
                if (!current) return null;
                const next = current.nextElementSibling;
                if (next && (next.tagName === 'A' || next.tagName === 'BUTTON')) return next;
                return next?.querySelector('a, button');
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
