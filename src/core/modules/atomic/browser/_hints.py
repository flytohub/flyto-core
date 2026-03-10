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
    // Inputs (exclude <select> — handled separately with options)
    const inputs = [];
    document.querySelectorAll('input:not([type=hidden]), textarea').forEach(el => {
        if (!el.offsetParent && el.type !== 'hidden') return;
        const id = el.id ? '#' + el.id : '';
        const name = el.name ? '[name="' + el.name + '"]' : '';
        const tag = el.tagName.toLowerCase();
        const selector = id || (tag + name) || (tag + '[type="' + (el.type || 'text') + '"]');
        inputs.push({
            selector: selector,
            type: el.type || tag,
            placeholder: (el.placeholder || '').substring(0, 50),
            value: (el.value || '').substring(0, 50),
        });
    });
    if (inputs.length) hints.inputs = inputs.slice(0, 15);
    // Selects (with their options)
    const selects = [];
    document.querySelectorAll('select').forEach(el => {
        if (!el.offsetParent) return;
        const id = el.id ? '#' + el.id : '';
        const name = el.name ? 'select[name="' + el.name + '"]' : '';
        const selector = id || name || 'select';
        const options = [];
        el.querySelectorAll('option').forEach(opt => {
            if (options.length >= 30) return;
            options.push({
                value: opt.value,
                label: (opt.textContent || '').trim().substring(0, 60),
                selected: opt.selected,
            });
        });
        selects.push({
            selector: selector,
            name: el.name || '',
            options: options,
        });
    });
    if (selects.length) hints.selects = selects.slice(0, 10);
    // Buttons
    const buttons = [];
    document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]').forEach(el => {
        if (!el.offsetParent) return;
        const id = el.id ? '#' + el.id : '';
        const cls = el.className ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
        const text = (el.textContent || el.value || '').trim().substring(0, 50);
        const selector = id || (cls ? 'button' + cls : '') || (text ? 'button:has-text("' + text + '")' : '');
        if (!selector) return;
        const entry = {selector: selector};
        if (text) entry.text = text;
        if (el.type && el.type !== 'submit') entry.type = el.type;
        buttons.push(entry);
    });
    if (buttons.length) hints.buttons = buttons.slice(0, 15);
    // Links (top 20 visible with text)
    const links = [];
    document.querySelectorAll('a[href]').forEach(el => {
        if (links.length >= 20) return;
        const text = (el.textContent || '').trim().substring(0, 60);
        if (!text) return;
        links.push({text: text, href: (el.href || '').substring(0, 120)});
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
