# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Form Module - Smart form filling

Automatically fills form fields based on a data object.
Supports various input types and can auto-detect field types.

Features:
- Auto-detect input types (text, email, password, select, checkbox, radio)
- Support field mapping with selectors
- Clear fields before filling option
- Submit form option

HOW FAR A FILLED FORM IS FOLLOWED

What this module reported about its own effect was ``success_count``:
``len(filled_fields)``, appended once per key in the caller's own ``data`` dict
for which no exception was raised. On a page where every selector resolves to a
``<div>``, ``browser.type`` still succeeds against it and the count still reads
"all of them". It is `file.write`'s ``bytes_written`` with a form attached.

The measurement that is not that is the field's own state, read out of the live
DOM twice -- once immediately before the fill (after the optional clear, so the
baseline is the state the fill actually starts from) and once after. It is
`browser.type`'s ``page.input_value`` read-back generalised to the four kinds of
control this module writes to:

    text / textarea       value LENGTH, and whether the value equals the target
    select                selectedIndex, and whether the value equals the target
    checkbox              checked
    radio                 which member of the name-group is checked

Never the value itself. The equality is computed inside the page and only the
boolean crosses back, because this module fills password fields and this
envelope is copied into a trace row and a websocket frame.

Per field, the pair of readings gives one of four answers:

    the reading changed                      the fill reached the page
    unchanged, and holds the target value    the field already held it
    unchanged, and does not hold it          nothing we can see moved
    could not be read                        we cannot look at this control

and the step's rung is the strongest thing true of the whole set:

    any field changed                        OBSERVED
    else any field unchanged and wrong       INDETERMINATE
    else any field already correct           ACCEPTED
    else any field filled but unreadable     ACCEPTED
    else nothing was filled at all           INDETERMINATE

"Already correct" is ACCEPTED and not OBSERVED for the one rule this contract
runs on: a checkbox that was already ticked reads identically whether this step
ran or not, so the reading is not evidence of the fill even though the form now
holds what the caller asked for. "Unchanged and wrong" is INDETERMINATE rather
than FAILED for the reason `outcome.py` separates the two -- a readonly input, a
framework-controlled value, a selector that resolved to the wrong node and a
fill that genuinely went nowhere all produce it, and nobody declared a contract
about the field's value.

Nothing here observes the SUBMIT. ``browser.click`` returning is not evidence a
form posted, so a requested submit rides in the envelope as an effect whose
``measured_by`` is None, and it never raises the rung.
"""
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup


#: Reads one control's state out of the live DOM, without letting its value out.
#:
#: The target value is passed IN and compared in the page; only the boolean
#: comes back. The four shapes are deliberately different dicts rather than one
#: normalised record, because comparing before/after is a plain ``!=`` on the
#: whole dict and a normalised record would have to invent a null for every
#: field that does not apply -- which is how two genuinely different states end
#: up comparing equal.
_READ_FIELD_STATE_JS = r"""
([selector, expectedText, expectedChecked]) => {
    let el = null;
    try { el = document.querySelector(selector); } catch (e) { return null; }
    if (!el) return null;

    if (el.type === 'checkbox') {
        return {
            kind: 'checkbox',
            checked: !!el.checked,
            matches: (!!el.checked) === (!!expectedChecked),
        };
    }
    if (el.type === 'radio') {
        const group = Array.from(document.querySelectorAll('input[type="radio"]'))
            .filter(r => r.name === el.name);
        const checked = group.filter(r => r.checked)[0];
        return {
            kind: 'radio',
            group_size: group.length,
            checked_index: checked ? group.indexOf(checked) : -1,
            matches: !!checked && String(checked.value) === String(expectedText),
        };
    }
    if (el.tagName === 'SELECT') {
        return {
            kind: 'select',
            selected_index: el.selectedIndex,
            matches: String(el.value) === String(expectedText),
        };
    }
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        const v = el.value == null ? '' : String(el.value);
        return { kind: 'text', length: v.length, matches: v === String(expectedText) };
    }
    if (el.isContentEditable) {
        const v = el.textContent == null ? '' : String(el.textContent);
        return { kind: 'contenteditable', length: v.length, matches: v === String(expectedText) };
    }
    return null;
}
"""

#: How many field names a single envelope will carry. The envelope lands in a
#: database column; a 200-field form must not make it unbounded.
_MAX_NAMED_FIELDS = 20


async def _read_field_state(browser, selector: str, value: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(state, None)`` when the control could be read, ``(None, why)`` when not.

    Failing here is not a failure of the fill. A control inside a shadow root, a
    canvas-backed editor, or a selector this module built that resolves to
    something with no value at all are all perfectly fillable by some other
    path; all that is lost is our ability to look, and the rung is lowered to
    match.
    """
    try:
        state = await browser.evaluate(
            _READ_FIELD_STATE_JS, [selector, str(value), bool(value)]
        )
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
    if not isinstance(state, dict):
        return None, "the selector matched no control this module knows how to read"
    return state, None


def _classify_field(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> str:
    """What the pair of readings says about one field. Four answers, no rung.

    ``matches`` participates in the equality on purpose: replacing ``abc`` with
    ``xyz`` leaves the length alone, and without the in-page comparison that
    would read as an unchanged field. With it, the state moved.
    """
    if before is None or after is None:
        return 'not_read'
    if before != after:
        return 'changed'
    if after.get('matches') is True:
        return 'already_correct'
    return 'unchanged'


def _form_outcome(
    *,
    measurements: List[Dict[str, Any]],
    offered_fields: int,
    filled_count: int,
    failed_count: int,
    submit_requested: bool,
    submit_dispatched: bool,
) -> Dict[str, Any]:
    """The rung this fill earned, and the readings that earned it."""
    def named(result: str) -> List[str]:
        return [m['name'] for m in measurements if m['result'] == result][:_MAX_NAMED_FIELDS]

    counts = {
        result: sum(1 for m in measurements if m['result'] == result)
        for result in ('changed', 'unchanged', 'already_correct', 'not_read')
    }

    effects: List[Dict[str, Any]] = [{
        'kind': 'fields_offered',
        'count': offered_fields,
        'measured_by': 'len() of the data parameter',
        'detail': (
            'How many keys the caller handed this module. No browser call '
            'contributes to it: it reads identically whether every field was '
            'filled, some were, or none were.'
        ),
    }]

    if measurements:
        effects.append({
            'kind': 'field_states_observed',
            'changed': counts['changed'],
            'unchanged': counts['unchanged'],
            'already_correct': counts['already_correct'],
            'not_read': counts['not_read'],
            'unchanged_fields': named('unchanged'),
            'not_read_fields': named('not_read'),
            'measured_by': (
                'document.querySelector(selector) state, read out of the live '
                'DOM before and after each fill'
            ),
            'detail': (
                'Lengths, indices and booleans only. No field value appears '
                'here: the target is compared inside the page and only the '
                'result crosses back, because this module fills passwords.'
            ),
        })

    if failed_count:
        effects.append({
            'kind': 'fields_not_filled',
            'count': failed_count,
            'detail': (
                'The fill raised for these fields and the error is in '
                'failed_fields. They contributed no reading either way.'
            ),
        })

    if submit_requested:
        effects.append({
            'kind': 'form_submit_dispatched' if submit_dispatched else 'form_submit_not_dispatched',
            'measured_by': None,
            'detail': (
                'A click was sent to the submit control and Playwright did not '
                'raise. Nothing was read back: a click that lands is not '
                'evidence a form posted, so this never raises the rung.'
            ) if submit_dispatched else (
                'A submit was requested and the click raised; the error is in '
                'failed_fields under __submit__.'
            ),
        })

    if counts['changed']:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: a predicate was evaluated and it was ours. No caller
            # asked for "these controls end up holding exactly this".
            claim_by=ClaimBy.INFERRED,
            effects=effects,
        )

    if counts['unchanged']:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=effects + [{
                'kind': 'field_states_unchanged',
                'predicate': 'the field state after the fill differs from the state before it',
                'count': counts['unchanged'],
                'detail': (
                    'These fields hold what they held before the fill and it is '
                    'not what was asked for. That reads the same whether '
                    'nothing was filled, the input is readonly, a framework '
                    'reset it, or the selector resolved to a different node. We '
                    'cannot say which, so this is indeterminate rather than '
                    'failed.'
                ),
            }],
        )

    if counts['already_correct']:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=effects + [{
                'kind': 'field_states_already_correct',
                'count': counts['already_correct'],
                'measured_by': None,
                'detail': (
                    'Every readable field already held the value it was being '
                    'given, so nothing moved. The form holds what was asked '
                    'for, but that reading is identical whether this step ran '
                    'or not, and so it is not evidence of the fill.'
                ),
            }],
        )

    if counts['not_read']:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=effects + [{
                'kind': 'field_states_not_observed',
                'count': counts['not_read'],
                'measured_by': None,
                'detail': (
                    'The fills completed and did not raise. No field could be '
                    'read back, so nothing followed them into the page.'
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=effects + [{
            'kind': 'no_field_was_filled',
            'measured_by': None,
            'detail': (
                'Every field raised, and the errors are in failed_fields. Those '
                'errors include Playwright timeouts, which say we stopped '
                'waiting rather than that nothing happened, so this is '
                'indeterminate rather than failed.'
            ),
        }],
    )


@register_module(
    module_id='browser.form',
    version='1.0.0',
    category='browser',
    tags=['browser', 'form', 'input', 'automation', 'ssrf_protected'],
    label='Fill Form',
    label_key='modules.browser.form.label',
    description='Smart form filling with automatic field detection. Run browser.snapshot first to find the correct selectors from the real page DOM.',
    description_key='modules.browser.form.description',
    icon='FormInput',
    color='#8B5CF6',

    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field(
            'form_selector',
            type='string',
            label='Form Selector',
            label_key='modules.browser.form.params.form_selector.label',
            description='CSS selector for the form element (optional)',
            placeholder='form, #login-form',
            required=False,
            ui={"widget": "element_picker", "element_types": ["input"], "value_key": "selector"},
            group=FieldGroup.BASIC,
        ),
        field(
            'data',
            type='object',
            label='Form Data',
            label_key='modules.browser.form.params.data.label',
            description='Key-value pairs to fill (key = field name/id, value = content)',
            required=True,
            group=FieldGroup.BASIC,
        ),
        field(
            'field_mapping',
            type='object',
            label='Field Mapping',
            label_key='modules.browser.form.params.field_mapping.label',
            description='Custom selector mapping {fieldName: selector}',
            required=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'clear_before_fill',
            type='boolean',
            label='Clear Before Fill',
            label_key='modules.browser.form.params.clear_before_fill.label',
            description='Clear existing field values before filling',
            default=True,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'submit',
            type='boolean',
            label='Submit Form',
            label_key='modules.browser.form.params.submit.label',
            description='Submit form after filling',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
        field(
            'submit_selector',
            type='string',
            label='Submit Button Selector',
            label_key='modules.browser.form.params.submit_selector.label',
            description='CSS selector for submit button',
            placeholder='button[type="submit"], input[type="submit"]',
            required=False,
            showIf={"submit": {"$in": [True]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'delay_between_fields_ms',
            type='number',
            label='Delay Between Fields (ms)',
            label_key='modules.browser.form.params.delay_between_fields_ms.label',
            description='Delay between filling each field (for more human-like behavior)',
            default=100,
            min=0,
            max=5000,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'filled_fields': {
            'type': 'array',
            'description': 'List of fields that were filled',
            'description_key': 'modules.browser.form.output.filled_fields.description'
        },
        'failed_fields': {
            'type': 'array',
            'description': 'List of fields that failed to fill',
            'description_key': 'modules.browser.form.output.failed_fields.description'
        },
        'submitted': {
            'type': 'boolean',
            'description': 'Whether form was submitted',
            'description_key': 'modules.browser.form.output.submitted.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this fill was followed: observed when a field state '
                'changed in the page, indeterminate when a readable field did '
                'not move, accepted when the fields could not be read back or '
                'already held the target value. The submit is never observed.'
            ),
            'description_key': 'modules.browser.form.output.outcome.description'
        }
    },
    examples=[
        {
            'name': 'Fill login form',
            'params': {
                'data': {
                    'email': 'team@flyto2.com',
                    'password': 'secret123'
                },
                'submit': True
            }
        },
        {
            'name': 'Fill with custom selectors',
            'params': {
                'data': {
                    'username': 'john_doe',
                    'bio': 'Hello world'
                },
                'field_mapping': {
                    'username': '#user-name-input',
                    'bio': 'textarea.bio-field'
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=60000,
    required_permissions=['browser.automation'],
)
class BrowserFormModule(BaseModule):
    """
    Smart form filling module.

    Fills form fields based on a data object with automatic
    field type detection and optional custom selector mapping.
    """

    module_name = "Fill Form"
    module_description = "Smart form filling with automatic field detection"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.form_selector = self.params.get('form_selector')
        self.data = self.params.get('data', {})
        self.field_mapping = self.params.get('field_mapping', {})
        self.clear_before_fill = self.params.get('clear_before_fill', True)
        self.submit = self.params.get('submit', False)
        self.submit_selector = self.params.get('submit_selector')
        self.delay_between_fields_ms = self.params.get('delay_between_fields_ms', 100)

        if not isinstance(self.data, dict):
            raise ValueError("data must be an object")

        if not self.data:
            raise ValueError("data cannot be empty")

    async def execute(self) -> Dict[str, Any]:
        import asyncio

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        filled_fields = []
        failed_fields = []
        measurements: List[Dict[str, Any]] = []

        for field_name, value in self.data.items():
            try:
                # Get selector for this field
                selector = self._get_field_selector(field_name)

                # Clear field if requested
                if self.clear_before_fill:
                    await browser.evaluate('''
                        (selector) => {
                            const el = document.querySelector(selector);
                            if (el) {
                                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                                    el.value = '';
                                }
                            }
                        }
                    ''', selector)

                # The baseline is read AFTER the clear, so it is the state the
                # fill actually starts from. Reading it before would report an
                # unchanged field for the ordinary case of rewriting a value
                # that was already there, which is a correct fill.
                before, before_error = await _read_field_state(browser, selector, value)

                # Fill the field based on type
                await self._fill_field(browser, selector, value)

                after, after_error = await _read_field_state(browser, selector, value)
                measurements.append({
                    'name': field_name,
                    'result': _classify_field(before, after),
                    'kind': (after or before or {}).get('kind'),
                    'reason': before_error or after_error,
                })

                filled_fields.append({
                    'name': field_name,
                    'selector': selector,
                    'value': value if not self._is_sensitive(field_name) else '***'
                })

                # Delay between fields
                if self.delay_between_fields_ms > 0:
                    await asyncio.sleep(self.delay_between_fields_ms / 1000)

            except Exception as e:
                failed_fields.append({
                    'name': field_name,
                    'error': str(e)
                })

        # Submit form if requested
        submitted = False
        submit_requested = bool(self.submit and len(filled_fields) > 0)
        if submit_requested:
            try:
                submit_sel = self.submit_selector or 'button[type="submit"], input[type="submit"]'
                await browser.click(submit_sel)
                submitted = True
            except Exception as e:
                failed_fields.append({
                    'name': '__submit__',
                    'error': str(e)
                })

        # Post-form: refresh hints (form submission may navigate or change DOM)
        result = {
            'status': 'success',
            'filled_fields': filled_fields,
            'failed_fields': failed_fields,
            'submitted': submitted,
            'total_fields': len(self.data),
            'success_count': len(filled_fields),
            'fail_count': len(failed_fields),
            'outcome': _form_outcome(
                measurements=measurements,
                offered_fields=len(self.data),
                filled_count=len(filled_fields),
                failed_count=len(failed_fields),
                submit_requested=submit_requested,
                submit_dispatched=submitted,
            ),
        }
        browser._snapshot_since_nav = True
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result

    def _get_field_selector(self, field_name: str) -> str:
        """Get CSS selector for a field."""
        # Check custom mapping first
        if field_name in self.field_mapping:
            return self.field_mapping[field_name]

        # Build form prefix if form_selector is specified
        prefix = f'{self.form_selector} ' if self.form_selector else ''

        # Try common patterns (escape quotes in field name for safe CSS selectors)
        escaped = field_name.replace('"', '\\"')
        selectors = [
            f'{prefix}[name="{escaped}"]',
            f'{prefix}#{field_name}',
            f'{prefix}[id="{escaped}"]',
            f'{prefix}[data-field="{escaped}"]',
        ]

        return selectors[0]  # Use first pattern by default

    async def _fill_field(self, browser, selector: str, value: Any) -> None:
        """Fill a field based on its type."""
        # Get element info to determine type
        element_info = await browser.evaluate('''
            (selector) => {
                const el = document.querySelector(selector);
                if (!el) return null;
                return {
                    tagName: el.tagName,
                    type: el.type || '',
                    isSelect: el.tagName === 'SELECT',
                    isCheckbox: el.type === 'checkbox',
                    isRadio: el.type === 'radio'
                };
            }
        ''', selector)

        if not element_info:
            # Try to find by name attribute
            await browser.type(selector, str(value))
            return

        if element_info.get('isSelect'):
            # Handle select dropdown
            await browser.evaluate('''
                ([selector, value]) => {
                    document.querySelector(selector).value = value;
                    document.querySelector(selector).dispatchEvent(new Event('change', { bubbles: true }));
                }
            ''', [selector, str(value)])
        elif element_info.get('isCheckbox'):
            # Handle checkbox
            should_check = bool(value)
            await browser.evaluate('''
                ([selector, shouldCheck]) => {
                    const cb = document.querySelector(selector);
                    if (cb.checked !== shouldCheck) {
                        cb.click();
                    }
                }
            ''', [selector, should_check])
        elif element_info.get('isRadio'):
            # Handle radio button
            #
            # RAW string, and it has to be. As a normal triple-quoted literal
            # Python collapsed every `\\` to one backslash, so the JS the page
            # received began `value.replace(/\/g, ...)` -- an escaped slash
            # inside a regex literal, which never terminates it. Chromium
            # answered `SyntaxError: Invalid regular expression` for EVERY radio
            # fill this module has ever attempted; the per-field `except` below
            # swallowed it into `failed_fields` and the step still returned
            # `status: "success"`. Found by giving this module an outcome rung
            # and then asking what the rung was measuring.
            await browser.evaluate(r'''
                ([selector, value]) => {
                    const escaped = value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
                    const radio = document.querySelector(selector + '[value="' + escaped + '"]') ||
                                 document.querySelector(selector);
                    if (radio) radio.click();
                }
            ''', [selector, str(value)])
        else:
            # Regular text input
            await browser.type(selector, str(value))

    def _is_sensitive(self, field_name: str) -> bool:
        """Check if field contains sensitive data."""
        sensitive_keywords = ['password', 'secret', 'token', 'key', 'credit', 'card', 'cvv', 'ssn']
        return any(kw in field_name.lower() for kw in sensitive_keywords)
