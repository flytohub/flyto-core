# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Evaluate Module

Execute JavaScript in page context.

ACCEPTED IS THE CEILING HERE, AND IT IS NOT A GAP TO BE CLOSED LATER

``page.evaluate`` returning without raising means the page's JS runtime took the
script, ran it to completion and serialised a value back across the CDP
connection. That is a peer reporting on its own work — the definition of
ACCEPTED — and it is a real fact: a syntax error, a thrown exception or a
navigated-away context all raise instead.

It is not OBSERVED, and no amount of work on this module would make it so. The
effect of ``browser.evaluate`` is whatever the caller's script does, and the
script is an opaque parameter: this module cannot know whether it read the DOM,
rewrote it, posted to an API or did nothing. The returned value is the script's
own report about itself, chosen by the script's author.

    ``{'script': 'return 1 + 1'}``            returns 2, changed nothing
    ``{'script': 'document.body.remove()'}``  returns null, destroyed the page

Both come back the same way. Reading the second as an observation because a
value arrived would attach evidence to the wrong thing, and reading the first as
one would be inventing an effect. So the rung is flat across every script, and
what varies is only the effect payload — whether a value came back and what
JSON type it was, which is exactly what the module can honestly say it saw.

A caller that needs a rung above this writes the read-back as a step of its own:
a second `browser.evaluate` that measures the state the first one was supposed
to produce is an observation, made by the workflow rather than claimed here.
"""
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _evaluate_outcome(*, returned: Any) -> Dict[str, Any]:
    """The rung a script execution earned: ACCEPTED, on every path.

    The payload records the SHAPE of what came back, never the value. A script
    is free to return a session token or a page of personal data, and this
    envelope is copied into a trace row and a websocket frame; the value already
    travels in `result`, where the redaction and retention rules for module
    output apply to it.
    """
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'script_executed',
            'returned_type': type(returned).__name__,
            'returned_null': returned is None,
            'measured_by': 'page.evaluate() returned a serialised value without raising',
            'detail': (
                "The page's JS runtime took the script, ran it and answered. "
                'What the script did to the page is not measured: the returned '
                'value is the script\'s own report about itself, and an '
                'arbitrary script has no postcondition this module could know.'
            ),
        }],
    )


@register_module(
    module_id='browser.evaluate',
    version='1.0.0',
    category='browser',
    tags=['browser', 'javascript', 'execute', 'script', 'ssrf_protected'],
    label='Execute JavaScript',
    label_key='modules.browser.evaluate.label',
    description='Execute JavaScript code in page context',
    description_key='modules.browser.evaluate.description',
    icon='Code',
    color='#FFC107',

    # Connection types
    input_types=['page'],
    output_types=['any'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['*'],    params_schema=compose(
        presets.JS_SCRIPT(),
        presets.JS_ARGS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.evaluate.output.status.description'},
        'result': {'type': 'any', 'description': 'The operation result',
                'description_key': 'modules.browser.evaluate.output.result.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this script was followed: always accepted -- the page '
                'ran it and answered, and what an arbitrary script does to the '
                'page cannot be measured from here'
            ),
            'description_key': 'modules.browser.evaluate.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Get page title',
            'params': {'script': 'return document.title'}
        },
        {
            'name': 'Get element count',
            'params': {'script': 'return document.querySelectorAll("a").length'}
        },
        {
            'name': 'Execute with arguments',
            'params': {
                'script': '(selector) => document.querySelector(selector)?.textContent',
                'args': ['#header']
            }
        },
        {
            'name': 'Modify page',
            'params': {'script': 'document.body.style.backgroundColor = "red"; return "done"'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=120000,
    required_permissions=["browser.automation"],
)
class BrowserEvaluateModule(BaseModule):
    """Execute JavaScript Module"""

    module_name = "Execute JavaScript"
    module_description = "Execute JavaScript in page context"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'script' not in self.params:
            raise ValueError("Missing required parameter: script")
        self.script = self.params['script']
        self.args = self.params.get('args', [])

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Wrap script if it doesn't look like a function
        script = self.script.strip()
        if not script.startswith('(') and not script.startswith('function'):
            # Wrap in arrow function
            script = f'() => {{ {script} }}'

        if self.args:
            result = await page.evaluate(script, *self.args)
        else:
            result = await page.evaluate(script)

        return {
            "status": "success",
            "result": result,
            "outcome": _evaluate_outcome(returned=result),
        }
