# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Shared interactive element hints extraction for browser modules.

Used by snapshot, click, type, goto etc. to capture page elements
(buttons, inputs, links, selects) for the Element Picker UI.

Supports: Shadow DOM (open), ARIA widgets, native HTML forms,
          contenteditable editors, portal-rendered dropdowns.
"""

# JS that extracts interactive elements from the current page.
# Returns: { text, inputs[], checkboxes[], radios[], switches[], selects[], buttons[], links[], elements[] }
# elements[] = unified list of ALL interactive elements sorted by page position (top→left)
EXTRACT_HINTS_JS = """() => {
    const hints = {};
    const body = document.body;
    if (body) {
        hints.text = (body.textContent || '').substring(0, 3000);
    }

    // === Shadow DOM: discover all roots (document + open shadow roots) ===
    // Collected once upfront; deepQSA uses this to query across all roots.
    // Fast path: skip the expensive querySelectorAll('*') scan when no shadow roots exist.
    const _shadowRoots = [];
    (function _discover(root) {
        root.querySelectorAll('*').forEach(function(el) {
            if (el.shadowRoot) {
                _shadowRoots.push(el.shadowRoot);
                _discover(el.shadowRoot);
            }
        });
    })(document);
    const _hasShadow = _shadowRoots.length > 0;

    function deepQSA(selector) {
        const results = Array.from(document.querySelectorAll(selector));
        if (!_hasShadow) return results;
        for (var i = 0; i < _shadowRoots.length; i++) {
            _shadowRoots[i].querySelectorAll(selector).forEach(function(el) {
                results.push(el);
            });
        }
        return results;
    }

    // --- stampSelector: guaranteed-unique selector via data-flyto-hint fallback ---
    // Preserve existing stamps so selectors stay stable across hint refreshes.
    // Continue numbering from the highest existing stamp to avoid collisions.
    let _hintCounter = 0;
    deepQSA('[data-flyto-hint]').forEach(function(el) {
        const n = parseInt(el.getAttribute('data-flyto-hint'), 10);
        if (n > _hintCounter) _hintCounter = n;
    });

    function stampSelector(el) {
        // 0. Reuse existing stamp (prevents duplicates when same element is visited twice)
        const existing = el.getAttribute('data-flyto-hint');
        if (existing) return '[data-flyto-hint="' + existing + '"]';

        // Shadow DOM elements: skip id/name uniqueness checks.
        // document.querySelectorAll cannot pierce shadow DOM, so uniqueness checks
        // would give wrong results. Playwright CSS selectors auto-pierce open shadow
        // roots, so a data-flyto-hint stamp inside shadow DOM works correctly.
        const inShadow = typeof ShadowRoot !== 'undefined' && el.getRootNode() instanceof ShadowRoot;

        if (!inShadow) {
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
                const sel = tag + '[name="' + CSS.escape(nameAttr) + '"]';
                try {
                    if (document.querySelectorAll(sel).length === 1) return sel;
                } catch (e) { /* fall through */ }
            }
        }

        // 3. data-flyto-hint fallback
        _hintCounter++;
        el.setAttribute('data-flyto-hint', String(_hintCounter));
        return '[data-flyto-hint="' + _hintCounter + '"]';
    }

    // =====================================================================
    // Elimination-based classification:
    //   1. Scan ALL interactive elements on the page (including shadow DOM)
    //   2. Classify obvious ones by tag/type/role
    //   3. Remainder = identified by what they ARE, not pattern-matching
    //
    // Categories: inputs, checkboxes, radios, switches, selects,
    //             buttons, links
    // =====================================================================

    const classified = new Set(); // track stamped selectors already classified

    // --- Helper: closest() that crosses shadow DOM boundaries ---
    function closestAcrossShadow(el, selector) {
        let current = el;
        while (current) {
            const found = current.closest(selector);
            if (found) return found;
            const root = current.getRootNode();
            if (root === document || !root.host) break;
            current = root.host;
        }
        return null;
    }

    // --- Helper: resolve human-readable name for any element ---
    // Priority: aria-label > aria-labelledby > <label for> > wrapping <label>
    //         > title > placeholder > adjacent text > name attr
    function resolveName(el) {
        let baseName = '';
        // 1. aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) { baseName = ariaLabel.trim().substring(0, 60); }
        // 2. aria-labelledby
        if (!baseName) {
            const labelledBy = el.getAttribute('aria-labelledby');
            if (labelledBy) {
                const text = labelledBy.split(/\\s+/).map(id => {
                    const ref = el.getRootNode().getElementById(id);
                    return ref ? (ref.textContent || '').trim() : '';
                }).filter(Boolean).join(' ');
                if (text) baseName = text.substring(0, 60);
            }
        }
        // 3. Associated <label> (via for= or wrapping)
        if (!baseName && el.labels && el.labels[0]) {
            const labelEl = el.labels[0];
            let lt = '';
            labelEl.childNodes.forEach(n => {
                if (n !== el && n.nodeType === 3) lt += n.textContent;
                else if (n !== el && n.nodeType === 1) lt += (n.textContent || '');
            });
            lt = lt.trim();
            if (lt) baseName = lt.substring(0, 60);
        }
        // 4. title attribute
        if (!baseName) {
            const title = el.getAttribute('title');
            if (title) baseName = title.trim().substring(0, 60);
        }
        // 5. placeholder (for inputs)
        if (!baseName) {
            const ph = el.getAttribute('placeholder');
            if (ph) baseName = ph.trim().substring(0, 60);
        }
        // 6. Adjacent sibling text (common: <input type="checkbox"> Some text)
        if (!baseName) {
            const next = el.nextSibling;
            if (next) {
                const nt = (next.nodeType === 3 ? next.textContent : (next.textContent || '')).trim();
                if (nt && nt.length > 1 && nt.length < 80) baseName = nt.substring(0, 60);
            }
        }
        // 7. Parent's direct text (exclude children elements' text)
        if (!baseName) {
            const parent = el.parentElement;
            if (parent && parent.childNodes.length <= 3) {
                let pt = '';
                parent.childNodes.forEach(n => {
                    if (n !== el && n.nodeType === 3) pt += n.textContent;
                    else if (n !== el && n.nodeType === 1 && n.tagName !== 'INPUT') pt += (n.textContent || '');
                });
                pt = pt.trim();
                if (pt && pt.length > 1 && pt.length < 80) baseName = pt.substring(0, 60);
            }
        }
        // 8. name attribute as last resort
        if (!baseName) baseName = el.getAttribute('name') || '';

        // Fieldset context: prepend legend text for disambiguation
        // e.g. "Shipping Address > City" instead of just "City"
        const fs = closestAcrossShadow(el, 'fieldset');
        if (fs && baseName) {
            const legend = fs.querySelector(':scope > legend');
            if (legend) {
                const legendText = (legend.textContent || '').trim().substring(0, 40);
                if (legendText && !baseName.startsWith(legendText)) {
                    return (legendText + ' > ' + baseName).substring(0, 80);
                }
            }
        }

        return baseName;
    }

    // --- Helper: get element position for layout ordering ---
    function getRect(el) {
        var r = el.getBoundingClientRect();
        return { top: Math.round(r.top), left: Math.round(r.left) };
    }

    function isVisible(el) {
        // aria-hidden="true" — hidden from assistive tech and typically from UI
        if (el.getAttribute('aria-hidden') === 'true') return false;
        // Fast path: offsetParent is non-null for most visible elements
        if (el.offsetParent) return true;
        // position:fixed/sticky elements have null offsetParent but may be visible
        if (el.getClientRects && el.getClientRects().length > 0) return true;
        // Computed style checks for hidden patterns
        const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
        if (!style) return false;
        if (style.display === 'none') return false;
        if (style.visibility === 'hidden' || style.visibility === 'collapse') return false;
        // opacity:0 — transparent, not interactable by user
        if (parseFloat(style.opacity) === 0) return false;
        // clip-path: inset(100%) — common screen-reader-only pattern
        if (style.clipPath === 'inset(100%)') return false;
        // Zero-size with overflow hidden — collapsed accordion, hidden panel
        var rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0 && style.overflow === 'hidden') return false;
        return true;
    }

    // === 1. TEXT INPUTS (input[text/email/password/number/...], textarea) ===
    const inputs = [];
    const INPUT_TYPES = new Set(['text','email','password','number','tel','url','search','date','time','datetime-local','month','week','color','range']);
    deepQSA('input, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || 'text').toLowerCase();
        // Skip types that belong to other categories
        if (type === 'hidden' || type === 'checkbox' || type === 'radio'
            || type === 'submit' || type === 'button' || type === 'reset'
            || type === 'image') return;
        // textarea or known text-like input
        if (el.tagName === 'TEXTAREA' || INPUT_TYPES.has(type)) {
            const selector = stampSelector(el);
            classified.add(selector);
            const label = resolveName(el);
            inputs.push({
                selector: selector,
                id: el.id || '',
                name: el.name || '',
                label: label,
                type: type,
                placeholder: (el.placeholder || '').substring(0, 50),
                value: (el.value || '').substring(0, 50),
                rect: getRect(el),
            });
        }
    });
    // ARIA textbox (custom text inputs)
    deepQSA('[role="textbox"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        inputs.push({
            selector: selector,
            id: el.id || '',
            name: '',
            label: resolveName(el),
            type: 'textbox',
            placeholder: el.getAttribute('aria-placeholder') || '',
            value: (el.textContent || '').substring(0, 50),
            rect: getRect(el),
        });
    });
    // contenteditable elements (rich text editors: Tiptap, ProseMirror, Slate.js)
    deepQSA('[contenteditable="true"], [contenteditable=""]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        inputs.push({
            selector: selector,
            id: el.id || '',
            name: '',
            label: resolveName(el),
            type: 'contenteditable',
            placeholder: el.getAttribute('aria-placeholder') || el.getAttribute('data-placeholder') || '',
            value: (el.textContent || '').substring(0, 50),
            rect: getRect(el),
        });
    });
    if (inputs.length) hints.inputs = inputs.slice(0, 15);

    // === 1b. FILE INPUTS (input[type=file]) ===
    const file_inputs = [];
    deepQSA('input[type="file"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        classified.add(selector);
        file_inputs.push({
            selector: selector,
            label: resolveName(el) || el.name || '',
            rect: getRect(el),
        });
    });
    if (file_inputs.length) hints.file_inputs = file_inputs.slice(0, 15);

    // === 2. CHECKBOXES (input[type=checkbox] + [role=checkbox]) ===
    const checkboxes = [];
    deepQSA('input[type="checkbox"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        classified.add(selector);
        checkboxes.push({
            selector: selector,
            id: el.id || '',
            name: el.name || '',
            label: resolveName(el),
            checked: el.checked,
            rect: getRect(el),
        });
    });
    deepQSA('[role="checkbox"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        checkboxes.push({
            selector: selector,
            id: el.id || '',
            name: '',
            label: resolveName(el) || (el.textContent || '').trim().substring(0, 50),
            checked: el.getAttribute('aria-checked') === 'true',
            rect: getRect(el),
        });
    });
    if (checkboxes.length) hints.checkboxes = checkboxes.slice(0, 15);

    // === 3. RADIOS — grouped by name (like selects, single-choice) ===
    // Collect all radio elements, then group by name/radiogroup
    const _rawRadios = [];
    deepQSA('input[type="radio"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        classified.add(selector);
        _rawRadios.push({
            selector: selector,
            group: el.name || '',
            label: resolveName(el),
            value: el.value || '',
            checked: el.checked,
        });
    });
    deepQSA('[role="radio"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        // ARIA radios: group by closest [role=radiogroup] or parent
        const rg = el.closest('[role="radiogroup"]');
        const groupName = rg ? (rg.getAttribute('aria-label') || rg.id || '') : '';
        _rawRadios.push({
            selector: selector,
            group: groupName,
            label: resolveName(el) || (el.textContent || '').trim().substring(0, 50),
            value: el.getAttribute('data-value') || (el.textContent || '').trim(),
            checked: el.getAttribute('aria-checked') === 'true',
        });
    });
    // Group by name -> radio_groups (structured like selects)
    if (_rawRadios.length) {
        const radioGroups = [];
        const groupMap = new Map();
        for (const r of _rawRadios) {
            const key = r.group || '__ungrouped_' + r.selector;
            if (!groupMap.has(key)) groupMap.set(key, []);
            groupMap.get(key).push(r);
        }
        groupMap.forEach((items, key) => {
            if (items.length === 1 && key.startsWith('__ungrouped_')) {
                // Standalone radio — keep as single-item group
                radioGroups.push({
                    name: items[0].label || key,
                    group_key: key,
                    current_value: items[0].checked ? items[0].label : '',
                    options: [{ value: items[0].value, label: items[0].label, selector: items[0].selector, selected: items[0].checked }],
                });
            } else {
                // Resolve group name: try fieldset>legend context
                let groupName = key;
                if (items[0].selector) {
                    try {
                        const firstEl = document.querySelector(items[0].selector);
                        if (firstEl) {
                            const fs = firstEl.closest('fieldset');
                            if (fs) {
                                const legend = fs.querySelector('legend');
                                if (legend) groupName = (legend.textContent || '').trim().substring(0, 60);
                            }
                        }
                    } catch(e) {}
                }
                const selected = items.find(i => i.checked);
                radioGroups.push({
                    name: groupName,
                    group_key: key,
                    current_value: selected ? selected.label : '',
                    options: items.map(i => ({ value: i.value, label: i.label, selector: i.selector, selected: i.checked })),
                });
            }
        });
        hints.radios = radioGroups.slice(0, 10);
    }

    // === 4. SWITCHES ([role=switch] — toggle on/off) ===
    const switches = [];
    deepQSA('[role="switch"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        switches.push({
            selector: selector,
            id: el.id || '',
            label: resolveName(el) || (el.textContent || '').trim().substring(0, 50),
            checked: el.getAttribute('aria-checked') === 'true',
            rect: getRect(el),
        });
    });
    if (switches.length) hints.switches = switches.slice(0, 15);

    // === 5. SELECTS / DROPDOWNS (native <select> + ARIA combobox/listbox) ===
    const selects = [];
    const seenTriggers = new Set();
    const MAX_OPTIONS = 20;
    const MAX_SELECTS = 15;

    function currentValue(el) {
        if (el.tagName === 'SELECT') {
            const opt = el.options && el.options[el.selectedIndex];
            return opt ? (opt.textContent || '').trim().substring(0, 60) : '';
        }
        return (el.textContent || el.value || '').trim().substring(0, 60);
    }

    function addTrigger(el, kind) {
        if (!isVisible(el)) return;
        const sel = stampSelector(el);
        if (seenTriggers.has(sel)) return;
        seenTriggers.add(sel);
        classified.add(sel);
        return { el: el, selector: sel, kind: kind };
    }

    const triggers = [];

    // 5a. Native <select>
    deepQSA('select').forEach(el => {
        if (!isVisible(el)) return;
        const t = addTrigger(el, 'native');
        if (t) triggers.push(t);
    });

    // 5b. [role="combobox"] — always detect
    deepQSA('[role="combobox"]').forEach(el => {
        const t = addTrigger(el, 'custom');
        if (t) triggers.push(t);
    });

    // 5c. [aria-haspopup="listbox"|"menu"|"true"]
    deepQSA('[aria-haspopup="listbox"], [aria-haspopup="menu"], [aria-haspopup="true"]').forEach(el => {
        const t = addTrigger(el, 'custom');
        if (t) triggers.push(t);
    });

    // Enumerate options for each trigger
    for (const trigger of triggers) {
        if (selects.length >= MAX_SELECTS) break;

        const el = trigger.el;
        const name = resolveName(el);
        const cv = currentValue(el);
        let options = [];
        let lazy = false;

        if (trigger.kind === 'native') {
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
            const listId = el.getAttribute('aria-controls') || el.getAttribute('aria-owns');
            let popup = listId ? document.getElementById(listId) : null;
            const OPT_SELECTOR = '[role="option"], [role="menuitem"]';
            let optEls = [];
            if (popup) {
                optEls = Array.from(popup.querySelectorAll(OPT_SELECTOR));
            }
            // Walk-up search: find listbox/menu in ancestor containers
            if (!optEls.length) {
                let wrapper = el.parentElement;
                const tooWide = new Set(['BODY', 'HTML']);
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
            // Portal fallback: global search for listbox/menu matching the trigger.
            // Handles React Portal, Vue Teleport, Angular CDK Overlay where the options
            // container is rendered outside the trigger's ancestor chain.
            // Safety: cross-check via aria-controls/aria-owns ID, then fall back to
            // aria-label matching. If multiple candidates match the same label, stay
            // lazy to avoid binding the wrong listbox.
            if (!optEls.length) {
                const allListboxes = deepQSA('[role="listbox"], [role="menu"]');
                // 1. Cross-check: trigger has aria-controls/owns pointing to a listbox
                //    that IS in the DOM but was empty at the popup reference — search globally
                if (listId) {
                    for (const cand of allListboxes) {
                        if (cand === popup) continue;
                        if (cand.id === listId) {
                            optEls = Array.from(cand.querySelectorAll(OPT_SELECTOR));
                            break;
                        }
                    }
                }
                // 2. aria-label matching — only if exactly one candidate matches
                if (!optEls.length) {
                    const triggerLabel = el.getAttribute('aria-label') || name;
                    if (triggerLabel) {
                        const matches = [];
                        for (const cand of allListboxes) {
                            if (cand === popup) continue;
                            const candLabel = cand.getAttribute('aria-label') || '';
                            if (candLabel && candLabel === triggerLabel) {
                                const opts = Array.from(cand.querySelectorAll(OPT_SELECTOR));
                                if (opts.length) matches.push(opts);
                            }
                        }
                        // Only use if exactly one match — ambiguous matches stay lazy.
                        // Known limitation: multiple comboboxes with the same aria-label
                        // (e.g. two "Country" dropdowns on a shipping/billing form) will
                        // all stay lazy because we can't reliably determine which listbox
                        // belongs to which trigger without aria-controls IDs.
                        if (matches.length === 1) {
                            optEls = matches[0];
                        }
                    }
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
            rect: getRect(el),
        };
        if (lazy) entry.lazy = true;
        selects.push(entry);
    }
    if (selects.length) hints.selects = selects;

    // === 6. BUTTONS (button, [role=button], input[submit/button]) ===
    const buttons = [];
    deepQSA('button, [role="button"], input[type="submit"], input[type="button"], input[type="reset"]').forEach(el => {
        if (!isVisible(el)) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        const text = (el.textContent || el.value || '').trim().substring(0, 50);
        const entry = { selector: selector, id: el.id || '', rect: getRect(el) };
        if (text) entry.text = text;
        if (el.type && el.type !== 'submit') entry.type = el.type;
        buttons.push(entry);
    });
    if (buttons.length) hints.buttons = buttons.slice(0, 15);

    // === 7. LINKS (a[href]) ===
    const links = [];
    deepQSA('a[href]').forEach(el => {
        if (links.length >= 20) return;
        const text = (el.textContent || '').trim().substring(0, 60);
        if (!text) return;
        const selector = stampSelector(el);
        if (classified.has(selector)) return;
        classified.add(selector);
        links.push({ text: text, href: (el.href || '').substring(0, 120), selector: selector, id: el.id || '', rect: getRect(el) });
    });
    if (links.length) hints.links = links;

    // === 8. UNIFIED ELEMENTS (all types, sorted by page position) ===
    // For browser.interact dialog: mixed layout mirroring the actual page.
    var _all = [];
    (hints.inputs || []).forEach(function(e) {
        _all.push({ _type: 'input', selector: e.selector, rect: e.rect,
            label: e.label || e.placeholder || e.name || '', input_type: e.type,
            placeholder: e.placeholder || '', value: e.value || '' });
    });
    (hints.file_inputs || []).forEach(function(e) {
        _all.push({ _type: 'file_input', selector: e.selector, rect: e.rect,
            label: e.label || '' });
    });
    (hints.checkboxes || []).forEach(function(e) {
        _all.push({ _type: 'checkbox', selector: e.selector, rect: e.rect,
            label: e.label || '', checked: e.checked });
    });
    (hints.radios || []).forEach(function(g) {
        var r = g.options && g.options[0] ? (function() {
            try { var el = document.querySelector(g.options[0].selector);
                  return el ? getRect(el) : { top: 0, left: 0 }; } catch(e) { return { top: 0, left: 0 }; }
        })() : { top: 0, left: 0 };
        _all.push({ _type: 'radio', selector: g.options && g.options[0] ? g.options[0].selector : '', rect: r,
            label: g.name || '', current_value: g.current_value || '', options: g.options || [] });
    });
    (hints.switches || []).forEach(function(e) {
        _all.push({ _type: 'switch', selector: e.selector, rect: e.rect,
            label: e.label || '', checked: e.checked });
    });
    (hints.selects || []).forEach(function(e) {
        _all.push({ _type: 'select', selector: e.selector, rect: e.rect,
            label: e.name || '', kind: e.kind, current_value: e.current_value || '',
            options: e.options || [], lazy: !!e.lazy });
    });
    (hints.buttons || []).forEach(function(e) {
        _all.push({ _type: 'button', selector: e.selector, rect: e.rect,
            label: e.text || '' });
    });
    (hints.links || []).forEach(function(e) {
        _all.push({ _type: 'link', selector: e.selector, rect: e.rect,
            label: e.text || '', href: e.href || '' });
    });
    // Sort by vertical position (top), then horizontal (left)
    _all.sort(function(a, b) {
        var dt = (a.rect ? a.rect.top : 0) - (b.rect ? b.rect.top : 0);
        if (dt !== 0) return dt;
        return (a.rect ? a.rect.left : 0) - (b.rect ? b.rect.left : 0);
    });
    if (_all.length) hints.elements = _all.slice(0, 80);

    return hints;
}"""


async def extract_element_hints(page) -> dict:
    """Extract interactive elements from page. Returns dict with text/inputs/checkboxes/radios/switches/selects/buttons/links/elements."""
    try:
        return await page.evaluate(EXTRACT_HINTS_JS)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("Failed to extract element hints: %s", e)
        return {}
