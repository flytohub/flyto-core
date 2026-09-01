# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Navigation Module - Go back, forward, or reload the page

GOING BACK WITH NOWHERE TO GO REPORTED SUCCESS

``page.go_back()`` returns the navigation's ``Response``, or ``None`` when there
was no history entry to move to. This module discarded that return value and
reported ``{"status": "success", "url": page.url}`` either way — and ``page.url``
is unchanged when nothing happened, so both fields agreed with each other and
with nothing else. Measured against a local server: two navigations, then
``go_forward`` twice; the second returns ``None``, the URL does not move, and
the old code called it a success.

Two readings decide the rung, both taken from the page:

    Response.status         the status of the document the browser fetched
    page.url before/after   read either side of the call

    a response object came back                   OBSERVED (with its status)
    no response, but the URL moved                OBSERVED — a same-document
                                                  navigation. `go_back` over a
                                                  '#fragment' does exactly this:
                                                  returns None, changes the URL.
    no response and the URL did not move          INDETERMINATE

The last row is INDETERMINATE rather than FAILED for the reason `outcome.py`
separates them: nobody declared a contract here, and "there was no history
entry" and "a same-document navigation landed back on the same URL" produce the
identical pair of readings. For ``reload`` the URL never moves by definition, so
only a response object lifts that action off the bottom — an about:blank reload
returns None and is honestly indeterminate.
"""
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


def _navigation_outcome(
    *,
    action: str,
    status_code: Optional[int],
    url_before: str,
    url_after: str,
) -> Dict[str, Any]:
    """The rung this history move earned, from the response and the address."""
    # `isinstance(True, int)` is True in Python, so a bool has to be excluded
    # explicitly or it would sail through as a status code.
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'navigation_response',
                'action': action,
                'status_code': status_code,
                'url_before': url_before,
                'url_after': url_after,
                'measured_by': f'Response.status returned by page.{_call_for(action)}()',
                'detail': (
                    'The browser fetched a document and the server answered. '
                    'A non-2xx status is still an observation — the rung says '
                    'how far the effect was followed, not whether we liked it.'
                ),
            }],
        )

    if url_after != url_before:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'same_document_navigation',
                'action': action,
                'url_before': url_before,
                'url_after': url_after,
                'measured_by': 'page.url, read before and after the call',
                'detail': (
                    'No response object, so no document was fetched, but the '
                    'address the page reports has changed. That is a '
                    'same-document navigation — moving across a #fragment '
                    'entry does exactly this — and it happened in the browser.'
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'navigation_not_observed',
            'action': action,
            'url_before': url_before,
            'url_after': url_after,
            'measured_by': None,
            'predicate': 'a Response came back, or page.url moved',
            'detail': (
                'Neither reading moved. For back and forward that is what an '
                'empty history looks like — the call returns None and the page '
                'stays put — and it is also what a same-document navigation '
                'onto the same URL looks like. For reload the URL never moves '
                'by definition, so a missing response leaves nothing to see. '
                'This step reported plain success in all of those cases.'
            ),
        }],
    )


def _call_for(action: str) -> str:
    return {'back': 'go_back', 'forward': 'go_forward'}.get(action, 'reload')


@register_module(
    module_id='browser.navigation',
    version='1.0.0',
    category='browser',
    tags=['browser', 'navigation', 'back', 'forward', 'reload', 'ssrf_protected'],
    label='Page Navigation',
    label_key='modules.browser.navigation.label',
    description='Navigate back, forward, or reload the page',
    description_key='modules.browser.navigation.description',
    icon='ArrowLeftRight',
    color='#5CB85C',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    # Schema-driven params
    params_schema=compose(
        field('action', type='select',
              label='Navigation Action',
              label_key='modules.browser.navigation.param.action.label',
              description='Which navigation action to perform',
              description_key='modules.browser.navigation.param.action.description',
              required=True,
              default='reload',
              options=[
                  {"value": "back", "label": "Go Back",
                   "label_key": "modules.browser.navigation.param.action.option.back"},
                  {"value": "forward", "label": "Go Forward",
                   "label_key": "modules.browser.navigation.param.action.option.forward"},
                  {"value": "reload", "label": "Reload Page",
                   "label_key": "modules.browser.navigation.param.action.option.reload"},
              ]),
        presets.WAIT_CONDITION(default='domcontentloaded'),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.navigation.output.status.description'},
        'action': {'type': 'string', 'description': 'Navigation action performed',
                'description_key': 'modules.browser.navigation.output.action.description'},
        'url': {'type': 'string', 'description': 'Current URL after navigation',
                'description_key': 'modules.browser.navigation.output.url.description'},
        'previous_url': {'type': 'string', 'description': 'URL the page reported before the call',
                'description_key': 'modules.browser.navigation.output.previous_url.description'},
        'status_code': {'type': 'number', 'description': 'HTTP status of the document fetched, or null when no navigation response came back',
                'description_key': 'modules.browser.navigation.output.status_code.description'},
        'outcome': {'type': 'object', 'description': (
            'How far the navigation was followed: observed when a response came '
            'back or the URL moved, indeterminate when neither did — which is '
            'what back or forward with no history entry looks like'
        ),
                'description_key': 'modules.browser.navigation.output.outcome.description'},
    },
    examples=[
        {
            'name': 'Go back to previous page',
            'params': {'action': 'back'}
        },
        {
            'name': 'Go forward',
            'params': {'action': 'forward'}
        },
        {
            'name': 'Reload current page',
            'params': {'action': 'reload', 'wait_until': 'networkidle'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserNavigationModule(BaseModule):
    """Page Navigation Module"""

    module_name = "Page Navigation"
    module_description = "Navigate back, forward, or reload the page"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['back', 'forward', 'reload']:
            raise ValueError(f"Invalid action: {self.action}. Must be 'back', 'forward', or 'reload'")

        self.wait_until = self.params.get('wait_until', 'domcontentloaded')
        self.timeout_ms = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Read either side of the call. `url_before` is what makes a
        # same-document navigation visible when no response comes back.
        url_before = page.url

        response = None
        if self.action == 'back':
            response = await page.go_back(wait_until=self.wait_until, timeout=self.timeout_ms)
        elif self.action == 'forward':
            response = await page.go_forward(wait_until=self.wait_until, timeout=self.timeout_ms)
        elif self.action == 'reload':
            response = await page.reload(wait_until=self.wait_until, timeout=self.timeout_ms)

        current_url = page.url
        status_code = getattr(response, 'status', None) if response else None

        # Post-navigation: invalidate and refresh hints — page content changed
        await browser.invalidate_hints(clear_stamps=True)
        result = {
            "status": "success",
            "action": self.action,
            "url": current_url,
            "previous_url": url_before,
            "status_code": status_code,
            "outcome": _navigation_outcome(
                action=self.action,
                status_code=status_code,
                url_before=url_before,
                url_after=current_url,
            ),
        }
        hints = await browser.get_hints(force=True)
        browser._snapshot_since_nav = True
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
