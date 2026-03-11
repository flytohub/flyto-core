# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Shared interactive element hints extraction for browser modules.

Used by snapshot, click, type, goto etc. to capture page elements
(buttons, inputs, links, selects) for the Element Picker UI.
"""

# JS that extracts interactive elements from the current page.
# Returns: { text, inputs[], buttons[], links[], selects[] }
EXTRACT_HINTS_JS = """() => {
    const hints = {};
    const body = document.body;
    if (body) {
        hints.text = body.innerText.substring(0, 3000);
    }

    // --- stampSelector: guaranteed-unique selector via data-flyto-hint fallback ---
    // Preserve existing stamps so selectors stay stable across hint refreshes.
    // Continue numbering from the highest existing stamp to avoid collisions.
    let _hintCounter = 0;
    document.querySelectorAll('[data-flyto-hint]').forEach(el => {
        const n = parseInt(el.getAttribute('data-flyto-hint'), 10);
        if (n > _hintCounter) _hintCounter = n;
    });

    function stampSelector(el) {
        // 0. Reuse existing stamp (prevents duplicates when same element is visited twice)
        const existing = el.getAttribute('data-flyto-hint');
        if (existing) return '[data-flyto-hint="' + existing + '"]';
        // 1. Unique #id
        if (el.id) {
            try {
                if (document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
                    return '#' + CSS.escape(el.id);
                }
            } catch (e) { /* invalid id for CSS — fall through */ }
        }
        // 2. tag[name="..."]
        const nameAttr = el.getAttribute('name');
        if (nameAttr) {
            const tag = el.tagName.toLowerCase();
            const sel = tag + '[name="' + nameAttr.replace(/"/g, '\\\\"') + '"]';
            try {
                if (document.querySelectorAll(sel).length === 1) return sel;
            } catch (e) { /* fall through */ }
        }
        // 3. data-flyto-hint fallback
        _hintCounter++;
        el.setAttribute('data-flyto-hint', String(_hintCounter));
        return '[data-flyto-hint="' + _hintCounter + '"]';
    }

    // --- Inputs (exclude <select>) ---
    const inputs = [];
    document.querySelectorAll('input:not([type=hidden]), textarea').forEach(el => {
        if (!el.offsetParent && el.type !== 'hidden') return;
        const selector = stampSelector(el);
        const label = el.labels && el.labels[0] ? (el.labels[0].textContent || '').trim().substring(0, 50) : '';
        inputs.push({
            selector: selector,
            id: el.id || '',
            name: el.name || '',
            label: label,
            type: el.type || el.tagName.toLowerCase(),
            placeholder: (el.placeholder || '').substring(0, 50),
            value: (el.value || '').substring(0, 50),
        });
    });
    if (inputs.length) hints.inputs = inputs.slice(0, 15);

    // --- Selects: two-pass dropdown detection ---
    const selects = [];
    const seenTriggers = new Set();
    const MAX_OPTIONS = 20;
    const MAX_SELECTS = 15;

    function resolveName(el) {
        // aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel.trim().substring(0, 60);
        // aria-labelledby — resolve to text
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const text = labelledBy.split(/\\s+/).map(id => {
                const ref = document.getElementById(id);
                return ref ? (ref.textContent || '').trim() : '';
            }).filter(Boolean).join(' ');
            if (text) return text.substring(0, 60);
        }
        // associated <label> (for native elements)
        if (el.labels && el.labels[0]) {
            const lt = (el.labels[0].textContent || '').trim();
            if (lt) return lt.substring(0, 60);
        }
        // name attribute as last resort
        return el.getAttribute('name') || '';
    }

    function currentValue(el) {
        // Native select
        if (el.tagName === 'SELECT') {
            const opt = el.options && el.options[el.selectedIndex];
            return opt ? (opt.textContent || '').trim().substring(0, 60) : '';
        }
        // Custom: displayed text
        return (el.textContent || el.value || '').trim().substring(0, 60);
    }

    // Pass 1: collect triggers
    const triggers = [];

    function isVisible(el) {
        // Check multiple visibility signals — offsetParent alone misses
        // position:fixed, elements in certain Google Material containers, etc.
        if (el.offsetParent) return true;
        if (el.getClientRects && el.getClientRects().length > 0) return true;
        const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
        if (style && style.display !== 'none' && style.visibility !== 'hidden') return true;
        return false;
    }

    function addTrigger(el, kind) {
        const sel = stampSelector(el);
        if (seenTriggers.has(sel)) return;
        seenTriggers.add(sel);
        triggers.push({ el: el, selector: sel, kind: kind });
    }

    // 1a. Native <select>
    document.querySelectorAll('select').forEach(el => {
        if (!isVisible(el)) return;
        addTrigger(el, 'native');
    });

    // 1b. [role="combobox"] — ARIA role = always detect, skip visibility check
    document.querySelectorAll('[role="combobox"]').forEach(el => {
        addTrigger(el, 'custom');
    });

    // 1c. [aria-haspopup="listbox"|"menu"|"true"] — same: trust ARIA
    document.querySelectorAll('[aria-haspopup="listbox"], [aria-haspopup="menu"], [aria-haspopup="true"]').forEach(el => {
        addTrigger(el, 'custom');
    });

    // Pass 2: enumerate options for each trigger
    for (const trigger of triggers) {
        if (selects.length >= MAX_SELECTS) break;

        const el = trigger.el;
        const name = resolveName(el);
        const cv = currentValue(el);
        let options = [];
        let lazy = false;

        if (trigger.kind === 'native') {
            // Native <select>: enumerate <option> children
            el.querySelectorAll('option').forEach(opt => {
                if (options.length >= MAX_OPTIONS) return;
                const label = (opt.textContent || '').trim().substring(0, 60);
                options.push({
                    value: opt.value,
                    label: label,
                    option_selector: stampSelector(opt),
                    selected: opt.selected,
                });
            });
        } else {
            // Custom: find linked popup via aria-controls / aria-owns
            const listId = el.getAttribute('aria-controls') || el.getAttribute('aria-owns');
            let popup = listId ? document.getElementById(listId) : null;

            // Find options: try aria-controls popup first, then search container
            const OPT_SELECTOR = '[role="option"], [role="menuitem"]';
            let optEls = [];
            if (popup) {
                optEls = Array.from(popup.querySelectorAll(OPT_SELECTOR));
            }
            // If popup is empty (Google puts aria-controls on a hidden empty span),
            // walk up to find a reasonable container (skip too-broad roots like body/#app)
            if (!optEls.length) {
                let wrapper = el.parentElement;
                const tooWide = new Set(['BODY', 'HTML']);
                // Walk up max 6 levels to find a container with listbox/menu children
                for (let i = 0; i < 6 && wrapper && !tooWide.has(wrapper.tagName); i++) {
                    const candidates = wrapper.querySelectorAll('[role="listbox"], [role="menu"], ul[role="group"]');
                    for (const cand of candidates) {
                        if (cand === popup) continue;
                        const opts = cand.querySelectorAll(OPT_SELECTOR);
                        if (opts.length > 0) {
                            optEls = Array.from(opts);
                            break;
                        }
                    }
                    if (optEls.length) break;
                    wrapper = wrapper.parentElement;
                }
            }

            if (optEls.length) {
                optEls.slice(0, MAX_OPTIONS).forEach(opt => {
                    const val = opt.getAttribute('data-value') || opt.getAttribute('value') || (opt.textContent || '').trim();
                    const label = (opt.textContent || '').trim().substring(0, 60);
                    if (!label) return;
                    const selected = opt.getAttribute('aria-selected') === 'true'
                        || opt.classList.contains('selected')
                        || (opt.className && typeof opt.className === 'string' && !!opt.className.match(/[-_]selected/i));
                    options.push({
                        value: val,
                        label: label,
                        option_selector: stampSelector(opt),
                        selected: !!selected,
                    });
                });
            } else {
                lazy = true;
            }
        }

        const entry = {
            selector: trigger.selector,
            kind: trigger.kind,
            name: name,
            current_value: cv,
            options: options,
        };
        if (lazy) entry.lazy = true;
        selects.push(entry);
    }
    if (selects.length) hints.selects = selects;

    // --- Buttons ---
    const buttons = [];
    document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        const text = (el.textContent || el.value || '').trim().substring(0, 50);
        const entry = { selector: selector, id: el.id || '' };
        if (text) entry.text = text;
        if (el.type && el.type !== 'submit') entry.type = el.type;
        buttons.push(entry);
    });
    if (buttons.length) hints.buttons = buttons.slice(0, 15);

    // --- Links (top 20 visible with text) ---
    const links = [];
    document.querySelectorAll('a[href]').forEach(el => {
        if (links.length >= 20) return;
        const text = (el.textContent || '').trim().substring(0, 60);
        if (!text) return;
        const selector = stampSelector(el);
        links.push({ text: text, href: (el.href || '').substring(0, 120), selector: selector, id: el.id || '' });
    });
    if (links.length) hints.links = links;

    return hints;
}"""


async def extract_element_hints(page) -> dict:
    """Extract interactive elements from page. Returns dict with text/inputs/buttons/links/selects."""
    try:
        return await page.evaluate(EXTRACT_HINTS_JS)
    except Exception:
        return {}
