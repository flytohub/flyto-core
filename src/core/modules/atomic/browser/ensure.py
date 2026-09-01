# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Ensure Module - Smart browser session management

Ensures a browser session exists, either by:
1. Reusing an existing browser from parent context (when called from template.invoke)
2. Launching a new browser if none exists (when run independently)

This enables templates to be both:
- Independently executable (will launch their own browser)
- Composable (will reuse parent's browser when invoked as sub-template)

Design Philosophy:
    browser.ensure = "I need a browser, but I don't care who started it"
    browser.release = "I'm done with the browser, close it if I own it"

TWO PATHS, AND ONLY ONE OF THEM DOES ANYTHING

The launch path is `browser.launch`'s question and gets `browser.launch`'s
answer: the process that was started is asked for its version, and the rung
follows (OBSERVED when it answers, ACCEPTED when there is no Browser object to
ask). See ``_session_outcome``.

The reuse path is the interesting one, because it dispatches nothing at all. No
instruction leaves this step; ``self.context.get('browser')`` is a dictionary
read. The ladder has four rungs and none of them means "no instruction was
issued", so — following `browser.close`'s precedent for the nothing-to-close
case — the reuse path writes no envelope and the engine's `dispatched` default
lands on it. That is a small overstatement, recorded here rather than papered
over with a rung invented to fit.

With ONE exception, and it is an asymmetry on purpose. ``is_connected()`` is
born ``True`` and is cleared only when a disconnect event actually arrives from
the browser process, so:

    reused a session that reports connected      no envelope. `True` is the
                                                 attribute's initial value; it
                                                 proves nothing.
    reused a session that reports DISCONNECTED   INDETERMINATE. That flag was
                                                 flipped by a real event, and
                                                 this step is about to hand a
                                                 dead browser to every module
                                                 downstream while reporting
                                                 "Reusing existing browser
                                                 session".

Only the second direction is a measurement, so only the second direction gets to
speak. The first is `browser.storage`'s literal `True` with an extra hop.
"""
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ._session_outcome import browser_object, read_engine, started_claim


def _reused_session_outcome(driver: Any):
    """An envelope for the reuse path, or None when there is nothing to say.

    None is the answer for a session that reports itself connected, and that is
    not a shrug: `is_connected()` starts life as `True` and only a disconnect
    event from the browser ever changes it, so reading `True` here is reading
    the value the attribute was initialised with. Nothing was dispatched and
    nothing was measured, so nothing is claimed.

    A `False` is a different animal. It means a disconnect event genuinely
    arrived, this step is about to report "Reusing existing browser session",
    and every module after it will be handed a dead driver.
    """
    found = browser_object(driver)
    if found is None:
        return None
    try:
        connected = found.is_connected()
    except Exception:  # noqa: BLE001 - any failure means "cannot look"
        return None
    if connected:
        return None
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'reused_session_not_connected',
            'predicate': 'Browser.is_connected() on the session found in context',
            'measured_by': 'Browser.is_connected() — cleared only by a disconnect event',
            'detail': (
                'This step launched nothing and is handing on a session whose '
                'connection to the browser process is already gone. Whether a '
                'later step can still use it is not something this module can '
                'say, so the rung is indeterminate rather than failed.'
            ),
        }],
    )


@register_module(
    module_id='browser.ensure',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup', 'session', 'composable', 'ssrf_protected'],
    label='Ensure Browser',
    label_key='modules.browser.ensure.label',
    description='Ensure a browser session exists (reuse or launch)',
    description_key='modules.browser.ensure.description',
    icon='MonitorCheck',
    color='#10B981',  # Green - indicates "ready" state

    # Connection types
    input_types=[],
    output_types=['browser', 'page'],

    # Connection rules - same as browser.launch
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    can_receive_from=['start', 'flow.*', 'browser.*'],  # Can also follow other browser ops

    # Execution settings
    timeout_ms=15000,
    retryable=True,
    max_retries=2,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    # Schema-driven params
    params_schema=compose(
        presets.BROWSER_HEADLESS(default=False),
        presets.VIEWPORT(),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'enum': ['launched', 'reused'],
            'description': 'Whether browser was launched or reused',
            'description_key': 'modules.browser.ensure.output.status.description'
        },
        'message': {
            'type': 'string',
            'description': 'Result message',
            'description_key': 'modules.browser.ensure.output.message.description'
        },
        'is_owner': {
            'type': 'boolean',
            'description': 'Whether this step owns the browser (responsible for closing)',
            'description_key': 'modules.browser.ensure.output.is_owner.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this step was followed. On the launch path: observed '
                'when the started process reported its version, accepted when '
                'there was no Browser object to ask. On the reuse path: absent, '
                'because nothing was dispatched — unless the reused session '
                'reports its connection already gone, which is indeterminate.'
            ),
            'description_key': 'modules.browser.ensure.output.outcome.description'
        }
    },
    examples=[
        {
            'name': 'Ensure browser (auto-detect)',
            'description': 'Reuse existing browser or launch new one',
            'params': {'headless': False}
        },
        {
            'name': 'Ensure headless browser',
            'description': 'For background automation',
            'params': {'headless': True}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserEnsureModule(BaseModule):
    """
    Ensure Browser Module

    Smart browser session management that enables template composability.

    Behavior:
    - If browser exists in context: reuse it, mark is_owner=False
    - If no browser: launch new one, mark is_owner=True

    This allows templates to:
    1. Run independently (will launch browser)
    2. Be called by other templates (will reuse parent's browser)
    """

    module_name = "Ensure Browser"
    module_description = "Ensure a browser session exists"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.headless = self.params.get('headless', False)
        self.viewport = self.params.get('viewport', {'width': 1280, 'height': 800})

    async def execute(self) -> Dict[str, Any]:
        # Check if browser already exists in context
        existing_browser = self.context.get('browser')

        if existing_browser:
            # Browser exists - reuse it
            # Don't change browser_owner - whoever created it owns it
            result = {
                "status": "success",
                "action": "reused",
                "message": "Reusing existing browser session",
                "is_owner": False,
            }
            reuse = _reused_session_outcome(existing_browser)
            if reuse is not None:
                result["outcome"] = reuse
            return result

        # No browser - launch a new one
        from core.browser.driver import BrowserDriver, browser_profile_scope_from_context

        driver = BrowserDriver(
            headless=self.headless,
            viewport=self.viewport,
            profile_scope=browser_profile_scope_from_context(self.context),
        )
        await driver.launch()

        # Store in context
        self.context['browser'] = driver

        # Mark this step as the owner (responsible for cleanup)
        # Use step_id if available, otherwise generate an owner marker
        step_id = self.params.get('$step_id', 'browser_ensure')
        self.context['browser_owner'] = step_id
        self.context['browser_owned_by_ensure'] = True  # Flag for release module

        engine, version, reason = read_engine(driver)
        rung, claim_by, reading = started_claim(
            engine=engine,
            version=version,
            requested_engine=getattr(driver, 'browser_type', None),
            reason=reason,
        )

        return {
            "status": "success",
            "action": "launched",
            "message": "Browser launched successfully",
            "is_owner": True,
            "headless": self.headless,
            "engine_version": version,
            "outcome": envelope(rung, claim_by=claim_by, effects=[reading]),
        }
