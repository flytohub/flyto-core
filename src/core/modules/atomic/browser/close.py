# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Close Module

Provides functionality to close browser instances.

"Browser closed successfully" IS A STRING, NOT A FINDING

``BrowserDriver.close()`` wraps each of its four teardown steps in
``except (asyncio.TimeoutError, Exception): logger.debug("... timed out or
failed, continuing")``, then drops the reference and returns ``{'status':
'success'}``. Every one of them can fail — a hung page, a context that will not
close, a browser process that ignores the request — and the return value is
identical. This module then rewrote that into "Browser closed successfully".
There is no path on which either string is derived from anything the browser
did.

Playwright will answer the question directly: ``Browser.is_connected()`` reports
whether the driver's connection to the browser process is still live. Holding
the object across ``close()`` and asking it afterwards is a measurement of the
process, not of our own bookkeeping — ``driver._browser`` is set to None whether
the close worked or timed out, so checking that would only confirm that this
code ran.

    a browser object, and it is no longer connected    -> OBSERVED
    a browser object, and it is still connected        -> INDETERMINATE
    no browser object to ask (persistent-context mode,
    or a driver that never launched)                   -> ACCEPTED
    nothing in context to close at all                 -> no envelope

The still-connected case is INDETERMINATE rather than FAILED because the
teardown is asynchronous at the process level: a browser that has been asked to
exit and has not finished exiting reads exactly like one that refused. What is
worth knowing is that this module said "successfully" in that state before.

The last row is the one this file cannot do justice to. When there is no driver
in context, this module returns a warning and makes no attempt to close
anything: nothing was dispatched, nothing was accepted, and nothing was
observed. The ladder has four rungs and none of them means "no instruction was
issued", so no envelope is written and the engine's default — `dispatched` —
lands on it. That is a small overstatement of a step that dispatched nothing,
and it is recorded here rather than papered over with a rung invented to fit:
`dispatched` is the weakest thing anything can say, and inventing a fifth rung
in one module would be a much larger error than tolerating this one.
"""
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module


def _observe_disconnected(browser_object: Any) -> Tuple[Optional[bool], Optional[str]]:
    """``(disconnected, None)`` when Playwright could be asked, ``(None, why)`` when not."""
    if browser_object is None:
        return None, 'no Browser object to ask (persistent context, or never launched)'
    try:
        return not browser_object.is_connected(), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


def _close_outcome(*, disconnected: Optional[bool], reason: Optional[str]) -> Dict[str, Any]:
    """The rung this teardown earned, from Playwright's own connection state."""
    if disconnected is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'browser_state_not_observed',
                'measured_by': None,
                'reason': reason,
                'detail': (
                    'close() returned. It swallows a failure or a timeout at '
                    'every teardown step and returns the same value either way, '
                    'so its return is an acknowledgement and not a finding.'
                ),
            }],
        )

    if disconnected:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'browser_disconnected',
                'measured_by': 'Browser.is_connected() on the object held across close()',
                'detail': (
                    'Playwright no longer has a live connection to the browser '
                    'process. Whether the OS process has fully exited, and '
                    'whether the profile directory was cleaned up, are not '
                    'measured here.'
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'browser_still_connected',
            'predicate': 'not Browser.is_connected()',
            'measured_by': 'Browser.is_connected() on the object held across close()',
            'detail': (
                'close() reported success and the connection is still live. '
                'Teardown is asynchronous, so a browser that has been asked to '
                'exit and has not finished reads the same as one that refused. '
                'We cannot say which, only that "closed successfully" is not '
                'established.'
            ),
        }],
    )


@register_module(
    module_id='browser.close',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'cleanup', 'ssrf_protected'],
    label='Close Browser',
    label_key='modules.browser.close.label',
    description='Close the browser instance and release resources',
    description_key='modules.browser.close.description',
    icon='X',
    color='#E74C3C',

    # Connection types
    input_types=['browser', 'page'],  # Accept both browser and page
    output_types=[],

    # Connection rules
    can_receive_from=['browser.*', 'element.*', 'flow.*'],
    can_connect_to=['*'],

    # Execution settings
    timeout_ms=15000,
    retryable=False,
    max_retries=0,
    concurrent_safe=False,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['browser.read', 'browser.write'],

    params_schema={
        '_no_params': {
            'type': 'boolean',
            'label': 'No Parameters',
            'description': 'This module requires no parameters',
            'default': True,
            'hidden': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.close.output.status.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.browser.close.output.message.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this teardown was followed: observed when Playwright '
                'reports the browser connection gone, indeterminate when it is '
                'still live, accepted when there was no Browser object to ask'
            ),
            'description_key': 'modules.browser.close.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Close browser',
            'params': {}
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BrowserCloseModule(BaseModule):
    """Close Browser Module"""

    module_name = "Close Browser"
    module_description = "Close the browser instance"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        pass

    async def execute(self) -> Any:
        driver = self.context.get('browser')

        if not driver:
            # Nothing was attempted. See the module docstring: no rung on the
            # ladder means "no instruction was issued", so nothing is claimed
            # here and the engine's default lands instead.
            return {"status": "warning", "message": "No browser instance to close"}

        # Held across close(), which sets driver._browser to None on every path
        # including the ones where the teardown timed out. Asking the object we
        # kept is asking Playwright; asking the driver's attribute afterwards
        # would only confirm that this code ran.
        browser_object = getattr(driver, '_browser', None)

        await driver.close()

        disconnected, reason = _observe_disconnected(browser_object)

        # Remove from context
        self.context.pop('browser', None)

        return {
            "status": "success",
            "message": "Browser closed successfully",
            "outcome": _close_outcome(disconnected=disconnected, reason=reason),
        }
