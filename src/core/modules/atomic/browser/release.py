# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Release Module - Smart browser session cleanup

Releases a browser session, but only closes it if:
1. This template owns the browser (launched via browser.ensure)
2. Force mode is enabled (explicit close regardless of ownership)

This enables templates to be both:
- Independently executable (will close their own browser)
- Composable (will NOT close parent's browser)

Design Philosophy:
    browser.ensure = "I need a browser, but I don't care who started it"
    browser.release = "I'm done with the browser, close it if I own it"

Pairing:
    browser.ensure  ←→  browser.release  (smart, composable)
    browser.launch  ←→  browser.close    (explicit, always close)

THREE PATHS, AND ONLY ONE OF THEM CLOSES ANYTHING

`browser.close` already established what a teardown may claim, and the closing
path here is the same measurement through the same helper: hold the Playwright
``Browser`` object across ``driver.close()`` — which sets ``driver._browser`` to
None whether the teardown worked or timed out, so asking the driver afterwards
would only confirm that this code ran — and ask it.

    the connection is gone         OBSERVED
    the connection is still live   INDETERMINATE
    no Browser object to ask       ACCEPTED

"Browser closed successfully" was this module's word for all three.
``BrowserDriver.close`` wraps each of its four teardown steps in a bare
``except`` and returns ``{'status': 'success'}`` either way, so its return has
never distinguished them.

The skipped and no_browser paths deliberately close nothing: skipped is the
whole point of this module, and no_browser has nothing to act on. Neither
dispatches an instruction, so neither writes an envelope — the same reasoning
`browser.close` records for its own nothing-to-close return, and the engine's
`dispatched` default lands on them.
"""
from typing import Any, Dict

from ....engine.outcome import envelope
from ...base import BaseModule
from ...registry import register_module
from ._session_outcome import browser_object, closed_claim, observe_disconnected


@register_module(
    module_id='browser.release',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'cleanup', 'session', 'composable', 'ssrf_protected'],
    label='Release Browser',
    label_key='modules.browser.release.label',
    description='Release browser session (close only if owned)',
    description_key='modules.browser.release.description',
    icon='MonitorOff',
    color='#6B7280',  # Gray - indicates "optional" action

    # Connection types
    input_types=['browser', 'page'],
    output_types=[],

    # Connection rules - same as browser.close
    can_receive_from=['browser.*', 'element.*', 'flow.*'],
    can_connect_to=['notify.*', 'data.*', 'file.*', 'flow.*', 'end', 'ai.*', 'llm.*', 'agent.*'],

    # Execution settings
    timeout_ms=10000,
    retryable=False,
    max_retries=0,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    params_schema={
        'force': {
            'type': 'boolean',
            'label': 'Force Close',
            'label_key': 'modules.browser.release.params.force.label',
            'description': 'Close browser even if not owned by this template',
            'description_key': 'modules.browser.release.params.force.description',
            'default': False
        }
    },
    output_schema={
        'status': {
            'type': 'string',
            'enum': ['closed', 'skipped', 'no_browser'],
            'description': 'What action was taken',
            'description_key': 'modules.browser.release.output.status.description'
        },
        'message': {
            'type': 'string',
            'description': 'Result message',
            'description_key': 'modules.browser.release.output.message.description'
        },
        'was_owner': {
            'type': 'boolean',
            'description': 'Whether this template owned the browser',
            'description_key': 'modules.browser.release.output.was_owner.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the teardown was followed: observed when Playwright '
                'reports the browser connection gone, indeterminate when it is '
                'still live, accepted when there was no Browser object to ask. '
                'Absent on the skipped and no_browser paths, which close '
                'nothing.'
            ),
            'description_key': 'modules.browser.release.output.outcome.description'
        }
    },
    examples=[
        {
            'name': 'Release browser (smart)',
            'description': 'Close only if this template owns the browser',
            'params': {}
        },
        {
            'name': 'Force release',
            'description': 'Always close browser regardless of ownership',
            'params': {'force': True}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserReleaseModule(BaseModule):
    """
    Release Browser Module

    Smart browser session cleanup that respects ownership.

    Behavior:
    - If no browser: return status="no_browser"
    - If browser exists but not owner: return status="skipped" (don't close)
    - If browser exists and is owner: close it, return status="closed"
    - If force=True: always close regardless of ownership

    Ownership is determined by:
    - browser_owner context key (set by browser.ensure)
    - browser_owned_by_ensure flag (indicates ensure pattern was used)
    """

    module_name = "Release Browser"
    module_description = "Release browser session (close only if owned)"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.force = self.params.get('force', False)

    async def execute(self) -> Dict[str, Any]:
        browser = self.context.get('browser')

        # No browser to release
        if not browser:
            return {
                "status": "success",
                "action": "no_browser",
                "message": "No browser session to release",
                "was_owner": False,
            }

        # Check ownership
        browser_owner = self.context.get('browser_owner')
        owned_by_ensure = self.context.get('browser_owned_by_ensure', False)
        browser_inherited = self.context.get('browser_inherited', False)
        step_id = self.params.get('$step_id', 'browser_release')

        # Determine if we should close
        # We are the owner if:
        # 1. browser was launched by browser.ensure in THIS template (owned_by_ensure=True)
        # 2. AND browser was NOT inherited from parent template
        # 3. OR force=True (explicit override)
        #
        # Key insight: browser_inherited is set by template.invoke when passing
        # browser to child templates. This tells us the browser belongs to parent.
        is_owner = owned_by_ensure and not browser_inherited

        should_close = self.force or is_owner

        if not should_close:
            # Not owner, don't close (parent will handle it)
            reason = "inherited from parent" if browser_inherited else "not launched by this template"
            return {
                "status": "success",
                "action": "skipped",
                "message": f"Browser {reason}, not closing (parent will handle cleanup)",
                "was_owner": False,
                "reason": reason,
                "browser_inherited": browser_inherited,
            }

        # Held across close(): the driver drops its own reference on every path,
        # including the ones where a teardown step timed out and was swallowed.
        held = browser_object(browser)

        # Close the browser
        await browser.close()

        disconnected, reason = observe_disconnected(held)
        rung, claim_by, reading = closed_claim(disconnected=disconnected, reason=reason)

        # Clean up context
        self.context.pop('browser', None)
        self.context.pop('browser_owner', None)
        self.context.pop('browser_owned_by_ensure', None)

        return {
            "status": "success",
            "action": "closed",
            "message": "Browser closed successfully",
            "was_owner": True,
            "outcome": envelope(rung, claim_by=claim_by, effects=[reading]),
        }
