# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Pages Module - List all browser pages/tabs

Lists all open browser pages with detailed information:
- URL and title
- Viewport dimensions
- Whether it's the current active page

Works across all browsers (Chromium, Firefox, WebKit).

WHAT A LISTING OBSERVED DEPENDS ON WHAT IT ASKED

This is an extraction module, and the brief for one is that the things it found
in the live browser are the things it observed. But it has two modes and they do
not measure the same amount:

    include_details=True    every page is asked for its title, which is a
                            protocol round trip into that page. A page that
                            answers is a page that exists right now.  OBSERVED
    include_details=False   only len(context.pages) and object identity are
                            read. That list is Playwright's, kept up to date
                            from target events, and a page that crashed a
                            moment ago is still in it.                ACCEPTED
    no pages at all         the `database.query` empty read: zero reads the
                            same whether the browser has no pages or this is
                            the wrong context.                        ACCEPTED

The rung is therefore decided per call, from what this run actually did, rather
than fixed per module — the same reason `database.query` decides its rung from
whether a row count crossed the wire on that particular statement.
"""
from typing import Any, Dict, List

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


def _pages_outcome(*, page_count: int, round_tripped: bool) -> Dict[str, Any]:
    """The rung this listing earned, from how deeply it looked."""
    if page_count <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_pages_listed',
                'measured_by': None,
                'detail': (
                    'The context reports no pages. An empty listing is not an '
                    'observation of the browser: it reads the same whether '
                    'there are no pages or this is not the context the caller '
                    'meant.'
                ),
            }],
        )

    if not round_tripped:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'pages_counted',
                'count': page_count,
                'measured_by': 'len(BrowserContext.pages)',
                'detail': (
                    'include_details was false, so nothing was asked of any '
                    'page. This count comes from the list Playwright maintains '
                    "from the browser's target events — accurate as of the last "
                    'event, and unchanged for a page that has since crashed.'
                ),
            }],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'pages_read',
            'count': page_count,
            'measured_by': (
                'page.title() round-tripped to each page, with page.url and '
                'page.viewport_size read from it'
            ),
            'detail': (
                'Every page listed answered a protocol call. What is observed '
                'is the pages that exist, not that any particular one should.'
            ),
        }],
    )


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
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

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
        'outcome': {
            'type': 'object',
            'description': (
                'How far this listing looked: observed when every page was '
                'round-tripped for its title, accepted when only the page count '
                'was read or the context reports none'
            ),
            'description_key': 'modules.browser.pages.output.outcome.description'
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
    author='Flyto2 Team',
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
            "outcome": _pages_outcome(
                page_count=len(page_list),
                # page.title() above is a protocol round trip; without it this
                # module never speaks to a page at all.
                round_tripped=bool(self.include_details),
            ),
        }
