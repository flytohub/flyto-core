# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Detect List Module — Auto-detect repeating items on any page

Finds groups of sibling elements with the same structure (same tag + similar classes),
then extracts common fields (title, link, image, text) from each item.

Works without any selectors — fully automatic:
- Blog listing pages
- News aggregators (HN, Reddit, etc.)
- Search results (Google, Bing, etc.)
- E-commerce product grids
- Forum thread lists

The algorithm:
1. Scan all parent elements for groups of 3+ similar children
2. Score each group by: item count × structure consistency × content richness
3. Pick the best group
4. Auto-extract fields from each item: first link (title+url), first image, text
"""
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

_DETECT_LIST_JS = r"""
(options) => {
    const opts = options || {};
    const customSelector = opts.selector || '';
    const minItems = opts.min_items || 3;
    const maxItems = opts.max_items || 200;
    const includeText = opts.include_text !== false;

    // ── If user specified a selector, just use it ──
    if (customSelector) {
        const items = Array.from(document.querySelectorAll(customSelector)).slice(0, maxItems);
        return {
            items: items.map((el, i) => extractItem(el, i)),
            count: items.length,
            selector: customSelector,
            auto_detected: false,
            content_found: items.length >= minItems,
        };
    }

    // ── Auto-detect: find repeating sibling groups ──

    /** Get a structural fingerprint for an element (tag + class pattern) */
    function fingerprint(el) {
        const tag = el.tagName?.toLowerCase() || '';
        if (!tag || ['script','style','noscript','br','hr'].includes(tag)) return '';
        // Use tag + sorted meaningful classes (skip utility classes like p-2, mt-4)
        const classes = Array.from(el.classList || [])
            .filter(c => c.length > 2 && !/^[a-z]{1,2}-\d/.test(c))  // skip Tailwind utilities
            .sort().join('.');
        return tag + (classes ? '.' + classes : '');
    }

    /** Check structural similarity between two elements */
    function structureSimilarity(a, b) {
        const aChildren = Array.from(a.children).map(c => c.tagName).join(',');
        const bChildren = Array.from(b.children).map(c => c.tagName).join(',');
        if (aChildren === bChildren) return 1.0;
        // Jaccard similarity on child tag sets
        const aSet = new Set(aChildren.split(','));
        const bSet = new Set(bChildren.split(','));
        const intersection = new Set([...aSet].filter(x => bSet.has(x)));
        const union = new Set([...aSet, ...bSet]);
        return union.size > 0 ? intersection.size / union.size : 0;
    }

    /** Extract common fields from a list item */
    function extractItem(el, index) {
        const item = { _index: index };

        // Title + URL: first meaningful link
        const links = el.querySelectorAll('a[href]');
        for (const a of links) {
            const href = a.href || '';
            const text = a.textContent.trim();
            if (text.length > 3 && href && !href.startsWith('javascript:') && !href.startsWith('#')) {
                item.title = text;
                item.url = href;
                break;
            }
        }

        // Fallback title: first heading or largest text node
        if (!item.title) {
            const h = el.querySelector('h1, h2, h3, h4, h5, h6');
            if (h) item.title = h.textContent.trim();
        }
        if (!item.title) {
            item.title = el.textContent.trim().substring(0, 120);
        }

        // Image: first meaningful image
        const img = el.querySelector('img[src], img[data-src]');
        if (img) {
            item.image = img.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
            item.image_alt = img.alt || '';
        }

        // Text snippet (exclude link text to avoid duplication)
        if (includeText) {
            const clone = el.cloneNode(true);
            clone.querySelectorAll('a, script, style, img').forEach(x => x.remove());
            const text = clone.textContent.replace(/\s+/g, ' ').trim();
            if (text.length > 5) item.text = text.substring(0, 500);
        }

        // Metadata: time, author-like elements
        const timeEl = el.querySelector('time[datetime]');
        if (timeEl) item.date = timeEl.getAttribute('datetime');

        return item;
    }

    // Scan all parent elements for groups of similar children
    const candidates = [];
    const seen = new Set();

    const containers = document.querySelectorAll(
        'ul, ol, div, section, main, table, tbody, [role="list"], [role="feed"], [role="main"]'
    );

    for (const parent of containers) {
        const children = Array.from(parent.children);
        if (children.length < minItems) continue;

        // Group children by fingerprint
        const groups = {};
        for (const child of children) {
            const fp = fingerprint(child);
            if (!fp) continue;
            if (!groups[fp]) groups[fp] = [];
            groups[fp].push(child);
        }

        for (const [fp, elements] of Object.entries(groups)) {
            if (elements.length < minItems) continue;

            // Structural consistency
            let totalSim = 0;
            const sampleSize = Math.min(elements.length - 1, 5);
            for (let i = 0; i < sampleSize; i++) {
                totalSim += structureSimilarity(elements[i], elements[i + 1]);
            }
            const avgSim = sampleSize > 0 ? totalSim / sampleSize : 0;

            // ── Item quality analysis (sample first 10) ──
            const sample = elements.slice(0, 10);
            let totalTextLen = 0;
            let totalChildTypes = 0;
            let pureLinks = 0;       // items that are JUST a link
            let hasLinks = 0;
            let hasMultiContent = 0; // items with >1 type of child element

            for (const el of sample) {
                const text = el.textContent.trim();
                totalTextLen += text.length;

                // Count distinct child element types
                const childTags = new Set(Array.from(el.children).map(c => c.tagName));
                totalChildTypes += childTags.size;
                if (childTags.size >= 2) hasMultiContent++;

                // Check if item is basically just a link
                const link = el.querySelector('a[href]');
                if (link) {
                    hasLinks++;
                    const linkText = link.textContent.trim();
                    if (linkText.length > 0 && linkText.length >= text.length * 0.85) {
                        pureLinks++;  // >85% of item text is the link = nav item
                    }
                }
            }

            const avgTextLen = totalTextLen / sample.length;
            const avgChildTypes = totalChildTypes / sample.length;
            const pureLinksRatio = pureLinks / sample.length;
            const linkRatio = hasLinks / sample.length;
            const multiContentRatio = hasMultiContent / sample.length;

            // Text length variance: real lists have items of SIMILAR lengths
            const textLengths = sample.map(el => el.textContent.trim().length);
            const maxText = Math.max(...textLengths);
            const minText = Math.min(...textLengths);
            const textVariance = maxText > 0 ? minText / maxText : 0; // 0 = wildly different, 1 = identical

            // ── Scoring ──
            let score = 0;

            // Content richness: longer text per item = more likely real content
            score += Math.min(avgTextLen, 200) * 2;  // cap at 200 chars

            // Structural complexity: items with diverse children = article cards
            score += avgChildTypes * 30;
            score += multiContentRatio * 80;

            // Has links (content items usually have links)
            score += linkRatio * 30;

            // Item count bonus (more items = more likely a real list, but diminishing returns)
            score += Math.min(elements.length, 30) * 5;

            // Text consistency: real list items have similar text lengths
            // A group with one 982-char item and one 0-char item is NOT a list
            if (textVariance < 0.1) score *= 0.2;  // wildly inconsistent
            else score *= (0.5 + textVariance * 0.5);  // bonus for consistency

            // ── Penalties ──
            // Pure link items = navigation/sidebar (TAG LISTS, LANGUAGE SELECTORS)
            if (pureLinksRatio > 0.7) score *= 0.1;

            // Very short text = tags, buttons, not articles
            if (avgTextLen < 15) score *= 0.1;

            // Too many items often = dropdown/select options, not content
            if (elements.length > 100) score *= 0.5;

            // Consistency bonus (items should look alike)
            score *= (0.5 + avgSim * 0.5);

            // Parent is in sidebar/nav? Heavy penalty
            let p = parent;
            let inSidebar = false;
            for (let d = 0; d < 5 && p; d++) {
                const cls = (p.className || '').toLowerCase();
                const id = (p.id || '').toLowerCase();
                const role = p.getAttribute?.('role') || '';
                if (/sidebar|aside|nav|menu|dropdown|select-menu|footer/i.test(cls + ' ' + id) ||
                    ['navigation','complementary','menu'].includes(role) ||
                    p.tagName?.toLowerCase() === 'nav' || p.tagName?.toLowerCase() === 'aside') {
                    inSidebar = true;
                    break;
                }
                p = p.parentElement;
            }
            if (inSidebar) score *= 0.05;

            const key = fp + ':' + parent.tagName + ':' + elements.length;
            if (seen.has(key)) continue;
            seen.add(key);

            candidates.push({
                parent,
                elements,
                fingerprint: fp,
                score,
                consistency: avgSim,
                avgTextLen: Math.round(avgTextLen),
                pureLinksRatio: Math.round(pureLinksRatio * 100) / 100,
                multiContentRatio: Math.round(multiContentRatio * 100) / 100,
            });
        }
    }

    // ── Post-scoring: re-rank top candidates by extracted item quality ──
    // Structure-only scoring can't distinguish "article titles" from "432 points by user".
    // Extract items from top candidates and boost based on title length + URL quality.
    candidates.sort((a, b) => b.score - a.score);
    const topN = candidates.slice(0, 5);
    for (const cand of topN) {
        const sampleItems = cand.elements.slice(0, 5).map((el, i) => extractItem(el, i));
        const titles = sampleItems.map(it => it.title || '');
        const urls = sampleItems.map(it => it.url || '');

        const avgTitleLen = titles.reduce((s, t) => s + t.length, 0) / titles.length;
        const hasExternalUrls = urls.filter(u => u.startsWith('http') && !u.includes(window.location.hostname)).length;
        const nonEmptyTitles = titles.filter(t => t.length > 5).length;

        // Long titles = article list (titles 20-100 chars)
        if (avgTitleLen > 25) cand.score *= 1.5;
        else if (avgTitleLen < 10) cand.score *= 0.3;

        // External URLs = content links, not navigation
        if (hasExternalUrls >= 2) cand.score *= 1.3;

        // Most items should have titles
        if (nonEmptyTitles < sampleItems.length * 0.5) cand.score *= 0.5;
    }
    candidates.sort((a, b) => b.score - a.score);
    const best = candidates[0];

    if (!best || best.elements.length < minItems) {
        return {
            items: [],
            count: 0,
            selector: '',
            auto_detected: true,
            content_found: false,
            candidates_evaluated: candidates.length,
        };
    }

    // Generate a reusable CSS selector for this group
    const sampleEl = best.elements[0];
    let selector = sampleEl.tagName.toLowerCase();
    if (sampleEl.className) {
        const mainClass = Array.from(sampleEl.classList)
            .filter(c => c.length > 2 && !/^[a-z]{1,2}-\d/.test(c))[0];
        if (mainClass) selector += '.' + mainClass;
    }

    const items = best.elements.slice(0, maxItems).map((el, i) => extractItem(el, i));

    return {
        items: items,
        count: items.length,
        selector: selector,
        auto_detected: true,
        content_found: items.length >= minItems,
        consistency: Math.round(best.consistency * 100) / 100,
        candidates_evaluated: candidates.length,
    };
}
"""


@register_module(
    module_id='browser.detect_list',
    version='1.0.0',
    category='browser',
    tags=['browser', 'scraping', 'extract', 'list', 'detect', 'ssrf_protected'],
    label='Detect List',
    label_key='modules.browser.detect_list.label',
    description='Auto-detect repeating items on any page (articles, products, search results). No selectors needed.',
    description_key='modules.browser.detect_list.description',
    icon='List',
    color='#F59E0B',

    input_types=['page'],
    output_types=['array', 'json'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*'],

    params_schema=compose(
        # Basic
        field('min_items', type='number', label='Min items',
              label_key='modules.browser.detect_list.params.min_items.label',
              description='Minimum items to consider a valid list.',
              required=False, default=3, min=1, max=50, step=1,
              group='basic'),
        field('max_items', type='number', label='Max items',
              label_key='modules.browser.detect_list.params.max_items.label',
              description='Maximum items to return.',
              required=False, default=200, min=1, max=1000, step=10,
              group='basic'),
        field('include_text', type='boolean', label='Include text snippet',
              label_key='modules.browser.detect_list.params.include_text.label',
              description='Include text content from each item (excluding links).',
              required=False, default=True,
              group='basic'),
        # Advanced
        field('selector', type='string', label='Item selector',
              label_key='modules.browser.detect_list.params.selector.label',
              description='CSS selector for list items. Leave empty for auto-detection.',
              required=False, default='',
              placeholder='.post-item, .result-card',
              group='advanced'),
    ),
    output_schema={
        'items':        {'type': 'array',   'description': 'Detected items [{title, url, image, text, date, _index}]', 'format': 'list'},
        'count':        {'type': 'number',  'description': 'Number of items found'},
        'selector':     {'type': 'string',  'description': 'CSS selector that matches the items (reusable for browser.extract or browser.pagination)'},
        'auto_detected': {'type': 'boolean', 'description': 'Whether items were auto-detected or from user selector'},
        'content_found': {'type': 'boolean', 'description': 'Whether enough items were found'},
        'consistency':  {'type': 'number',  'description': 'Structural consistency score (0-1)'},
    },
    examples=[
        {
            'name': 'Auto-detect list (no config)',
            'params': {},
        },
        {
            'name': 'Detect with known selector',
            'params': {'selector': '.post-item'},
        },
        {
            'name': 'Detect with minimum threshold',
            'params': {'min_items': 5, 'max_items': 50},
        },
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.read"],
)
class BrowserDetectListModule(BaseModule):
    """Auto-detect repeating list items on any page."""

    module_name = "Detect List"
    module_description = "Auto-detect repeating items on any page"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.selector = self.params.get('selector', '')
        self.min_items = self.params.get('min_items', 3)
        self.max_items = self.params.get('max_items', 200)
        self.include_text = self.params.get('include_text', True)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        result = await page.evaluate(_DETECT_LIST_JS, {
            'selector': self.selector,
            'min_items': self.min_items,
            'max_items': self.max_items,
            'include_text': self.include_text,
        })

        return {
            "status": "success" if result.get('content_found') else "no_list",
            **result,
        }
