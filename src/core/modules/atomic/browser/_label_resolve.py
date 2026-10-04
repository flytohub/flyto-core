# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Label resolution shared by the browser modules that find a field by its label.

``browser.type`` (``type_method: label``) and ``browser.fill_form`` resolve a
label text to a control the same way, so a page that one of them can fill the
other can too. The resolution order is:

1. every control the label text names -- a ``<label>`` wrapping it or pointing
   at it with ``for`` (``label.control``), ``aria-labelledby``, ``aria-label``
   -- ranked inside the page: exact text before partial, visible before
   hidden, then label, labelledby, aria-label, then document order;
2. static fallbacks for a page that cannot be evaluated or names nothing:
   ``aria-label``, then ``label >> control``, ``label + control`` and
   ``label ~ control``.

What counts as a "control" is the caller's: ``browser.type`` accepts only
elements that take keystrokes, ``browser.fill_form`` also accepts checkboxes,
radios and file inputs depending on what it is filling.
"""
import re
from typing import List

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

#: An ``<input>`` that accepts text: the structural fallbacks must not pick a
#: checkbox ("Show password") or a button sitting next to the label.
_TYPEABLE_INPUT = (
    'input:not([type=hidden]):not([type=button]):not([type=submit])'
    ':not([type=reset]):not([type=checkbox]):not([type=radio])'
    ':not([type=image]):not([type=file])'
)

#: Ranks every typeable field a label text names, whatever the markup: a
#: ``<label>`` wrapping it or pointing at it with ``for`` (``label.control``),
#: ``aria-labelledby``, and ``aria-label``. Ranked as one list -- exact text
#: before partial, visible before hidden, then label, labelledby, aria-label,
#: then document order -- so "Password" never lands in "Confirm password", a
#: "Show password" checkbox, or a "Password hint" text box ahead of the field
#: actually labelled "Password". Text matching mirrors Playwright's
#: ``:has-text``: whitespace collapsed, case-insensitive, substring. A label's
#: own text excludes the controls inside it (a ``<select>``'s options).
#: Returns ``{attr, value}`` for the first of id, aria-labelledby, name or
#: aria-label that is unique on the page, else a structural ``path``
#: (tag names and ``:nth-of-type`` only); the selector is built in Python.
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
  const labelText = (label) => {
    const copy = label.cloneNode(true);
    copy.querySelectorAll('input, textarea, select, button').forEach((c) => c.remove());
    return copy.textContent || '';
  };
  const visible = (el) => {
    if (typeof el.checkVisibility === 'function') {
      return el.checkVisibility({visibilityProperty: true});
    }
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  };
  const best = new Map();
  const add = (field, text, kind) => {
    if (!field || !field.matches || !field.matches(typeable)) return;
    const r = rank(text);
    if (r > 1) return;
    const prev = best.get(field);
    if (!prev || r < prev.rank || (r === prev.rank && kind < prev.kind)) {
      best.set(field, {rank: r, kind});
    }
  };
  for (const label of document.querySelectorAll('label')) {
    const field = label.control
      || (label.htmlFor ? document.getElementById(label.htmlFor) : null);
    add(field, labelText(label), 0);
  }
  for (const field of document.querySelectorAll('[aria-labelledby]')) {
    const ids = (field.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
    add(field, ids.map((id) => textOf(document.getElementById(id))).join(' '), 1);
  }
  for (const field of document.querySelectorAll('[aria-label]')) {
    add(field, field.getAttribute('aria-label'), 2);
  }
  const pathOf = (el) => {
    const parts = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const tag = node.tagName.toLowerCase();
      let nth = 1;
      for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (sib.tagName === node.tagName) nth += 1;
      }
      parts.unshift(node.parentElement ? `${tag}:nth-of-type(${nth})` : tag);
    }
    return parts.join(' > ');
  };
  const entries = [...best.entries()].map(([el, info]) => ({el, ...info, shown: visible(el)}));
  entries.sort((a, b) => (a.rank - b.rank)
    || ((b.shown ? 1 : 0) - (a.shown ? 1 : 0))
    || (a.kind - b.kind)
    || ((a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1));
  const unique = (attr, value) => [...document.querySelectorAll(`[${attr}]`)]
    .filter((n) => n.getAttribute(attr) === value).length === 1;
  return entries.map(({el}) => {
    for (const attr of ['id', 'aria-labelledby', 'name', 'aria-label']) {
      const value = el.getAttribute(attr);
      if (value && unique(attr, value)) return {attr, value};
    }
    return {path: pathOf(el)};
  });
}
"""


def _css_attr_selector(attr: str, value: str) -> str:
    """``[attr="value"]`` with the value escaped for a CSS string."""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'[{attr}="{escaped}"]'


_UNIQUE_ATTRS = frozenset({'id', 'name', 'aria-labelledby', 'aria-label'})

_STRUCTURAL_PATH = re.compile(r'^[a-z][a-z0-9-]*(?::nth-of-type\(\d+\))?(?: > [a-z][a-z0-9-]*:nth-of-type\(\d+\))*$')


async def _associated_label_selectors(page, target: str, accept: str = None) -> List[str]:
    """Selectors for the fields a label text names, best match first.

    ``accept`` is the CSS a candidate control must match; it defaults to the
    elements that take keystrokes. Best effort: a page that refuses evaluation
    yields nothing here and the static selectors are still tried.
    """
    try:
        found = await page.evaluate(_ASSOCIATED_FIELDS_JS, [target, accept or _TYPEABLE])
    except Exception:  # noqa: BLE001 - see docstring
        return []
    selectors: List[str] = []
    for item in found or []:
        if not isinstance(item, dict):
            continue
        if item.get('attr') in _UNIQUE_ATTRS and item.get('value'):
            selector = _css_attr_selector(str(item['attr']), str(item['value']))
        elif isinstance(item.get('path'), str) and _STRUCTURAL_PATH.match(item['path']):
            selector = f"css={item['path']}"
        else:
            continue
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


def label_fallback_selectors(target: str, control: str = None) -> List[str]:
    """The static selectors tried after the in-page ranking, in order.

    ``control`` is the CSS of an acceptable control (an ``<input>`` that takes
    text by default). The ``aria-label`` pair is only offered for text controls,
    which is the only kind it has ever been offered for.
    """
    escaped = target.replace('"', '\\"') if target else ''
    element = control or _TYPEABLE_INPUT
    selectors: List[str] = []
    if control is None:
        selectors += [
            f'input[aria-label="{escaped}"]',
            f'textarea[aria-label="{escaped}"]',
        ]
    selectors += [
        f'label:has-text("{escaped}") >> {element}',
        f'label:has-text("{escaped}") + {element}',
        f'label:has-text("{escaped}") ~ {element}',
    ]
    return selectors
