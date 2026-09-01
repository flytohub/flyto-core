# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Dialog Module

Handle alert, confirm, and prompt dialogs.

HOW FAR A HANDLED DIALOG IS FOLLOWED

Two different jobs live behind one ``action`` parameter, and they do not earn
the same rung.

``listen`` performs no effect at all. It registers a handler, watches for the
window, and reports what the page said. ``dialog.message``, ``dialog.type`` and
``dialog.default_value`` are strings the PAGE produced and that crossed the CDP
wire; not one of them is an echo of a parameter. Seeing a dialog is therefore an
observation. Seeing none is the empty-read case `database.query` is built
around: no dialog inside the window reads identically whether the page never
opened one, opened one a millisecond late, or opened one on a frame this handler
was not attached to. That is ACCEPTED and no more.

``accept`` and ``dismiss`` DO perform an effect, and nothing here reads it back.
``dialog.accept()`` is a CDP command the browser acknowledges -- "the other side
acknowledged taking it. Not that it ran" -- which is exactly ACCEPTED, and it is
the ceiling for these two no matter how clearly the dialog itself was seen. The
page after a dismissed confirm looks the same as the page after an accepted one
unless the page's own script says otherwise, and this module does not run the
page's script.

    listen, a dialog arrived                    OBSERVED
    listen, none arrived inside the window      ACCEPTED
    accept/dismiss, handled without raising     ACCEPTED
    accept/dismiss, the handler raised          FAILED
    accept/dismiss, no dialog arrived           INDETERMINATE

The last line is why ``handle_error`` exists at all. The handler runs inside
Playwright's event dispatch, so an exception from ``dialog.accept()`` -- the
dialog was already handled, the page navigated out from under it -- never
reached this coroutine and vanished entirely while the module went on returning
``status: "success"``. It is captured now, and it is the one path here that is
FAILED rather than a rung: the execution itself raised.

And no dialog arriving is INDETERMINATE rather than FAILED because it is a
timeout. We know we stopped waiting; we do not know that the page had nothing to
show.
"""
from typing import Any, Dict, Optional
import asyncio

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _dialog_outcome(
    *,
    action: str,
    appeared: bool,
    dialog_type: Optional[str],
    handle_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this dialog step earned, and the readings that earned it."""
    if not appeared:
        nothing_seen = {
            'kind': 'no_dialog_in_window',
            'measured_by': None,
            'detail': (
                'No dialog event arrived before the timeout. That reads the '
                'same whether the page never opened one, opened one just after '
                'we stopped listening, or opened one on a frame this handler '
                'was not attached to.'
            ),
        }
        if action == 'listen':
            # An empty read, not a failed effect: `listen` never asked the page
            # for anything, so there is nothing that could have gone wrong.
            return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=[nothing_seen])
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[nothing_seen, {
                'kind': 'dialog_not_handled',
                'action': action,
                'detail': (
                    'There was nothing to accept or dismiss, so this step '
                    'changed nothing. It is a timeout and not a failure: we '
                    'know we stopped waiting, not that the page had nothing '
                    'to show.'
                ),
            }],
        )

    seen = {
        'kind': 'dialog_observed',
        'dialog_type': dialog_type,
        'measured_by': 'the dialog event Playwright delivered from the page',
        'detail': (
            'The type, message and default value came out of the page across '
            'the CDP wire. None of them is an echo of a parameter, so a dialog '
            'demonstrably opened.'
        ),
    }

    if action == 'listen':
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[seen])

    if handle_error:
        return envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.NONE,
            effects=[seen, {
                'kind': 'dialog_handling_raised',
                'action': action,
                'reason': handle_error,
                'detail': (
                    'The dialog was seen and the accept/dismiss raised inside '
                    'Playwright\'s event dispatch. The execution itself failed, '
                    'which is not a rung.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[seen, {
            'kind': 'dialog_handled',
            'action': action,
            'measured_by': None,
            'detail': (
                'The browser acknowledged the accept/dismiss and did not raise. '
                'Nothing was read back afterwards: an accepted confirm and a '
                'dismissed one leave a page that looks identical unless the '
                'page\'s own script says otherwise.'
            ),
        }],
    )


@register_module(
    module_id='browser.dialog',
    version='1.0.0',
    category='browser',
    tags=['browser', 'dialog', 'alert', 'confirm', 'prompt', 'ssrf_protected'],
    label='Handle Dialog',
    label_key='modules.browser.dialog.label',
    description='Handle alert, confirm, and prompt dialogs',
    description_key='modules.browser.dialog.description',
    icon='MessageSquare',
    color='#FD7E14',

    # Connection types
    input_types=['page'],
    output_types=['object'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.DIALOG_ACTION(),
        presets.DIALOG_PROMPT_TEXT(),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.dialog.output.status.description'},
        'message': {'type': 'string', 'description': 'Result message describing the outcome',
                'description_key': 'modules.browser.dialog.output.message.description'},
        'type': {'type': 'string', 'description': 'The type',
                'description_key': 'modules.browser.dialog.output.type.description'},
        'default_value': {'type': 'string', 'description': 'The default value',
                'description_key': 'modules.browser.dialog.output.default_value.description'},
        'outcome': {'type': 'object', 'description': (
            'How far this step was followed: observed when listening saw a real '
            'dialog, accepted when one was accepted or dismissed without a '
            'read-back, failed when the handling raised, indeterminate when no '
            'dialog arrived before the timeout.'
        ), 'description_key': 'modules.browser.dialog.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Accept alert',
            'params': {'action': 'accept'}
        },
        {
            'name': 'Dismiss confirm dialog',
            'params': {'action': 'dismiss'}
        },
        {
            'name': 'Accept prompt with text',
            'params': {'action': 'accept', 'prompt_text': 'Hello World'}
        },
        {
            'name': 'Listen for dialogs',
            'params': {'action': 'listen', 'timeout': 5000}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserDialogModule(BaseModule):
    """Handle Dialog Module"""

    module_name = "Handle Dialog"
    module_description = "Handle alert, confirm, and prompt dialogs"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['accept', 'dismiss', 'listen']:
            raise ValueError(f"Invalid action: {self.action}")

        self.prompt_text = self.params.get('prompt_text')
        self.timeout = self.params.get('timeout', 30000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        dialog_info = {
            'appeared': False, 'message': None, 'type': None,
            'default_value': None, 'handle_error': None,
        }

        async def handle_dialog(dialog):
            dialog_info['appeared'] = True
            dialog_info['message'] = dialog.message
            dialog_info['type'] = dialog.type
            dialog_info['default_value'] = dialog.default_value

            # This coroutine runs inside Playwright's event dispatch, so an
            # exception here is swallowed there and never reaches `execute`.
            # Without capturing it, an accept that raised -- the dialog was
            # already handled, the page navigated out from under it -- was
            # indistinguishable from one that worked.
            try:
                if self.action == 'accept':
                    if self.prompt_text is not None:
                        await dialog.accept(self.prompt_text)
                    else:
                        await dialog.accept()
                elif self.action == 'dismiss':
                    await dialog.dismiss()
                # For 'listen', just capture info without handling
            except Exception as error:  # noqa: BLE001 - the reason is the payload
                dialog_info['handle_error'] = (
                    f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
                )

        page.on('dialog', handle_dialog)

        try:
            if self.action == 'listen':
                # Just wait and capture any dialogs
                await asyncio.sleep(self.timeout / 1000)
            else:
                # Wait for dialog to appear
                try:
                    await asyncio.wait_for(
                        self._wait_for_dialog(dialog_info),
                        timeout=self.timeout / 1000
                    )
                except asyncio.TimeoutError:
                    pass

        finally:
            page.remove_listener('dialog', handle_dialog)

        found = _dialog_outcome(
            action=self.action,
            appeared=bool(dialog_info['appeared']),
            dialog_type=dialog_info['type'],
            handle_error=dialog_info['handle_error'],
        )

        if dialog_info['appeared']:
            return {
                "status": "success",
                "message": dialog_info['message'],
                "type": dialog_info['type'],
                "default_value": dialog_info['default_value'],
                "action": self.action,
                "handle_error": dialog_info['handle_error'],
                "outcome": found,
            }
        else:
            return {
                "status": "success",
                "message": None,
                "type": None,
                "default_value": None,
                "action": self.action,
                "note": "No dialog appeared within timeout",
                "outcome": found,
            }

    async def _wait_for_dialog(self, dialog_info: dict):
        while not dialog_info['appeared']:
            await asyncio.sleep(0.1)
