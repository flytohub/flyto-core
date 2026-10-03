# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Type Module - Type text into an input field

HOW FAR A KEYSTROKE IS FOLLOWED

What this module used to report about its own effect was ``text_length``:
``len(self.text)``. That is the length of the caller's own string. It is the
same integer whether every character reached the field, the selector resolved to
a div that swallowed them, or the page's JS cleared the input on the first
keypress. It is `file.write`'s ``bytes_written`` with a keyboard attached.

The measurement that is not that is ``page.input_value(selector)`` — the value
the browser holds for that element, read twice: once immediately before the
keystrokes (after the optional clear, so the baseline is the state typing
actually starts from) and once after. A difference between the two readings
happened in the browser and could not have happened without this step.

    read back, and the field now holds baseline + text   OBSERVED (exact)
    read back, and the field changed to something else   OBSERVED
    read back, and the field did not change at all       INDETERMINATE
    could not read the field back                        ACCEPTED

The middle case is OBSERVED on purpose and it is not a fudge: the ladder defines
that rung as "we saw the world change. Not that the right thing changed", and a
field that went from empty to ``(555) 123-4567`` when ``5551234567`` was typed is
exactly that — an input mask doing its job. Calling it FAILED would put a red
mark on a correct type; calling it OBSERVED and carrying the discrepancy in the
effect says what happened without pretending to judge it.

The unchanged case is INDETERMINATE rather than FAILED for the reason
`outcome.py` separates the two: nobody declared a contract about the field's
value, the equality is this module's own inference, and a readonly input, a
canvas-backed editor or a selector that resolved to the wrong node all produce
it. We cannot say the keystrokes went nowhere — only that nothing we can see
moved.

Sensitive values never enter the envelope. The effects carry character COUNTS
and a boolean, never the value; a password read back and shipped into a trace
row would be a worse defect than the one this file is fixing.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....engine.redaction import SENSITIVE_PARAMS_KEY
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup

#: Words in a field's target or selector that mean the typed text is a secret.
#: Domain-neutral on purpose: these name credentials, not any one site.
_SENSITIVE_FIELD_HINT = re.compile(
    r'(?i)(password|passwd|passphrase|passcode|pwd|secret|token|credential|'
    r'api[_ -]?key|private[_ -]?key|\bpin\b|\botp\b|one[_ -]?time)',
)

#: Elements a label can point at and that accept keystrokes.
_TYPEABLE = (
    'input:not([type=hidden]):not([type=button]):not([type=submit])'
    ':not([type=reset]):not([type=checkbox]):not([type=radio])'
    ':not([type=image]):not([type=file]), textarea, select,'
    ' [contenteditable=""], [contenteditable="true"], [role=textbox]'
)

#: Finds the fields a visible label names through an explicit association --
#: ``<label for=id>`` or ``aria-labelledby`` -- which the structural selectors
#: (label containing the input, label followed by it) cannot see: a label and
#: its input in different containers is the ordinary markup of most form
#: frameworks. Text matching mirrors Playwright's ``:has-text``: whitespace
#: collapsed, case-insensitive, substring; exact matches are ranked first.
#: Returns attribute values only. The selector is built in Python, with
#: escaping, from those values.
_ASSOCIATED_FIELDS_JS = """
([target, typeable]) => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const want = norm(target);
  if (!want) return [];
  const rank = (text) => {
    const t = norm(text);
    return t === want ? 0 : (t.includes(want) ? 1 : 2);
  };
  const textOf = (el) => (el ? (el.innerText || el.textContent || '') : '');
  const found = [];
  for (const label of document.querySelectorAll('label[for]')) {
    const r = rank(textOf(label));
    const field = r < 2 ? document.getElementById(label.htmlFor) : null;
    if (field && field.matches(typeable)) {
      found.push({kind: 'label_for', attr: 'id', value: field.id, rank: r});
    }
  }
  for (const field of document.querySelectorAll('[aria-labelledby]')) {
    if (!field.matches(typeable)) continue;
    const ids = (field.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
    const text = ids.map((id) => textOf(document.getElementById(id))).join(' ');
    const r = rank(text);
    if (r < 2) {
      found.push({kind: 'aria_labelledby', attr: 'aria-labelledby',
                  value: field.getAttribute('aria-labelledby'), rank: r});
    }
  }
  found.sort((a, b) => a.rank - b.rank);
  return found;
}
"""


def _css_attr_selector(attr: str, value: str) -> str:
    """``[attr="value"]`` with the value escaped for a CSS string."""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'[{attr}="{escaped}"]'


async def _associated_label_selectors(page, target: str) -> List[str]:
    """Selectors for fields the label text names via ``for`` / ``aria-labelledby``.

    Best effort: a page that refuses evaluation yields nothing here and the
    structural selectors are still tried.
    """
    try:
        found = await page.evaluate(_ASSOCIATED_FIELDS_JS, [target, _TYPEABLE])
    except Exception:  # noqa: BLE001 - see docstring
        return []
    selectors: List[str] = []
    for item in found or []:
        if not isinstance(item, dict) or not item.get('value'):
            continue
        selector = _css_attr_selector(str(item.get('attr')), str(item['value']))
        if selector not in selectors:
            selectors.append(selector)
    return selectors


async def _is_password_field(page, selector: str) -> bool:
    """Whether the resolved field is an ``<input type=password>``.

    Asked of the page, not the parameters: a selector like ``#pw`` says
    nothing, and the step log must not learn the password because of it.
    """
    try:
        return bool(await page.locator(selector).first.evaluate(
            "(el) => (el.getAttribute('type') || '').toLowerCase() === 'password'",
            timeout=2000,
        ))
    except Exception:  # noqa: BLE001 - cannot tell is not "it is not one"
        return False


async def _read_field_value(page, selector: str) -> Tuple[Optional[str], Optional[str]]:
    """``(value, None)`` when the field could be read, ``(None, why)`` when not.

    Failing here is not a failure of the typing. ``input_value`` raises for a
    contenteditable, a shadow-DOM editor, or any node that is not an
    input/textarea/select — all of which are perfectly typeable. All that is
    lost is our ability to look, and the rung is lowered to match.
    """
    try:
        return await page.input_value(selector, timeout=2000), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


#: What VERIFIED means for this module, and the only branch that may claim it.
#:
#: The read-back goes through a DIFFERENT CHANNEL than the write: the keystrokes
#: go through the keyboard, and `page.input_value` asks the page what the field
#: now holds. That is what makes it evidence rather than an echo -- the value
#: would not read back correct if the keystrokes had not landed.
#:
#: MEASURED CAVEAT, and the reason the sentence says what it says: with
#: `clear=False` the keystrokes go to the caret, which is at position 0, so a
#: field that already held something ends up PREPENDED, not appended. The
#: predicate is `baseline + text` and it correctly does NOT hold in that case --
#: that run lands on the `field_value_differs` branch at OBSERVED, which is the
#: honest answer: the page changed, and it does not hold what was typed.
POSTCONDITION = (
    'the field, read back through input_value after the keystrokes, holds '
    'exactly the value it held before them with the text appended'
)


def _type_outcome(
    *,
    baseline: Optional[str],
    after: Optional[str],
    typed_characters: int,
    expected: Optional[str],
    read_error: Optional[str],
) -> Dict[str, Any]:
    """The rung these keystrokes earned, and the readings that earned it."""
    offered_effect = {
        'kind': 'text_offered',
        'characters': typed_characters,
        'measured_by': 'len() of the text parameter',
        'detail': (
            'Length of the string handed to this module. No browser call '
            'contributes to it: it reads identically whether the field received '
            'every character, some of them, or none.'
        ),
    }

    if baseline is None or after is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'field_value_not_observed',
                    'measured_by': None,
                    'reason': read_error or 'the field value could not be read back',
                    'detail': (
                        'Playwright accepted the keystrokes and did not raise. '
                        'The field was not read back, so nothing followed them '
                        'into the page.'
                    ),
                },
            ],
        )

    observed_effect = {
        'kind': 'field_value_observed',
        'characters_before': len(baseline),
        'characters_after': len(after),
        'matches_expected': after == expected,
        'measured_by': 'page.input_value(selector), read before and after the keystrokes',
        'detail': (
            'Character counts only. The value itself is deliberately absent: '
            'this envelope is copied into a trace row and a websocket frame, and '
            'this module types passwords.'
        ),
    }

    if after == expected:
        return envelope(
            Outcome.VERIFIED,
            # INFERRED: a predicate was evaluated and it was ours. No caller
            # asked for "the field ends up holding exactly what I typed".
            claim_by=ClaimBy.INFERRED,
            effects=[offered_effect, observed_effect],
            postcondition=POSTCONDITION,
        )

    if after != baseline:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.INFERRED,
            effects=[
                offered_effect,
                observed_effect,
                {
                    'kind': 'field_value_differs',
                    'predicate': 'input_value(after) == input_value(before) + text',
                    'expected_characters': len(expected or ''),
                    'actual_characters': len(after),
                    'detail': (
                        'The field changed, so the keystrokes reached the page, '
                        'but it does not hold exactly what was typed. An input '
                        'mask, a maxlength, or a framework-controlled value all '
                        'do this to a correct type. The change is observed; that '
                        'the right thing changed is not claimed.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            offered_effect,
            observed_effect,
            {
                'kind': 'field_value_unchanged',
                'predicate': 'input_value(after) != input_value(before)',
                'detail': (
                    'The field holds what it held before the keystrokes. That '
                    'reads the same whether nothing was typed, the input is '
                    'readonly, the page reset it, or the characters landed on a '
                    'different element. We cannot say which, so this is '
                    'indeterminate rather than failed.'
                ),
            },
        ],
    )


@register_module(
    module_id='browser.type',
    postcondition=POSTCONDITION,
    version='1.2.0',
    category='browser',
    tags=['browser', 'interaction', 'input', 'keyboard', 'ssrf_protected'],
    label='Type Text',
    label_key='modules.browser.type.label',
    description='Type text into an input field. Run browser.snapshot first to find the correct selector from the real page DOM.',
    description_key='modules.browser.type.description',
    icon='Keyboard',
    color='#5BC0DE',

    # Connection types
    input_types=['page', 'string'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*', 'crypto.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field("type_method", type="select",
              label="How to find the input field",
              label_key="modules.browser.type.param.type_method.label",
              description="Choose the easiest way to identify the input field",
              description_key="modules.browser.type.param.type_method.description",
              default="placeholder",
              options=[
                  {"value": "placeholder", "label": "By placeholder text",
                   "label_key": "modules.browser.type.param.type_method.option.placeholder"},
                  {"value": "label", "label": "By label text",
                   "label_key": "modules.browser.type.param.type_method.option.label"},
                  {"value": "name", "label": "By input name",
                   "label_key": "modules.browser.type.param.type_method.option.name"},
                  {"value": "id", "label": "By element ID",
                   "label_key": "modules.browser.type.param.type_method.option.id"},
                  {"value": "selector", "label": "CSS / XPath selector (advanced)",
                   "label_key": "modules.browser.type.param.type_method.option.selector"},
              ],
              group=FieldGroup.BASIC),
        field("target", type="string",
              label="Input field identifier",
              label_key="modules.browser.type.param.target.label",
              description='e.g. "Enter your email", "Email", "username"',
              description_key="modules.browser.type.param.target.description",
              placeholder="Enter your email",
              showIf={"type_method": {"$in": ["placeholder", "label", "name", "id"]}},
              ui={"widget": "element_picker", "element_types": ["input"],
                  "value_key_from": "type_method",
                  "value_key_map": {
                      "placeholder": "placeholder",
                      "label": "label",
                      "name": "name",
                      "id": "id",
                  }},
              group=FieldGroup.BASIC),
        field("selector", type="string",
              label="CSS/XPath Selector",
              label_key="schema.field.selector",
              description="CSS selector, XPath, or text selector",
              placeholder='input[name="email"], #username',
              showIf={"type_method": {"$in": ["selector"]}},
              ui={"widget": "element_picker", "element_types": ["input"], "value_key": "selector"},
              group=FieldGroup.BASIC),
        field("input_type", type="select",
              label="Input type",
              label_key="modules.browser.type.param.input_type.label",
              description="Type of input field — use Password to mask the value in the builder",
              description_key="modules.browser.type.param.input_type.description",
              default="text",
              options=[
                  {"value": "text", "label": "Text",
                   "label_key": "modules.browser.type.param.input_type.option.text"},
                  {"value": "password", "label": "Password",
                   "label_key": "modules.browser.type.param.input_type.option.password"},
                  {"value": "email", "label": "Email",
                   "label_key": "modules.browser.type.param.input_type.option.email"},
              ],
              group=FieldGroup.BASIC),
        field("text", type="string",
              label="Text to type",
              label_key="modules.browser.type.param.text.label",
              placeholder="Text to type",
              required=True,
              showIf={"input_type": {"$in": ["text", "email"]}},
              group=FieldGroup.BASIC),
        field("sensitive_text", type="string",
              label="Text to type",
              label_key="modules.browser.type.param.text.label",
              placeholder="••••••••",
              required=True,
              format="password",
              secret=True,
              showIf={"input_type": {"$in": ["password"]}},
              group=FieldGroup.BASIC),
        field('delay', type='number', label='Typing Delay (ms)',
              label_key='modules.browser.type.param.delay.label',
              description='Delay between keystrokes in milliseconds',
              description_key='modules.browser.type.param.delay.description',
              default=0, min=0, max=5000, step=10,
              group=FieldGroup.OPTIONS),
        field('clear', type='boolean', label='Clear Field First',
              label_key='modules.browser.type.param.clear.label',
              description='Clear the input field before typing',
              description_key='modules.browser.type.param.clear.description',
              default=True,
              group=FieldGroup.OPTIONS),
        presets.TIMEOUT_MS(default=30000),
    ),
    output_schema={
        'browser': {'type': 'object', 'description': 'Browser session (pass-through for chaining)',
                'description_key': 'modules.browser.type.output.browser.description'},
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.type.output.status.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.type.output.selector.description'},
        'method': {'type': 'string', 'description': 'Type method used'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far these keystrokes were followed: observed when the '
                'field value changed, indeterminate when it did not, accepted '
                'when the field could not be read back'
            ),
            'description_key': 'modules.browser.type.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Type by placeholder',
            'params': {'type_method': 'placeholder', 'target': 'Enter your email', 'text': 'team@flyto2.com'}
        },
        {
            'name': 'Type by label',
            'params': {'type_method': 'label', 'target': 'Email', 'text': 'team@flyto2.com'}
        },
        {
            'name': 'Type password',
            'params': {'type_method': 'placeholder', 'target': 'Password', 'input_type': 'password', 'sensitive_text': '${env.LOGIN_PASSWORD}'}
        },
        {
            'name': 'Type with selector',
            'params': {'type_method': 'selector', 'selector': '#email', 'text': 'team@flyto2.com'}
        },
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserTypeModule(BaseModule):
    """Type Text Module"""

    module_name = "Type Text"
    module_description = "Type text into an input field"
    required_permission = "browser.automation"

    @classmethod
    def sensitive_params(cls, params: Dict[str, Any]) -> frozenset:
        """``text`` carries a credential when the step says so or names one.

        ``sensitive_text`` is already secret in the schema. ``text`` is the
        free-text field, and it holds a password whenever ``input_type`` is
        password or the field being typed into is named like a credential --
        a login step built with ``type_method: label, target: Password``
        and the default ``input_type: text`` is the case that leaked.
        """
        if not isinstance(params, dict):
            return frozenset()
        if str(params.get('input_type') or '').lower() == 'password':
            return frozenset({'text'})
        for key in ('target', 'selector'):
            value = params.get(key)
            if isinstance(value, str) and _SENSITIVE_FIELD_HINT.search(value):
                return frozenset({'text'})
        return frozenset()

    def validate_params(self) -> None:
        method = self.params.get('type_method', 'placeholder')
        raw_selector = self.params.get('selector', '').strip()

        # Backward compatibility: selector provided without type_method → selector mode
        if 'type_method' not in self.params and raw_selector:
            method = 'selector'

        target = self.params.get('target', '').strip()

        # Escape quotes in target for safe selector construction
        escaped = target.replace('"', '\\"') if target else ''

        if method == 'selector':
            if not raw_selector:
                raise ValueError("CSS/XPath selector is required in advanced mode")
            self.selector = raw_selector
        elif method == 'id':
            if not target:
                raise ValueError("Element ID is required")
            self.selector = f'#{target.lstrip("#")}'
        elif method == 'name':
            if not target:
                raise ValueError("Input name is required")
            self.selector = f'input[name="{escaped}"], textarea[name="{escaped}"]'
        elif method == 'label':
            if not target:
                raise ValueError("Label text is required")
            # Tried in order during execute(), explicit associations first:
            # 1. a label wrapping the input
            # 2. label[for=id] -> #id, and aria-labelledby (resolved on the
            #    page, inserted here by execute())
            # 3. aria-label on the field itself
            # 4. structural guesses: the input right after / after the label
            self._label_selectors = [
                f'label:has-text("{escaped}") >> input',
                f'input[aria-label="{escaped}"]',
                f'textarea[aria-label="{escaped}"]',
                f'label:has-text("{escaped}") + input',
                f'label:has-text("{escaped}") ~ input',
            ]
            self.selector = self._label_selectors[0]  # default, may be overridden in execute
        else:  # placeholder (default)
            if not target:
                raise ValueError("Placeholder text is required")
            self.selector = f'input[placeholder="{escaped}"], textarea[placeholder="{escaped}"]'

        self.input_type = self.params.get('input_type', 'text')
        # Merge text from the visible field (text or sensitive_text based on input_type)
        text = self.params.get('text') or self.params.get('sensitive_text') or ''
        if not text:
            raise ValueError("Missing required parameter: text")

        self.method = method
        self.text = text
        self.delay = int(self.params.get('delay') or 0)
        self.clear = bool(self.params.get('clear', True))

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Label method: try multiple selector strategies (label>>input, label+input, aria-label)
        if hasattr(self, '_label_selectors'):
            page = browser.page
            found = False
            associated = await _associated_label_selectors(
                page, self.params.get('target', '').strip(),
            )
            candidates = (
                self._label_selectors[:1] + associated + self._label_selectors[1:]
            )
            for sel in candidates:
                try:
                    count = await page.locator(sel).count()
                    if count > 0:
                        self.selector = sel
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                raise RuntimeError(
                    f"Could not find input field with label \"{self.params.get('target')}\". "
                    f"Tried: label>>input, label[for], aria-labelledby, aria-label, "
                    f"label+input, label~input"
                )

        # Wait for element to be visible before interacting
        await browser.wait(self.selector, state='visible', timeout_ms=10000)

        # Pre-action: refresh element hints after element is confirmed visible
        await browser.get_hints(force=True)

        # Clear field first if requested
        if self.clear:
            await browser.page.fill(self.selector, '')

        # The baseline is read AFTER the clear, so it is the state the
        # keystrokes actually start from. Reading it before would report an
        # unchanged field for the ordinary case of retyping the value that was
        # already there, which is a correct type and not an indeterminate one.
        baseline, baseline_error = await _read_field_value(browser.page, self.selector)

        await browser.type(self.selector, self.text, delay_ms=self.delay)

        after, after_error = await _read_field_value(browser.page, self.selector)

        # Mask sensitive text in return value. The page is asked too: a field
        # that turns out to be <input type=password> is a password field
        # whatever the parameters called it.
        is_password_field = await _is_password_field(browser.page, self.selector)
        is_sensitive = (
            is_password_field
            or bool(self.sensitive_params(self.params))
            or any(
                kw in self.selector.lower()
                for kw in ['password', 'passwd', 'secret', 'token', 'key', 'credential']
            )
        )
        result = {
            "status": "success",
            "selector": self.selector,
            "method": self.method,
            "input_type": self.input_type,
            "text": '***' if is_sensitive else self.text,
            "text_length": len(self.text),
            "outcome": _type_outcome(
                baseline=baseline,
                after=after,
                typed_characters=len(self.text),
                expected=None if baseline is None else baseline + self.text,
                read_error=baseline_error or after_error,
            ),
        }
        if is_sensitive:
            # Tells the engine to redact these parameters wherever it records
            # this step (hooks, trace), including what it learned only now.
            result[SENSITIVE_PARAMS_KEY] = ['text', 'sensitive_text']
        # Post-action: refresh hints (typing may trigger dynamic UI changes)
        hints = await browser.get_hints(force=True)
        browser._snapshot_since_nav = True
        if hints.get('text'):
            result["_page_hint"] = hints["text"][:800]
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
