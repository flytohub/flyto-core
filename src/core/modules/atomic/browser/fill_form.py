# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Fill Form Module - fill, upload and submit a whole form in one call

WHY THIS EXISTS

An agent that can only type one field per call needs one model round-trip per
field, per select, per upload and for the submit. A ten-field form costs a dozen
rounds, each one a full model turn, even when the agent already knows every
value after reading the page once. This module takes every field at once, so
"read the form, then fill it" is two calls however many fields there are.

HOW A FIELD IS FOUND

By its visible label, with the resolver ``browser.type`` uses
(``_label_resolve.py``): ``label[for]``/wrapping label, ``aria-labelledby``,
``aria-label``, then ``label >> control``, ``label + control`` and
``label ~ control``; exact text before partial, visible before hidden. Or by a
CSS selector. A radio group can also be named by its ``<fieldset>`` legend or
``role=radiogroup`` name, with the option chosen by ``value``.

ALL OR NOTHING BEFORE THE FIRST WRITE

Every field, every upload and the submit control are resolved before anything is
written. If any of them is missing the module returns ``ok: false`` with the
list and has typed nothing, so a caller never has to work out which half of a
form it filled. A fill that then raises (an option that does not exist, text in
a number input) also returns ``ok: false``, and the form is not submitted. A
form whose own constraint validation fails (an empty required field) is not
submitted either; the invalid controls are listed instead.

WHAT IS READ BACK

After the fill, each control is read back from the live DOM: text value
equality, the selected option, the checked state, the attached file names.
A password field, or a field whose label or selector names a credential, or a
value passed as ``sensitive_value``, never has its value returned or logged --
only whether it matched -- and the step tells the engine to redact ``fields``
from its records, exactly as ``browser.type`` does for ``text``.

After a submit the module waits for the caller's confirmation (a selector or a
text that appears) or, without one, for the page to settle, and returns the
confirmation's text as the readback.
"""
import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....engine.redaction import SENSITIVE_PARAMS_KEY
from ....utils import validate_path_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup
from ._label_resolve import (
    _SENSITIVE_FIELD_HINT,
    _associated_label_selectors,
    label_fallback_selectors,
)
from ._settle import (
    RequestTracker,
    first_state,
    install_dom_watch,
    next_mutation,
    settle_dom,
    settle_new_document,
    stop_dom_watch,
)

logger = logging.getLogger(__name__)

#: Every control a value can be written to, as one CSS list for the in-page
#: ranking. File inputs are uploads and are resolved separately.
_FILLABLE = (
    'input:not([type=hidden]):not([type=button]):not([type=submit])'
    ':not([type=reset]):not([type=image]):not([type=file]), textarea, select,'
    ' [contenteditable=""], [contenteditable="true"], [role=textbox]'
)

#: The static fallbacks need one element per selector: ``label + a, b`` would
#: apply the combinator to ``a`` only.
_FALLBACK_CONTROLS = (
    None,  # text inputs, plus the aria-label pair (browser.type's own list)
    'textarea',
    'select',
    'input[type=checkbox]',
    'input[type=radio]',
)

_FILE_INPUT = 'input[type=file]'

_DEFAULT_FIELD_TIMEOUT_MS = 5000
_DEFAULT_RESOLVE_WAIT_MS = 3000
_DEFAULT_CONFIRM_TIMEOUT_MS = 10000
_MAX_READBACK_CHARS = 2000
_MAX_VALUE_ECHO_CHARS = 200

_TRUE_WORDS = frozenset({'true', 'yes', 'on', '1', 'checked', 'y'})
_FALSE_WORDS = frozenset({'false', 'no', 'off', '0', 'unchecked', 'n', ''})

POSTCONDITION = (
    'every requested field and upload reads back holding its value, and, when '
    'a confirmation is requested, it appeared after the submit'
)

_DESCRIBE_JS = r"""
(el) => {
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  let kind = 'other';
  if (tag === 'select') kind = 'select';
  else if (tag === 'textarea') kind = 'text';
  else if (tag === 'input') {
    kind = type === 'checkbox' ? 'checkbox'
      : type === 'radio' ? 'radio'
      : type === 'file' ? 'file' : 'text';
  } else if (el.isContentEditable || el.getAttribute('role') === 'textbox') kind = 'text';
  return {kind, tag, type, name: el.getAttribute('name') || '', multiple: !!el.multiple};
}
"""

#: Index of the option whose value, else exact text, else partial text, matches
#: each wanted entry; ``-1`` for one that matches nothing. Decided in the page so
#: a missing option fails at once instead of after Playwright's actionability wait.
_SELECT_INDICES_JS = r"""
(el, wanted) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const options = [...el.options];
  return wanted.map((raw) => {
    const w = norm(String(raw));
    let i = options.findIndex((o) => o.value === String(raw));
    if (i < 0) i = options.findIndex((o) => norm(o.text) === w);
    if (i < 0 && w) i = options.findIndex((o) => norm(o.text).includes(w));
    return i;
  });
}
"""

#: Index, among the document's radios sharing this radio's name, of the option
#: whose value, else label text, matches ``want``; ``-1`` when none does.
_RADIO_OPTION_JS = r"""
(el, want) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const w = norm(String(want));
  const group = el.name
    ? [...document.querySelectorAll('input[type=radio]')].filter((r) => r.name === el.name)
    : [el];
  const text = (r) => [...(r.labels || [])].map((l) => l.textContent).join(' ')
    || r.getAttribute('aria-label') || '';
  let i = group.findIndex((r) => r.value === String(want));
  if (i < 0) i = group.findIndex((r) => norm(text(r)) === w);
  if (i < 0 && w) i = group.findIndex((r) => norm(text(r)).includes(w));
  return {index: i, name: el.name || ''};
}
"""

#: What the control holds now. ``value`` is only returned for a control the
#: caller did not mark secret; the comparison itself happens here.
_READBACK_JS = r"""
(el, [expected, secret]) => {
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  if (type === 'checkbox' || type === 'radio') {
    return {checked: !!el.checked, matches: !!el.checked === !!expected};
  }
  if (type === 'file') {
    const names = [...(el.files || [])].map((f) => f.name);
    return {files: names, matches: names.includes(String(expected))};
  }
  if (tag === 'select') {
    const chosen = [...el.selectedOptions];
    const wanted = Array.isArray(expected) ? expected.map(String) : [String(expected)];
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const hit = (w) => chosen.some((o) => o.value === w || norm(o.text) === norm(w)
      || (norm(w) && norm(o.text).includes(norm(w))));
    return {
      value: secret ? null : chosen.map((o) => o.value).join(', '),
      text: secret ? null : chosen.map((o) => o.text.trim()).join(', '),
      matches: wanted.every(hit),
    };
  }
  const v = ('value' in el && tag !== 'div') ? String(el.value ?? '') : String(el.innerText ?? '');
  return {value: secret ? null : v, length: v.length, matches: v === String(expected)};
}
"""

#: Constraint-validation failures of the form a submit control belongs to.
#: ``validity`` is read rather than ``checkValidity()`` called, so no ``invalid``
#: event fires and no browser bubble opens.
_INVALID_CONTROLS_JS = r"""
(el) => {
  const form = el.form || el.closest('form');
  if (!form) return [];
  const labelOf = (c) => {
    const l = c.labels && c.labels[0];
    return ((l && l.textContent) || c.getAttribute('aria-label') || c.name || c.id || c.tagName)
      .replace(/\s+/g, ' ').trim();
  };
  return [...form.elements]
    .filter((c) => c.willValidate && !c.validity.valid)
    .map((c) => ({label: labelOf(c), message: c.validationMessage || 'invalid'}));
}
"""


def _truthy(value: Any) -> Optional[bool]:
    """``True``/``False`` for a value that reads as a switch, else ``None``."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    word = str(value).strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return None


def _target_name(item: Dict[str, Any]) -> str:
    """How a field is named in results: its label, else its selector."""
    return str(item.get('label') or item.get('selector') or '').strip()


def _names_a_credential(item: Dict[str, Any]) -> bool:
    return any(
        isinstance(item.get(key), str) and _SENSITIVE_FIELD_HINT.search(item[key])
        for key in ('label', 'selector')
    )


def _value_of(item: Dict[str, Any]) -> Any:
    if 'sensitive_value' in item and item['sensitive_value'] is not None:
        return item['sensitive_value']
    return item.get('value')


def _echo(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_VALUE_ECHO_CHARS:
        return value[:_MAX_VALUE_ECHO_CHARS] + '...'
    return value


def _fill_outcome(
    *,
    fields: List[Dict[str, Any]],
    uploads: List[Dict[str, Any]],
    submit_requested: bool,
    submitted: bool,
    confirm_requested: bool,
    confirmed: bool,
    settled: Optional[str],
) -> Dict[str, Any]:
    entries = fields + uploads
    mismatched = [e['name'] for e in entries if e.get('matches') is False][:20]
    effects: List[Dict[str, Any]] = [{
        'kind': 'fields_read_back',
        'count': len(entries),
        'mismatched': mismatched,
        'measured_by': 'each control read back from the live DOM after the fill',
        'detail': 'Equality is computed in the page; secret values never cross back.',
    }]
    if submit_requested:
        effects.append({
            'kind': 'external.record.changed' if confirmed else 'form_submit_dispatched',
            'measured_by': 'the caller\'s confirmation appeared' if confirmed else None,
            'settled': settled,
        })
    all_match = not mismatched
    if submit_requested and confirm_requested:
        if confirmed and all_match:
            return envelope(Outcome.VERIFIED, claim_by=ClaimBy.CALLER,
                            postcondition=POSTCONDITION, effects=effects)
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.CALLER, effects=effects)
    if submit_requested:
        # A click that lands is not evidence the record was stored.
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.INFERRED, effects=effects)
    if all_match:
        return envelope(Outcome.VERIFIED, claim_by=ClaimBy.INFERRED,
                        postcondition=POSTCONDITION, effects=effects)
    return envelope(Outcome.OBSERVED, claim_by=ClaimBy.INFERRED, effects=effects)


_PARAMS_SCHEMA = compose(
    field(
        'fields',
        type='array',
        label='Fields',
        label_key='modules.browser.fill_form.params.fields.label',
        description=(
            'Every field to fill, in order. Each item is {"label": visible label text, '
            '"value": ...} or {"selector": CSS, "value": ...}. Value types: text for '
            'inputs/textarea/date (YYYY-MM-DD), option value or option text for a '
            'select (a list for a multi-select), true/false for a checkbox, the option '
            'value or text for a radio group. Put a credential in "sensitive_value" instead '
            'of "value".'
        ),
        required=False,
        items={
            'type': 'object',
            'properties': {
                'label': {'type': 'string', 'description': 'Visible label text of the field'},
                'selector': {'type': 'string', 'description': 'CSS selector, instead of label'},
                'value': {'description': 'Value to fill'},
                # No ``format`` hint and no credential words in this schema:
                # it is published on /v1/capabilities. The value is redacted by
                # its key name (``sensitive_*``) wherever the step is recorded.
                'sensitive_value': {'type': 'string',
                                    'description': 'Use instead of value for a credential; never echoed or logged'},
            },
        },
        group=FieldGroup.BASIC,
    ),
    field(
        'uploads',
        type='array',
        label='File uploads',
        label_key='modules.browser.fill_form.params.uploads.label',
        description='Files to attach: [{"label": "Photo", "path": "/path/to/file.png"}] or with "selector".',
        required=False,
        items={
            'type': 'object',
            'properties': {
                'label': {'type': 'string'},
                'selector': {'type': 'string'},
                'path': {'type': 'string'},
            },
        },
        group=FieldGroup.BASIC,
    ),
    field(
        'submit',
        type='object',
        label='Submit',
        label_key='modules.browser.fill_form.params.submit.label',
        description=(
            'Submit after filling: {"label": button text} or {"selector": CSS}. '
            '{} submits with the form\'s own submit button. Omit to fill without submitting.'
        ),
        required=False,
        group=FieldGroup.BASIC,
    ),
    field(
        'confirm',
        type='object',
        label='Confirmation',
        label_key='modules.browser.fill_form.params.confirm.label',
        description=(
            'What proves the submit worked: {"selector": CSS} and/or {"text": "Saved"}, '
            'optional "timeout_ms" (default 10000). The text of the matched element is '
            'returned as readback. Without it the module waits for the page to settle.'
        ),
        required=False,
        group=FieldGroup.OPTIONS,
    ),
    field(
        'field_timeout_ms',
        type='number',
        label='Per-field timeout (ms)',
        label_key='modules.browser.fill_form.params.field_timeout_ms.label',
        description='How long one fill, upload or click may wait for its control to be actionable.',
        default=_DEFAULT_FIELD_TIMEOUT_MS,
        min=100,
        max=60000,
        group=FieldGroup.ADVANCED,
    ),
    field(
        'resolve_wait_ms',
        type='number',
        label='Wait for fields (ms)',
        label_key='modules.browser.fill_form.params.resolve_wait_ms.label',
        description='How long to wait for fields that are not on the page yet (a form still rendering).',
        default=_DEFAULT_RESOLVE_WAIT_MS,
        min=0,
        max=30000,
        group=FieldGroup.ADVANCED,
    ),
)

# Top-level finite bounds, as capability_contract._check_params_schema asks of
# an actuating contract's numeric parameters; field() keeps them under
# ``validation`` only, and declaring them costs nothing here.
for _name in ('field_timeout_ms', 'resolve_wait_ms'):
    _PARAMS_SCHEMA[_name]['min'] = _PARAMS_SCHEMA[_name]['validation']['min']
    _PARAMS_SCHEMA[_name]['max'] = _PARAMS_SCHEMA[_name]['validation']['max']


@register_module(
    module_id='browser.fill_form',
    version='1.0.0',
    category='browser',
    tags=['browser', 'form', 'input', 'upload', 'submit', 'automation', 'ssrf_protected'],
    label='Fill Whole Form',
    label_key='modules.browser.fill_form.label',
    description=(
        'Fill every field of a form in ONE call: text, textarea, number, date, select, '
        'radio, checkbox and file uploads, found by their visible label text (or a CSS '
        'selector), then optionally submit and wait for a confirmation. Read the page '
        'once (browser.snapshot), then call this once with all fields instead of one '
        'browser.type/select/upload/click per field. Every field is located before '
        'anything is typed; if any is missing it returns ok=false with the list and '
        'fills nothing.'
    ),
    description_key='modules.browser.fill_form.description',
    icon='FormInput',
    color='#8B5CF6',

    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=_PARAMS_SCHEMA,
    output_schema={
        'ok': {'type': 'boolean', 'description': 'True only when every field was found and filled (and, when asked, the submit was confirmed)'},
        'fields': {'type': 'array', 'description': 'Per-field result: name, kind, selector, matches, value (masked for credentials)'},
        'uploads': {'type': 'array', 'description': 'Per-upload result: name, selector, files, matches'},
        'missing': {'type': 'array', 'description': 'Fields, uploads or the submit control that could not be found'},
        'invalid': {'type': 'array', 'description': 'Controls the form itself reported invalid, so it was not submitted'},
        'submitted': {'type': 'boolean', 'description': 'Whether the submit control was clicked'},
        'confirmed': {'type': 'boolean', 'description': 'Whether the requested confirmation appeared'},
        'readback': {'type': 'string', 'description': 'Text of the confirmation element, else the page text after the action'},
        'url': {'type': 'string', 'description': 'Page URL after the action'},
        'outcome': {'type': 'object', 'description': 'Outcome envelope'},
    },
    examples=[
        {
            'name': 'Fill and submit a report',
            'params': {
                'fields': [
                    {'label': 'Result', 'value': 'Delivered'},
                    {'label': 'Distance (cm)', 'value': 120},
                    {'label': 'Location', 'value': 'Room 501'},
                    {'label': 'Notes', 'value': 'Arrived without incident'},
                ],
                'uploads': [{'label': 'Photo', 'path': '/tmp/evidence.png'}],
                'submit': {'label': 'Submit'},
                'confirm': {'text': 'Saved'},
            },
        },
        {
            'name': 'Fill by selector without submitting',
            'params': {
                'fields': [
                    {'selector': '#email', 'value': 'team@flyto2.com'},
                    {'selector': '#agree', 'value': True},
                ],
            },
        },
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=120000,
    required_permissions=['browser.automation'],
    postcondition=POSTCONDITION,
    provides_capability='browser.fill_form',
    # A submit writes to an external system: consequence level 3, "external
    # write", which is what ``controlled`` without ``actuates`` grades to.
    # ``actuates`` is level 4, a real-world (physical) effect; hosts put it
    # behind a DANGER_FULL confirmation (flyto-ai permissions.py), which would
    # grade one fill_form above the browser.type calls it replaces.
    contract={
        'actuates': False,
        'safety_class': 'controlled',
        'requires_safe_stop': False,
        'cancellable': True,
        'idempotent': False,
        'effects': ['external.record.changed'],
    },
)
class BrowserFillFormModule(BaseModule):
    """Fill, upload and submit a whole form in one call."""

    module_name = "Fill Whole Form"
    module_description = "Fill every field of a form in one call"
    required_permission = "browser.automation"

    @classmethod
    def sensitive_params(cls, params: Dict[str, Any]) -> frozenset:
        """``fields`` carries a credential when any field is named like one.

        A ``sensitive_value`` is already redacted by its name wherever the step
        is recorded. A ``value`` typed into a field labelled "Password" is the
        case ``browser.type`` learned to catch; here the whole ``fields`` list
        is withheld, as ``browser.type`` withholds the whole ``text``.
        """
        if not isinstance(params, dict):
            return frozenset()
        for item in params.get('fields') or ():
            if isinstance(item, dict) and _names_a_credential(item) and item.get('value') not in (None, ''):
                return frozenset({'fields'})
        return frozenset()

    def validate_params(self) -> None:
        fields = self.params.get('fields') or []
        uploads = self.params.get('uploads') or []
        if not isinstance(fields, list) or not isinstance(uploads, list):
            raise ValueError("fields and uploads must be lists")
        if not fields and not uploads:
            raise ValueError("Provide at least one item in fields or uploads")

        self.fields: List[Dict[str, Any]] = []
        for index, item in enumerate(fields):
            if not isinstance(item, dict) or not _target_name(item):
                raise ValueError(f"fields[{index}] needs a 'label' or a 'selector'")
            if 'value' not in item and 'sensitive_value' not in item:
                raise ValueError(f"fields[{index}] ({_target_name(item)}) needs a 'value'")
            self.fields.append(item)

        self.uploads: List[Dict[str, Any]] = []
        for index, item in enumerate(uploads):
            if not isinstance(item, dict) or not _target_name(item):
                raise ValueError(f"uploads[{index}] needs a 'label' or a 'selector'")
            if not item.get('path'):
                raise ValueError(f"uploads[{index}] ({_target_name(item)}) needs a 'path'")
            # SECURITY: the file's bytes go to the visited page; same read
            # boundary as browser.upload (GHSA-wc94-386q-5478).
            resolved = validate_path_with_env_config(str(item['path']))
            path = Path(resolved)
            if not path.is_file():
                raise ValueError(f"uploads[{index}]: file not found: {item['path']}")
            self.uploads.append({**item, 'path': str(path)})

        submit = self.params.get('submit')
        if submit is True:
            submit = {}
        if submit is not None and submit is not False and not isinstance(submit, dict):
            raise ValueError("submit must be an object such as {\"label\": \"Submit\"}")
        self.submit: Optional[Dict[str, Any]] = submit if isinstance(submit, dict) else None

        confirm = self.params.get('confirm')
        if confirm is not None and not isinstance(confirm, dict):
            raise ValueError("confirm must be an object such as {\"text\": \"Saved\"}")
        if confirm and not (confirm.get('selector') or confirm.get('text')):
            raise ValueError("confirm needs a 'selector' or a 'text'")
        if confirm and self.submit is None:
            raise ValueError("confirm only applies when submit is given")
        self.confirm: Optional[Dict[str, Any]] = confirm or None

        self.field_timeout = int(self.params.get('field_timeout_ms') or _DEFAULT_FIELD_TIMEOUT_MS)
        wait = self.params.get('resolve_wait_ms')
        self.resolve_wait = int(_DEFAULT_RESOLVE_WAIT_MS if wait is None else wait)

    # ------------------------------------------------------------------ resolve

    async def _first_present(self, page, selectors: List[str]):
        """The first selector that matches anything, as a locator, else None."""
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    return selector, locator.first
            except Exception:  # noqa: BLE001 - an unparseable candidate is just not it
                continue
        return None, None

    async def _resolve_control(self, page, item: Dict[str, Any], *, upload: bool):
        """``(selector, locator)`` for one field or upload, ``(None, None)`` if absent."""
        if item.get('selector'):
            return await self._first_present(page, [str(item['selector'])])
        label = str(item['label']).strip()
        if upload:
            candidates = await _associated_label_selectors(page, label, accept=_FILE_INPUT)
            candidates += label_fallback_selectors(label, _FILE_INPUT)
        else:
            candidates = await _associated_label_selectors(page, label, accept=_FILLABLE)
            for control in _FALLBACK_CONTROLS:
                candidates += label_fallback_selectors(label, control)
        selector, locator = await self._first_present(page, candidates)
        if locator is None and not upload:
            return await self._resolve_radio_group(page, label)
        return selector, locator

    async def _resolve_radio_group(self, page, label: str):
        """A radio group named by its ``<fieldset>`` legend or radiogroup name."""
        groups = [
            page.locator('fieldset').filter(has=page.locator('legend', has_text=label)),
            page.get_by_role('radiogroup', name=label),
        ]
        for group in groups:
            try:
                radio = group.first.locator('input[type=radio]')
                if await radio.count() > 0:
                    return f'radio group "{label}"', radio.first
            except Exception:  # noqa: BLE001
                continue
        return None, None

    async def _resolve_submit(self, page, first_control):
        submit = self.submit or {}
        if submit.get('selector'):
            return await self._first_present(page, [str(submit['selector'])])
        if submit.get('label'):
            label = str(submit['label']).strip()
            escaped = label.replace('\\', '\\\\').replace('"', '\\"')
            candidates = [
                page.get_by_role('button', name=label, exact=True),
                page.get_by_role('button', name=label),
                page.locator(f'input[type=submit][value="{escaped}"]'),
            ]
            for locator in candidates:
                try:
                    count = await locator.count()
                except Exception:  # noqa: BLE001
                    continue
                for index in range(min(count, 10)):
                    if await locator.nth(index).is_visible():
                        return f'button "{label}"', locator.nth(index)
                if count:
                    return f'button "{label}"', locator.first
            return None, None
        if first_control is None:
            return await self._first_present(page, ['form button[type=submit], form input[type=submit]'])
        form_submit = first_control.locator('xpath=ancestor::form[1]').locator(
            'button[type=submit], input[type=submit], button:not([type])'
        )
        if await form_submit.count() > 0:
            return "the form's submit button", form_submit.first
        return None, None

    async def _resolve_all(self, page) -> Tuple[list, list, Any, List[Dict[str, Any]]]:
        """Resolve every target, waiting up to ``resolve_wait`` for late ones."""
        loop = asyncio.get_running_loop()
        loop_deadline = loop.time() + self.resolve_wait / 1000
        field_hits: List[Any] = [None] * len(self.fields)
        upload_hits: List[Any] = [None] * len(self.uploads)
        while True:
            for index, item in enumerate(self.fields):
                if field_hits[index] is None:
                    selector, locator = await self._resolve_control(page, item, upload=False)
                    if locator is not None:
                        field_hits[index] = (selector, locator)
            for index, item in enumerate(self.uploads):
                if upload_hits[index] is None:
                    selector, locator = await self._resolve_control(page, item, upload=True)
                    if locator is not None:
                        upload_hits[index] = (selector, locator)
            if all(field_hits) and all(upload_hits):
                break
            remaining_ms = (loop_deadline - loop.time()) * 1000
            if remaining_ms <= 0:
                break
            with suppress(Exception):  # a page mid-navigation; try again
                await next_mutation(page, cap_ms=int(remaining_ms))

        missing: List[Dict[str, Any]] = []
        for item, hit in zip(self.fields, field_hits, strict=True):
            if hit is None:
                missing.append({'kind': 'field', 'name': _target_name(item)})
        for item, hit in zip(self.uploads, upload_hits, strict=True):
            if hit is None:
                missing.append({'kind': 'upload', 'name': _target_name(item)})

        submit_hit = None
        if self.submit is not None:
            first = next((hit[1] for hit in field_hits + upload_hits if hit), None)
            selector, locator = await self._resolve_submit(page, first)
            if locator is None:
                missing.append({'kind': 'submit', 'name': _target_name(self.submit) or 'form submit button'})
            else:
                submit_hit = (selector, locator)
        return field_hits, upload_hits, submit_hit, missing

    # --------------------------------------------------------------------- fill

    async def _fill_one(self, page, item, selector, locator) -> Dict[str, Any]:
        name = _target_name(item)
        value = _value_of(item)
        info = await locator.evaluate(_DESCRIBE_JS)
        kind = info.get('kind')
        secret = (
            'sensitive_value' in item
            or _names_a_credential(item)
            or info.get('type') == 'password'
        )
        result: Dict[str, Any] = {'name': name, 'kind': kind, 'selector': selector}
        timeout = self.field_timeout
        expected: Any = value

        if kind == 'select':
            wanted = value if isinstance(value, list) else [value]
            indices = await locator.evaluate(_SELECT_INDICES_JS, [str(w) for w in wanted])
            absent = [str(w) for w, i in zip(wanted, indices, strict=False) if i < 0]
            if absent:
                raise ValueError(f"no option matches {absent if secret is False else '***'}")
            await locator.select_option(index=indices if info.get('multiple') else indices[0],
                                        timeout=timeout)
            expected = [str(w) for w in wanted]
        elif kind == 'checkbox':
            switch = _truthy(value)
            if switch is None:
                raise ValueError('a checkbox takes true or false')
            await locator.set_checked(switch, timeout=timeout)
            expected = switch
        elif kind == 'radio':
            switch = _truthy(value)
            if switch is False:
                raise ValueError('a radio button cannot be unchecked; choose another option')
            target = locator
            if switch is None:
                found = await locator.evaluate(_RADIO_OPTION_JS, value)
                if found['index'] < 0:
                    raise ValueError(f'no radio option matches {"***" if secret else value!r}')
                if found['name']:
                    escaped = found['name'].replace('\\', '\\\\').replace('"', '\\"')
                    target = page.locator(f'input[type=radio][name="{escaped}"]').nth(found['index'])
            await target.check(timeout=timeout)
            locator = target
            expected = True
        elif kind == 'text':
            await locator.fill('' if value is None else str(value), timeout=timeout)
            expected = '' if value is None else str(value)
        else:
            raise ValueError(f'"{name}" is not a fillable control ({info.get("tag")})')

        readback = await locator.evaluate(_READBACK_JS, [expected, secret])
        result['matches'] = bool(readback.get('matches'))
        if secret:
            result['value'] = '***'
            result['secret'] = True
        else:
            result['value'] = _echo(value)
            if 'value' in readback and readback.get('value') is not None and not result['matches']:
                result['actual'] = _echo(readback['value'])
            if readback.get('text'):
                result['selected_text'] = _echo(readback['text'])
        return result

    async def _upload_one(self, item, selector, locator) -> Dict[str, Any]:
        path = Path(item['path'])
        await locator.set_input_files(str(path), timeout=self.field_timeout)
        readback = await locator.evaluate(_READBACK_JS, [path.name, False])
        return {
            'name': _target_name(item),
            'kind': 'file',
            'selector': selector,
            'filename': path.name,
            'size': path.stat().st_size,
            'files': readback.get('files') or [],
            'matches': bool(readback.get('matches')),
        }

    # ------------------------------------------------------------------ execute

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")
        page = browser.page

        field_hits, upload_hits, submit_hit, missing = await self._resolve_all(page)
        names_secret = bool(self.sensitive_params(self.params))
        base: Dict[str, Any] = {
            'fields': [], 'uploads': [], 'missing': missing, 'invalid': [],
            'submitted': False, 'confirmed': False,
        }
        if names_secret:
            base[SENSITIVE_PARAMS_KEY] = ['fields']

        if missing:
            listed = ', '.join(f"{m['kind']} \"{m['name']}\"" for m in missing)
            return {
                **base,
                'ok': False,
                'status': 'error',
                'error_code': 'FIELDS_NOT_FOUND',
                'error': (
                    f'Not found on the page: {listed}. Nothing was filled. Read the page '
                    '(browser.snapshot) and use the exact visible label text or a selector.'
                ),
                'outcome': envelope(Outcome.FAILED, claim_by=ClaimBy.INFERRED, effects=[
                    {'kind': 'fields_not_found', 'missing': missing[:20],
                     'detail': 'Resolved before any write; the page was not changed.'},
                ]),
                'url': _page_url(browser),
            }

        failures: List[Dict[str, Any]] = []
        any_password = False
        for item, (selector, locator) in zip(self.fields, field_hits, strict=True):
            try:
                entry = await self._fill_one(page, item, selector, locator)
                any_password = any_password or entry.get('secret', False)
                base['fields'].append(entry)
            except Exception as error:  # noqa: BLE001 - reported per field
                failures.append({'kind': 'field', 'name': _target_name(item),
                                 'error': _short(error)})
                base['fields'].append({'name': _target_name(item), 'selector': selector,
                                       'filled': False, 'error': _short(error)})
        for item, (selector, locator) in zip(self.uploads, upload_hits, strict=True):
            try:
                base['uploads'].append(await self._upload_one(item, selector, locator))
            except Exception as error:  # noqa: BLE001
                failures.append({'kind': 'upload', 'name': _target_name(item),
                                 'error': _short(error)})
                base['uploads'].append({'name': _target_name(item), 'selector': selector,
                                        'filled': False, 'error': _short(error)})
        if any_password and SENSITIVE_PARAMS_KEY not in base:
            base[SENSITIVE_PARAMS_KEY] = ['fields']

        if failures:
            listed = '; '.join(f"{f['name']}: {f['error']}" for f in failures)
            return {
                **base, 'ok': False, 'status': 'error', 'error_code': 'FILL_FAILED',
                'failed': failures,
                'error': f'Could not fill: {listed}. The form was not submitted.',
                'outcome': envelope(Outcome.FAILED, claim_by=ClaimBy.INFERRED, effects=[
                    {'kind': 'fields_not_filled', 'failed': failures[:20]},
                ]),
                'url': _page_url(browser),
            }

        settled: Optional[str] = None
        readback: Optional[str] = None
        if submit_hit is not None:
            submit_selector, submit_locator = submit_hit
            invalid = await _invalid_controls(submit_locator)
            if invalid:
                base['invalid'] = invalid
                listed = ', '.join(f"{i['label']} ({i['message']})" for i in invalid)
                return {
                    **base, 'ok': False, 'status': 'error', 'error_code': 'FORM_INVALID',
                    'error': f'The form reports invalid fields, not submitted: {listed}',
                    'outcome': envelope(Outcome.FAILED, claim_by=ClaimBy.INFERRED, effects=[
                        {'kind': 'form_invalid', 'invalid': invalid[:20]},
                    ]),
                    'url': _page_url(browser),
                }
            settled, readback, confirmed = await self._submit_and_wait(browser, page, submit_locator)
            base['submitted'] = True
            base['confirmed'] = confirmed
            base['submit_selector'] = submit_selector
            if self.confirm and not confirmed:
                hint = await _page_hint(browser)
                return {
                    **base, 'ok': False, 'status': 'error', 'error_code': 'CONFIRMATION_NOT_SEEN',
                    'error': (
                        'The form was submitted but the confirmation did not appear within '
                        f"{int(self.confirm.get('timeout_ms') or _DEFAULT_CONFIRM_TIMEOUT_MS)} ms. "
                        'Check readback for an error message before retrying: the record may '
                        'already exist.'
                    ),
                    'readback': hint,
                    'outcome': _fill_outcome(
                        fields=base['fields'], uploads=base['uploads'], submit_requested=True,
                        submitted=True, confirm_requested=True, confirmed=False, settled=settled,
                    ),
                    'url': _page_url(browser),
                }

        if readback is None:
            readback = await _page_hint(browser)
        browser._snapshot_since_nav = True
        return {
            **base,
            'ok': True,
            'status': 'success',
            'readback': readback,
            'url': _page_url(browser),
            'outcome': _fill_outcome(
                fields=base['fields'], uploads=base['uploads'],
                submit_requested=submit_hit is not None, submitted=base['submitted'],
                confirm_requested=bool(self.confirm), confirmed=base['confirmed'],
                settled=settled,
            ),
        }

    async def _submit_and_wait(self, browser, page, submit_locator) -> Tuple[Optional[str], Optional[str], bool]:
        """Click the submit control, then wait for the confirmation or a settled page."""
        real_page = getattr(browser, 'real_page', None) or page
        requests = RequestTracker(real_page).attach()
        watching = await install_dom_watch(page)
        try:
            await submit_locator.click(timeout=self.field_timeout)
            if self.confirm:
                timeout = int(self.confirm.get('timeout_ms') or _DEFAULT_CONFIRM_TIMEOUT_MS)
                waits = {}
                if self.confirm.get('selector'):
                    waits['selector'] = page.locator(str(self.confirm['selector'])).first.wait_for(
                        state='visible', timeout=timeout)
                if self.confirm.get('text'):
                    waits['text'] = page.get_by_text(str(self.confirm['text'])).first.wait_for(
                        state='visible', timeout=timeout)
                seen = await first_state(waits, timeout)
                watching = False
                await stop_dom_watch(page)
                readback = None
                if seen == 'selector':
                    readback = await _inner_text(page.locator(str(self.confirm['selector'])).first)
                elif seen == 'text':
                    readback = await _page_hint(browser)
                return seen, readback, seen is not None
            settled = await settle_dom(page, requests=requests, cap_ms=5000)
            watching = False
            if settled in ('new_document', 'error'):
                await settle_new_document(real_page, cap_ms=5000)
            return settled, None, False
        finally:
            requests.detach()
            if watching:
                await stop_dom_watch(page)


async def _invalid_controls(submit_locator) -> List[Dict[str, Any]]:
    try:
        return list(await submit_locator.evaluate(_INVALID_CONTROLS_JS) or [])
    except Exception:  # noqa: BLE001 - cannot read validity is not "invalid"
        return []


async def _inner_text(locator) -> Optional[str]:
    try:
        return (await locator.inner_text(timeout=2000))[:_MAX_READBACK_CHARS]
    except Exception:  # noqa: BLE001
        return None


async def _page_hint(browser) -> Optional[str]:
    try:
        hints = await browser.get_hints(force=True)
    except Exception:  # noqa: BLE001
        return None
    text = hints.get('text') if isinstance(hints, dict) else None
    return text[:_MAX_READBACK_CHARS] if text else None


def _page_url(browser) -> Optional[str]:
    try:
        return browser.page.url
    except Exception:  # noqa: BLE001
        return None


def _short(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error).splitlines()[0][:200]}" if str(error) else type(error).__name__
