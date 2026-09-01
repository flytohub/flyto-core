# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Connect Module — Connect to remote browser services

Connect to cloud browser providers for:
- Real browser fingerprints (bypass Cloudflare, Akamai)
- Residential IP + real Chrome = undetectable
- Scale to hundreds of concurrent sessions

Supported services:
- Browserless.io (ws://...)
- BrowserBase (wss://connect.browserbase.com)
- Any Playwright-compatible CDP endpoint
- Self-hosted (Docker browserless)

``connected: True`` IS A LITERAL

It is the same defect `browser.storage` had: a boolean written in this file, on
the line after the connect, reporting the value it was born with. The two
things this module can actually read from the far end are

  * ``Browser.version`` — the remote's own build string, arriving through the
    CDP handshake. Measured against a local Chromium started with
    ``--remote-debugging-port``: the endpoint's ``/json/version`` said
    ``HeadlessChrome/151.0.7922.34`` and ``Browser.version`` said
    ``151.0.7922.34``. Nothing we sent contributes to it.
  * the remote's target inventory — how many contexts it has, and how many
    pages are in the one we adopt. Playwright builds those lists from target
    events the remote sends, not from our bookkeeping.

That splits the rung, and the split is the honest part:

    we created a context or a page on the remote, and the count
    it reports grew                                              OBSERVED
    we adopted an existing context and page and created nothing  ACCEPTED
    we created one and the count did not move                    INDETERMINATE
    the remote never identified itself                           ACCEPTED

Adopting is only ACCEPTED because nothing about the remote changed: it answered
and named itself, which is exactly "the other side acknowledged taking it".
Creating a target IS a change to the remote — it costs the provider a tab and
the caller a billed session — and we watched its inventory grow by one, which is
what OBSERVED means here.

``Browser.is_connected()`` is deliberately not consulted: see
``_session_outcome`` for why `True` from it is not a measurement.
"""
import logging
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ....utils import enforce_outbound_service_url
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _connect_outcome(
    *,
    version: Optional[str],
    created_context: bool,
    created_page: bool,
    contexts_before: int,
    contexts_after: int,
    pages_before: int,
    pages_after: int,
) -> Dict[str, Any]:
    """The rung this connection earned, from what the remote reported.

    ``version`` alone never lifts this past ACCEPTED. A remote that names itself
    has acknowledged us and no more; the ladder's OBSERVED asks that we watched
    something change, and the only thing this module changes on the far side is
    the target inventory.
    """
    identified = {
        'kind': 'remote_browser_identified' if version else 'remote_browser_not_identified',
        'version': version,
        'measured_by': (
            'Browser.version — the build string the remote reported through the '
            'CDP handshake'
        ) if version else None,
        'detail': (
            'A remote process answered and named its own build. That it took '
            'the connection is established; that anything on it changed is a '
            'separate question, answered by the target counts.'
        ) if version else (
            'connect_over_cdp returned without raising, but the remote build '
            'string could not be read back.'
        ),
    }

    targets = {
        'kind': 'remote_targets_counted',
        'created_context': created_context,
        'created_page': created_page,
        'contexts_before': contexts_before,
        'contexts_after': contexts_after,
        'pages_before': pages_before,
        'pages_after': pages_after,
        'measured_by': (
            'len(Browser.contexts) and len(BrowserContext.pages), read before '
            'and after the create calls — both lists are built from target '
            'events the remote sends'
        ),
    }

    if not (created_context or created_page):
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[identified, {
                **targets,
                'detail': (
                    'An existing context and page were adopted. Nothing was '
                    'created on the remote, so there was no change to watch.'
                ),
            }],
        )

    grew = contexts_after > contexts_before or pages_after > pages_before
    if not grew:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[identified, {
                **targets,
                'predicate': 'len(contexts) or len(pages) grew after the create call',
                'detail': (
                    'A context or page was requested from the remote and the '
                    'inventory it reports did not grow. A target closing in the '
                    'same instant reads the same as one that was never created, '
                    'so this is indeterminate rather than failed.'
                ),
            }],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[identified, {
            **targets,
            'detail': (
                'The remote created the target we asked for and reported it '
                'back. This is a change to the far side — a tab on the '
                'provider, a billed session — and not an echo of the endpoint '
                'we dialled.'
            ),
        }],
    )


@register_module(
    module_id='browser.connect',
    version='1.0.0',
    category='browser',
    tags=['browser', 'remote', 'cloud', 'browserless', 'anti-detection'],
    label='Connect Remote',
    label_key='modules.browser.connect.label',
    description='Connect to a remote browser service (Browserless, BrowserBase, CDP). Real fingerprints, residential IPs.',
    description_key='modules.browser.connect.description',
    icon='Cloud',
    color='#7C3AED',
    input_types=[],
    output_types=['browser', 'page'],
    can_receive_from=['start', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('ws_endpoint', type='string', label='WebSocket endpoint',
              description='CDP WebSocket URL (e.g., wss://chrome.browserless.io?token=xxx).',
              required=True, format='url',
              placeholder='wss://chrome.browserless.io?token=YOUR_TOKEN',
              group='basic'),
        field('viewport_width', type='number', label='Viewport width',
              default=1280, min=320, max=3840,
              group='basic'),
        field('viewport_height', type='number', label='Viewport height',
              default=720, min=240, max=2160,
              group='basic'),
        field('locale', type='string', label='Locale',
              default='en-US', required=False,
              group='advanced'),
        field('timeout_ms', type='number', label='Connection timeout (ms)',
              default=30000, min=5000, max=120000, step=5000,
              group='advanced'),
    ),
    output_schema={
        'connected':    {'type': 'boolean', 'description': 'Literal True on the success path — kept for compatibility, not a measurement'},
        'browser_type': {'type': 'string',  'description': 'Browser type (chromium)'},
        'remote_version': {'type': 'string', 'description': 'Build string the remote browser reported over CDP, or null when it could not be read'},
        'endpoint':     {'type': 'string',  'description': 'Connected endpoint (redacted)'},
        'outcome':      {'type': 'object',  'description': (
            'How far this connection was followed: observed when a context or '
            'page was created on the remote and its target count grew, accepted '
            'when an existing one was adopted, indeterminate when a create was '
            'requested and the count did not move'
        )},
    },
    examples=[
        {'name': 'Connect to Browserless', 'params': {'ws_endpoint': 'wss://chrome.browserless.io?token=TOKEN'}},
        {'name': 'Connect to BrowserBase', 'params': {'ws_endpoint': 'wss://connect.browserbase.com?apiKey=KEY'}},
        {'name': 'Self-hosted', 'params': {'ws_endpoint': 'ws://localhost:3000'}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=35000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserConnectModule(BaseModule):
    module_name = "Connect Remote"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.ws_endpoint = self.params.get('ws_endpoint', '')
        if not self.ws_endpoint:
            raise ValueError("ws_endpoint is required")
        # SECURITY: connect_over_cdp() dials this endpoint and hands the caller
        # full DevTools control of whatever answers. An unguarded ws:// target
        # reaches any internal debugging port the runner can route to, and CDP
        # is remote code execution by design. validate_url_ssrf only speaks
        # http(s), so the ws/wss host goes through the service-URL guard.
        enforce_outbound_service_url(self.ws_endpoint, purpose='CDP endpoint')
        self.viewport = {
            'width': self.params.get('viewport_width', 1280),
            'height': self.params.get('viewport_height', 720),
        }
        self.locale = self.params.get('locale', 'en-US')
        self.conn_timeout = self.params.get('timeout_ms', 30000)

    async def execute(self) -> Any:
        from playwright.async_api import async_playwright
        from core.browser.driver import BrowserDriver

        # Close existing browser
        existing = self.context.get('browser')
        if existing:
            try:
                await existing.close()
            except Exception:
                pass

        # Connect to remote CDP endpoint
        pw = await async_playwright().start()

        try:
            remote_browser = await pw.chromium.connect_over_cdp(
                self.ws_endpoint,
                timeout=self.conn_timeout,
            )
        except Exception as e:
            await pw.stop()
            raise RuntimeError(f"Failed to connect to remote browser: {e}") from e

        # Get or create context + page. The counts are read before and after
        # each create so the envelope can tell "we changed the remote and
        # watched it change" from "we adopted what was already there".
        contexts = remote_browser.contexts
        contexts_before = len(contexts)
        created_context = False
        if contexts:
            context = contexts[0]
        else:
            context = await remote_browser.new_context(
                viewport=self.viewport,
                locale=self.locale,
            )
            created_context = True

        pages = context.pages
        pages_before = len(pages)
        created_page = False
        if pages:
            page = pages[0]
        else:
            page = await context.new_page()
            created_page = True

        contexts_after = len(remote_browser.contexts)
        pages_after = len(context.pages)

        try:
            remote_version = remote_browser.version
        except Exception:  # noqa: BLE001 - any failure means "cannot look"
            remote_version = None

        # Wrap in BrowserDriver for compatibility with other browser.* modules
        driver = BrowserDriver(
            headless=True,
            viewport=self.viewport,
            browser_type='chromium',
        )
        driver._playwright = pw
        driver._browser = remote_browser
        driver._context = context
        driver._page = page

        self.context['browser'] = driver
        self.context['browser_remote'] = True

        # Redact token from endpoint for output
        endpoint_display = self.ws_endpoint.split('?')[0] + '?...'

        logger.info("Connected to remote browser: %s", endpoint_display)

        return {
            "status": "success",
            # A literal, kept for compatibility. `remote_version` below is the
            # field that could not have been produced without a live remote.
            "connected": True,
            "browser_type": "chromium",
            "remote_version": remote_version,
            "endpoint": endpoint_display,
            "outcome": _connect_outcome(
                version=remote_version,
                created_context=created_context,
                created_page=created_page,
                contexts_before=contexts_before,
                contexts_after=contexts_after,
                pages_before=pages_before,
                pages_after=pages_after,
            ),
        }
