# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Tab Module

Create, switch, and close browser tabs.

SECURITY: Includes SSRF protection for new tab URLs.

FOUR ACTIONS, FOUR DIFFERENT ANSWERS

``context.pages`` is the measurement this module was already standing next to
and never used as one. Playwright builds that list from target events the
browser sends, so a length read before an action and again after it is a
read-back of the browser's own inventory — the same shape `browser.close` uses
for ``Browser.is_connected()`` and `browser.type` uses for ``input_value``.

    new      pages_after == pages_before + 1                      OBSERVED
             the count did not grow                               INDETERMINATE
             a URL was requested and the SSRF guard refused it    FAILED
    close    the count fell by one and Page.is_closed() agrees    OBSERVED
             either disagrees                                     INDETERMINATE
    list     pages were read, each answering page.title()         OBSERVED
             the context reports no pages at all                  ACCEPTED
    switch   bring_to_front() returned                            ACCEPTED

``url`` on the `new` path used to be ``self.url or "about:blank"`` — the
parameter, echoed. It is now ``new_page.url``, read from the page after the
navigation, and the response status rides in the envelope beside it. A redirect,
a 404 or a meta-refresh all change the first and not the second.

WHY `switch` STOPS AT ACCEPTED, AND WHAT WAS TRIED

The obvious candidate for OBSERVED was reading the pages back after
``bring_to_front()``. Measured on the Chromium this repo drives (151.0.7922.34,
headless), with two tabs open and either one brought to front:

    document.visibilityState  ->  'visible' for BOTH pages, always
    document.hasFocus()       ->  True for BOTH pages, always

The predicate does not discriminate, so shipping it would have marked every
switch OBSERVED including the ones that did nothing — the mirror image of
`browser.hover`, where the predicate read false for every hover including the
ones that worked. Both are the same mistake. What is left is real but small:
the CDP command was sent and the browser answered it without raising, which is
ACCEPTED and exactly ACCEPTED. The measurement is pinned as a test.

The SSRF path is FAILED rather than off-ladder-silent because the distinction
matters to a consumer: the tab was opened, the caller's URL was refused before
any navigation was dispatched, and the tab was closed again. It did not happen,
and we know it did not happen. ``claim_by`` is CALLER — the URL was theirs.
"""
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import SSRFError, validate_url_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


def _tab_opened_outcome(
    *,
    pages_before: int,
    pages_after: int,
    requested_url: Optional[str],
    landed_url: Optional[str],
    status_code: Optional[int],
) -> Dict[str, Any]:
    """The rung a new tab earned, from the context's own page count."""
    counted = {
        'kind': 'tab_opened',
        'pages_before': pages_before,
        'pages_after': pages_after,
        'measured_by': (
            'len(BrowserContext.pages), read before and after '
            'context.new_page() — the list Playwright builds from the '
            "browser's target events"
        ),
    }

    if pages_after != pages_before + 1:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                **counted,
                'predicate': 'len(context.pages) == len(context.pages before) + 1',
                'detail': (
                    'new_page() returned and the context does not report one '
                    'more page than it had. A tab closing in the same instant '
                    'and a tab that never opened read alike here, so this is '
                    'indeterminate rather than failed.'
                ),
            }],
        )

    effects = [counted]
    if requested_url:
        if isinstance(status_code, int) and not isinstance(status_code, bool):
            effects.append({
                'kind': 'navigation_response',
                'status_code': status_code,
                'requested_url': requested_url,
                'landed_url': landed_url,
                'measured_by': 'Response.status from new_page.goto(), with page.url read back after it',
            })
        else:
            effects.append({
                'kind': 'navigation_not_measured',
                'requested_url': requested_url,
                'landed_url': landed_url,
                'measured_by': None,
                'detail': (
                    'goto() returned no response object — a same-document or '
                    'about: navigation. The tab exists; where it ended up is '
                    'only what page.url now says.'
                ),
            })
    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=effects)


def _tab_blocked_outcome(url: str, reason: str) -> Dict[str, Any]:
    """The rung a refused navigation earned. It did not happen, and we know it."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.CALLER,
        effects=[{
            'kind': 'navigation_refused',
            'requested_url': url,
            'reason': reason,
            'measured_by': 'validate_url_with_env_config, before any request left this process',
            'detail': (
                'A tab was opened, the caller\'s URL was refused by the egress '
                'guard, and the tab was closed again. Nothing was dispatched to '
                'the network, so this is a broken contract rather than an '
                'unknown one.'
            ),
        }],
    )


def _tab_closed_outcome(
    *, pages_before: int, pages_after: int, is_closed: Optional[bool]
) -> Dict[str, Any]:
    """The rung a closed tab earned, from the count and the page's own flag."""
    counted = {
        'kind': 'tab_closed',
        'pages_before': pages_before,
        'pages_after': pages_after,
        'page_reports_closed': is_closed,
        'measured_by': (
            'len(BrowserContext.pages) read before and after page.close(), '
            'and Page.is_closed() on the page that was closed'
        ),
    }
    if is_closed and pages_after == pages_before - 1:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[counted])
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            **counted,
            'predicate': 'page.is_closed() and len(context.pages) fell by one',
            'detail': (
                'close() returned and the two readings do not agree that the '
                'tab is gone. We cannot say whether it closed, so this is not '
                'a failure — only an unconfirmed close.'
            ),
        }],
    )


def _tab_list_outcome(tab_count: int) -> Dict[str, Any]:
    """Listing tabs is an extraction: the tabs found are the tabs observed.

    Finding none is the `database.query` empty-read: a context reporting zero
    pages reads the same whether it truly has none or we asked a context that
    is not the one the caller means.
    """
    if tab_count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_tabs_listed',
                'measured_by': None,
                'detail': (
                    'The context reports no pages. That is not an observation '
                    'of the browser: an empty list reads the same whether the '
                    'browser has no tabs or this is the wrong context.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'tabs_listed',
            'count': tab_count,
            'measured_by': (
                'len(BrowserContext.pages), with page.title() round-tripped to '
                'each page and page.url read from it'
            ),
        }],
    )


def _tab_switched_outcome(*, index: int, tab_count: int, url: str) -> Dict[str, Any]:
    """ACCEPTED, and no further. See the module docstring for what was measured
    and rejected."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'bring_to_front_acknowledged',
            'index': index,
            'tab_count': tab_count,
            'url': url,
            'measured_by': 'Page.bring_to_front() returned without raising',
            'detail': (
                'The browser took the activation command. Nothing readable '
                'changes: measured on this Chromium, document.visibilityState '
                "is 'visible' and document.hasFocus() is True for every open "
                'page whichever one was brought to front, so no predicate here '
                'can tell a switch that worked from one that did nothing.'
            ),
        }],
    )


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
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
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
        presets.SSRF_PROTECTION(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.tab.output.status.description'},
        'tab_count': {'type': 'number', 'description': 'The tab count',
                'description_key': 'modules.browser.tab.output.tab_count.description'},
        'current_index': {'type': 'number', 'description': 'The current index',
                'description_key': 'modules.browser.tab.output.current_index.description'},
        'tabs': {'type': 'array', 'description': 'List of open tabs',
                'description_key': 'modules.browser.tab.output.tabs.description'},
        'url': {'type': 'string', 'description': 'Where the tab actually is, read back from the page after the action',
                'description_key': 'modules.browser.tab.output.url.description'},
        'status_code': {'type': 'number', 'description': 'HTTP status of a new tab\'s navigation, or null when there was no response object',
                'description_key': 'modules.browser.tab.output.status_code.description'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed, decided per action: observed when '
            'the context\'s page count moved as it should, indeterminate when '
            'it did not, accepted for a switch (nothing readable changes) and '
            'for an empty tab list, failed when the egress guard refused the URL'
        ),
                'description_key': 'modules.browser.tab.output.outcome.description'}
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
                "current_index": current_index,
                "outcome": _tab_list_outcome(len(tabs)),
            }

        elif self.action == 'new':
            pages_before = len(context.pages)
            new_page = await context.new_page()
            status_code = None
            if self.url:
                # SECURITY: Outbound policy is operator-controlled. The legacy
                # ssrf_protection parameter remains accepted for compatibility,
                # but untrusted workflow input cannot disable this boundary.
                try:
                    validate_url_with_env_config(self.url)
                except SSRFError as e:
                    await new_page.close()
                    return {
                        "status": "error",
                        "error": str(e),
                        "error_code": "SSRF_BLOCKED",
                        "outcome": _tab_blocked_outcome(self.url, str(e)),
                    }
                response = await new_page.goto(self.url)
                status_code = getattr(response, 'status', None) if response else None

            # Update browser's current page reference
            browser._page = new_page

            # page.url is where the tab actually is; self.url is where it was
            # asked to go. A redirect makes those different.
            landed_url = new_page.url

            return {
                "status": "success",
                "tab_count": len(context.pages),
                "current_index": len(context.pages) - 1,
                "url": landed_url,
                "requested_url": self.url,
                "status_code": status_code,
                "outcome": _tab_opened_outcome(
                    pages_before=pages_before,
                    pages_after=len(context.pages),
                    requested_url=self.url,
                    landed_url=landed_url,
                    status_code=status_code,
                ),
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
                "url": pages[self.index].url,
                "outcome": _tab_switched_outcome(
                    index=self.index,
                    tab_count=len(pages),
                    url=pages[self.index].url,
                ),
            }

        elif self.action == 'close':
            if self.index is not None:
                if self.index < 0 or self.index >= len(pages):
                    raise ValueError(f"Invalid tab index: {self.index}")
                page_to_close = pages[self.index]
            else:
                page_to_close = current_page

            pages_before = len(context.pages)
            await page_to_close.close()

            # Update current page if we closed it
            remaining_pages = context.pages
            if remaining_pages and page_to_close == browser._page:
                browser._page = remaining_pages[-1]

            try:
                is_closed = page_to_close.is_closed()
            except Exception:  # noqa: BLE001 - any failure means "cannot look"
                is_closed = None

            return {
                "status": "success",
                "tab_count": len(remaining_pages),
                "current_index": len(remaining_pages) - 1 if remaining_pages else -1,
                "outcome": _tab_closed_outcome(
                    pages_before=pages_before,
                    pages_after=len(remaining_pages),
                    is_closed=is_closed,
                ),
            }
