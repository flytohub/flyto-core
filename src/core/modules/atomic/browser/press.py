# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Press Module - Press a keyboard key

WHY THIS MODULE REPORTS NO OUTCOME

A keypress has no effect of its own. What it changes is decided entirely by what
had focus and by what the page's own handlers do with the event, and this module
knows neither -- it does not even take a selector. There is no field to read
back, because there is no field.

The one candidate that is a page reading rather than a restatement of the
parameter is ``document.activeElement``. Measured on the Chromium this
repository drives, with a real page and a real ``keyboard.press``:

    Tab                                     BODY -> INPUT#a      moves
    Tab again                               INPUT#a -> INPUT#b   moves
    Enter, with nothing focused             BODY -> BODY         unchanged
    Enter, with a text input focused        INPUT#a -> INPUT#a   unchanged
    Escape, with a text input focused       INPUT#a -> INPUT#a   unchanged
    Enter, with a button focused            BUTTON -> BUTTON     unchanged
        ...and the button's click handler ran and rewrote the page

That last line is the whole argument. The press did the most consequential thing
a press can do -- it fired a handler that changed the document -- and
``activeElement`` did not move a millimetre. `Enter` and `Escape` are the two
keys in this module's own examples, and a rung resting on activeElement would
mark every correct one of them INDETERMINATE while reporting OBSERVED for `Tab`,
the one press that changes nothing anybody cares about.

That is `browser.hover`'s withdrawn ``:hover`` predicate in a different costume:
a signal that reads false for the cases that matter. So this module keeps the
engine's default `dispatched`, which is the honest description of a key that
left us with nobody confirming anything. The measurement is pinned as a test
rather than left as prose, in
``tests/modules/test_browser_actions_outcome.py::TestPressHasNothingToRead``.

What would earn a rung: a selector to press INTO, so the same
``page.input_value`` read-back `browser.type` uses would apply -- or a
caller-supplied assertion about the page afterwards, evaluated here as a
declared postcondition. Both are changes to this module's parameters before they
are changes to its reporting.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


@register_module(
    module_id='browser.press',
    version='1.0.0',
    category='browser',
    tags=['browser', 'keyboard', 'interaction', 'key', 'ssrf_protected'],
    label='Press Key',
    label_key='modules.browser.press.label',
    description='Press a keyboard key',
    description_key='modules.browser.press.description',
    icon='Command',
    color='#34495E',

    # Connection types
    input_types=['page'],
    output_types=['browser', 'page'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.KEYBOARD_KEY(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.press.output.status.description'},
        'key': {'type': 'string', 'description': 'Key identifier',
                'description_key': 'modules.browser.press.output.key.description'}
    },
    examples=[
        {
            'name': 'Press Enter key',
            'params': {'key': 'Enter'}
        },
        {
            'name': 'Press Escape key',
            'params': {'key': 'Escape'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserPressModule(BaseModule):
    """Press Key Module"""

    module_name = "Press Key"
    module_description = "Press a keyboard key"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'key' not in self.params:
            raise ValueError("Missing required parameter: key")
        self.key = self.params['key']

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        await browser.real_page.keyboard.press(self.key)
        return {"status": "success", "key": self.key}
