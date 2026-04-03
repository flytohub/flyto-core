# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Detect Module - Smart element detection with multi-strategy matching.

Finds elements using cascading strategies:
1. CSS/XPath selector (exact)
2. Playwright role + text
3. Exact text match
4. Label / placeholder / alt text / title
5. Contains text
6. Alternative texts
7. Fuzzy text matching (bigram similarity)
8. Proximity to anchor text

Returns the best match with confidence score.
Optionally performs an action (click / type) on the found element.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)

# ---------- JS: fuzzy + proximity fallback matcher ----------
# Only runs when all Playwright locator strategies fail.
# Returns { candidates: [{ score, strategy, selector, text, tag, ariaLabel }] }
FUZZY_DETECT_JS = """(config) => {
    function normalize(s) { return (s || '').trim().toLowerCase().replace(/\\s+/g, ' '); }

    // Bigram similarity (Dice coefficient)
    function similarity(a, b) {
        a = normalize(a); b = normalize(b);
        if (a === b) return 1;
        if (!a || !b) return 0;
        if (a.includes(b) || b.includes(a)) return 0.85;
        const bigrams = s => { const bg = new Set(); for (let i = 0; i < s.length - 1; i++) bg.add(s.substring(i, i+2)); return bg; };
        const bg1 = bigrams(a), bg2 = bigrams(b);
        let inter = 0; bg1.forEach(x => { if (bg2.has(x)) inter++; });
        const total = bg1.size + bg2.size;
        return total === 0 ? 0 : (2 * inter) / total;
    }

    // Build a unique standard CSS selector for an element
    function buildSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        const tag = el.tagName.toLowerCase();
        if (el.name && (tag === 'input' || tag === 'textarea' || tag === 'select'))
            return tag + '[name="' + el.name + '"]';
        const testId = el.getAttribute('data-testid') || el.getAttribute('data-test');
        if (testId) return '[data-testid="' + testId + '"]';
        // Positional fallback
        const parts = []; let cur = el;
        for (let d = 0; d < 4 && cur && cur !== document.body; d++) {
            let s = cur.tagName.toLowerCase();
            if (cur.id) { parts.unshift('#' + CSS.escape(cur.id)); break; }
            const p = cur.parentElement;
            if (p) {
                const sibs = Array.from(p.children).filter(c => c.tagName === cur.tagName);
                if (sibs.length > 1) s += ':nth-of-type(' + (sibs.indexOf(cur) + 1) + ')';
            }
            parts.unshift(s); cur = p;
        }
        return parts.join(' > ');
    }

    const roleSelectors = {
        button: 'button, [role="button"], input[type="submit"], input[type="button"]',
        link: 'a[href], [role="link"]',
        textbox: 'input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea, [contenteditable="true"]',
        combobox: 'select, [role="combobox"], [role="listbox"]',
        checkbox: 'input[type="checkbox"], [role="checkbox"]',
        radio: 'input[type="radio"], [role="radio"]',
        heading: 'h1, h2, h3, h4, h5, h6, [role="heading"]',
        img: 'img, [role="img"]',
    };
    const base = config.role && config.role !== 'any'
        ? (roleSelectors[config.role] || '*')
        : Object.values(roleSelectors).join(', ');

    const allTexts = [];
    if (config.text) allTexts.push(normalize(config.text));
    (config.alternatives || []).forEach(t => { const n = normalize(t); if (n) allTexts.push(n); });

    // Find anchor for proximity
    let anchorRect = null;
    if (config.near_text) {
        const nt = normalize(config.near_text);
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            if (normalize(walker.currentNode.textContent).includes(nt)) {
                const p = walker.currentNode.parentElement;
                if (p) { const r = p.getBoundingClientRect(); if (r.width > 0 && r.height > 0) { anchorRect = r; break; } }
            }
        }
    }

    // Collect elements including those inside open shadow DOMs
    function querySelectorAllDeep(root, selector) {
        const results = Array.from(root.querySelectorAll(selector));
        root.querySelectorAll('*').forEach(el => {
            if (el.shadowRoot) {
                results.push(...querySelectorAllDeep(el.shadowRoot, selector));
            }
        });
        return results;
    }

    const candidates = [];
    querySelectorAllDeep(document, base).forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        const elText = normalize(el.textContent || el.value || '');
        const attrs = [
            [elText, 'text'],
            [normalize(el.getAttribute('aria-label') || ''), 'aria_label'],
            [normalize(el.placeholder || ''), 'placeholder'],
            [normalize(el.title || ''), 'title'],
            [normalize(el.getAttribute('alt') || ''), 'alt'],
        ];

        let bestScore = 0, matchedVia = '';
        for (const st of allTexts) {
            for (const [val, via] of attrs) {
                if (!val) continue;
                let sc = 0;
                if (val === st) sc = 95;
                else if (val.includes(st) && st.length > 2) sc = 70 + (st.length / Math.max(val.length, 1)) * 20;
                else {
                    const sim = similarity(val, st);
                    if (sim > 0.5) sc = 30 + sim * 40;
                }
                if (sc > bestScore) { bestScore = sc; matchedVia = via; }
            }
        }

        // Proximity bonus
        if (anchorRect && bestScore > 30) {
            const cx = rect.x + rect.width / 2, cy = rect.y + rect.height / 2;
            const ax = anchorRect.x + anchorRect.width / 2, ay = anchorRect.y + anchorRect.height / 2;
            const dist = Math.sqrt((cx - ax) ** 2 + (cy - ay) ** 2);
            if (dist < 150) bestScore += 15;
            else if (dist < 300) bestScore += 8;
            else if (dist < 500) bestScore += 3;
        }

        if (bestScore > 40) {
            candidates.push({
                score: Math.min(Math.round(bestScore), 100),
                strategy: matchedVia,
                selector: buildSelector(el),
                text: (el.textContent || el.value || '').trim().substring(0, 80),
                tag: el.tagName.toLowerCase(),
                ariaLabel: el.getAttribute('aria-label') || '',
            });
        }
    });

    candidates.sort((a, b) => b.score - a.score);
    return { candidates: candidates.slice(0, 10) };
}"""


@register_module(
    module_id='browser.detect',
    version='1.0.0',
    category='browser',
    tags=['browser', 'detection', 'smart', 'resilient', 'self-healing', 'ssrf_protected'],
    label='Smart Detect',
    label_key='modules.browser.detect.label',
    description='Smart element detection with multi-strategy matching. Finds elements using text, selector, role, proximity, and fuzzy matching with automatic fallbacks.',
    description_key='modules.browser.detect.description',
    icon='ScanSearch',
    color='#F59E0B',

    input_types=['page'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field("text", type="string",
              label="Element Text",
              label_key="modules.browser.detect.param.text.label",
              description="Text content of the element to find (e.g. 'Login', 'Submit')",
              placeholder="Login",
              required=False,
              ui={"widget": "element_picker", "element_types": ["button", "link", "input"]},
              group=FieldGroup.BASIC),
        field("selector", type="string",
              label="CSS Selector (optional)",
              label_key="modules.browser.detect.param.selector.label",
              description="CSS/XPath selector to try first. Falls back to text matching if not found.",
              placeholder="#login-btn, .submit-button",
              required=False,
              ui={"widget": "element_picker", "element_types": ["button", "link", "input"], "value_key": "selector"},
              group=FieldGroup.BASIC),
        field("alternatives", type="string",
              label="Alternative Texts",
              label_key="modules.browser.detect.param.alternatives.label",
              description="Comma-separated alternative texts to try (e.g. 'Sign In, 登入, Log In')",
              placeholder="Sign In, 登入, Log In",
              required=False,
              group=FieldGroup.BASIC),
        field("role", type="select",
              label="Element Role",
              label_key="modules.browser.detect.param.role.label",
              description="Expected ARIA role (narrows search)",
              default="any",
              options=[
                  {"value": "any", "label": "Any"},
                  {"value": "button", "label": "Button"},
                  {"value": "link", "label": "Link"},
                  {"value": "textbox", "label": "Text Input"},
                  {"value": "combobox", "label": "Dropdown / Select"},
                  {"value": "checkbox", "label": "Checkbox"},
                  {"value": "radio", "label": "Radio Button"},
                  {"value": "heading", "label": "Heading"},
                  {"value": "img", "label": "Image"},
              ],
              group=FieldGroup.OPTIONS),
        field("near_text", type="string",
              label="Near Text",
              label_key="modules.browser.detect.param.near_text.label",
              description="Find element near this text (e.g. 'Password' to find nearby Submit button)",
              placeholder="Password",
              required=False,
              group=FieldGroup.OPTIONS),
        field("match_mode", type="select",
              label="Match Mode",
              label_key="modules.browser.detect.param.match_mode.label",
              description="How strictly to match text",
              default="best",
              options=[
                  {"value": "exact", "label": "Exact match only"},
                  {"value": "contains", "label": "Contains text"},
                  {"value": "fuzzy", "label": "Fuzzy matching"},
                  {"value": "best", "label": "Best match (try all)"},
              ],
              group=FieldGroup.OPTIONS),
        field("action", type="select",
              label="Action",
              label_key="modules.browser.detect.param.action.label",
              description="Action to perform on the found element",
              default="none",
              options=[
                  {"value": "none", "label": "Find only (no action)"},
                  {"value": "click", "label": "Click"},
                  {"value": "type", "label": "Type text"},
              ],
              group=FieldGroup.OPTIONS),
        field("action_value", type="string",
              label="Text to Type",
              label_key="modules.browser.detect.param.action_value.label",
              description="Text to type into the element (when action is 'type')",
              placeholder="user@example.com",
              required=False,
              showIf={"action": {"$in": ["type"]}},
              group=FieldGroup.OPTIONS),
        presets.TIMEOUT_MS(default=10000),
    ),
    output_schema={
        'status': {'type': 'string',
                   'description': 'Operation status (success / not_found / ambiguous)'},
        'found': {'type': 'boolean',
                  'description': 'Whether an element was found'},
        'selector': {'type': 'string',
                     'description': 'Resolved CSS/Playwright selector of the matched element'},
        'strategy': {'type': 'string',
                     'description': 'Which detection strategy matched (selector / role / text / label / placeholder / fuzzy / proximity)'},
        'confidence': {'type': 'number',
                       'description': 'Match confidence 0-100'},
        'element': {'type': 'object',
                    'description': 'Element info: tag, text, id, ariaLabel, href, etc.'},
        'candidates': {'type': 'array',
                       'description': 'Top alternative matches (for debugging)'},
        'action_result': {'type': 'string',
                          'description': 'Result of performed action (if any)'},
    },
    examples=[
        {
            'name': 'Find login button (resilient)',
            'params': {'text': 'Login', 'alternatives': 'Sign In, 登入', 'role': 'button'}
        },
        {
            'name': 'Find and click submit near password',
            'params': {'text': 'Submit', 'near_text': 'Password', 'action': 'click'}
        },
        {
            'name': 'Find input by placeholder',
            'params': {'text': 'Enter your email', 'role': 'textbox', 'action': 'type', 'action_value': 'user@example.com'}
        },
        {
            'name': 'Selector with text fallback',
            'params': {'selector': '#old-login-btn', 'text': 'Login', 'match_mode': 'best'}
        },
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserDetectModule(BaseModule):
    """Smart Detect Module — multi-strategy element detection with fallbacks."""

    module_name = "Smart Detect"
    module_description = "Find elements with intelligent fallback strategies"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.text = (self.params.get('text') or '').strip()
        self.selector = (self.params.get('selector') or '').strip()
        self.alternatives = [
            t.strip() for t in (self.params.get('alternatives') or '').split(',')
            if t.strip()
        ]
        self.role = self.params.get('role', 'any')
        self.near_text = (self.params.get('near_text') or '').strip()
        self.match_mode = self.params.get('match_mode', 'best')
        self.action = self.params.get('action', 'none')
        self.action_value = (self.params.get('action_value') or '').strip()
        self.timeout = self.params.get('timeout', 10000)

        if not self.text and not self.selector and not self.alternatives:
            raise ValueError("Must provide at least one of: text, selector, or alternatives")
        if self.action == 'type' and not self.action_value:
            raise ValueError("action_value (text to type) is required when action is 'type'")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        if not page:
            raise RuntimeError("No active page. Please navigate to a URL first")

        all_texts = ([self.text] if self.text else []) + self.alternatives
        strategies = self._build_strategies(all_texts)

        # Retry loop: honour self.timeout for dynamically loaded elements.
        # First attempt runs immediately; if nothing found, poll every 500ms
        # until timeout expires.
        deadline = time.monotonic() + (self.timeout / 1000)
        match = None
        js_candidates = []

        while True:
            # Try main page first
            match, js_candidates = await self._run_detection(
                page, strategies, all_texts
            )
            # iframe fallback — search child frames if main page missed
            # or only got a low-confidence fuzzy match (< 80)
            if not match or match['confidence'] < 80:
                frame_match, iframe_candidates = await self._search_frames(
                    page, strategies, all_texts
                )
                if frame_match:
                    if not match or frame_match['confidence'] > match['confidence']:
                        match = frame_match
                if not js_candidates:
                    js_candidates = iframe_candidates
            if match or time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.5)

        # ── Build result ──
        if match:
            result = {
                "status": "success",
                "found": True,
                "selector": match['info'].get('selector', ''),
                "strategy": match['strategy'],
                "confidence": match['confidence'],
                "element": match['info'],
            }

            # Perform action if requested
            if self.action == 'click':
                await match['locator'].click()
                result['action_result'] = 'clicked'
                # Brief wait for potential navigation
                try:
                    await page.wait_for_load_state('domcontentloaded', timeout=3000)
                except Exception:
                    pass
            elif self.action == 'type':
                await match['locator'].fill(self.action_value)
                result['action_result'] = 'typed'

            # Add extra candidates for debugging
            if js_candidates:
                result['candidates'] = js_candidates[:5]
        else:
            result = {
                "status": "not_found",
                "found": False,
                "strategies_tried": len(strategies) + (1 if self.match_mode in ('fuzzy', 'best') else 0),
                "candidates": js_candidates[:5],
            }

        # Post-action hints for Element Picker
        hints = await browser.get_hints(force=True)
        browser._snapshot_since_nav = True
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]

        return result

    async def _run_detection(self, page, strategies, all_texts):
        """Single detection pass. Returns (match_dict_or_None, js_candidates)."""
        match = None

        # ── Phase 1: Playwright locator strategies (fast, robust) ──
        for name, locator_fn, base_confidence in strategies:
            try:
                locator = locator_fn(page)
                count = await locator.count()
                if count == 0:
                    continue
                for i in range(min(count, 10)):
                    el = locator.nth(i)
                    try:
                        visible = await el.is_visible()
                    except Exception:
                        continue
                    if not visible:
                        continue
                    info = await self._get_element_info(el)
                    # Guard: skip if element info extraction failed
                    if not info or not info.get('tag'):
                        continue
                    # Role filter (skip for role-scoped strategies)
                    if self.role != 'any' and name != 'role':
                        if not self._role_matches(info, self.role):
                            continue
                    match = {
                        'strategy': name,
                        'confidence': base_confidence,
                        'locator': el,
                        'info': info,
                    }
                    break
                if match:
                    break
            except Exception as exc:
                logger.debug("detect: strategy %s failed: %s", name, exc)
                continue

        # ── Phase 2: JS fuzzy + proximity fallback ──
        js_candidates = []
        if not match and self.match_mode in ('fuzzy', 'best'):
            try:
                js_result = await page.evaluate(FUZZY_DETECT_JS, {
                    'text': self.text,
                    'alternatives': self.alternatives,
                    'role': self.role,
                    'near_text': self.near_text,
                })
                js_candidates = js_result.get('candidates', [])
                if js_candidates:
                    top = js_candidates[0]
                    loc = page.locator(top['selector']).first
                    try:
                        visible = await loc.is_visible()
                    except Exception:
                        visible = False
                    if visible:
                        info = await self._get_element_info(loc)
                        if info and info.get('tag'):
                            match = {
                                'strategy': top['strategy'] or 'fuzzy',
                                'confidence': top['score'],
                                'locator': loc,
                                'info': info,
                            }
            except Exception as exc:
                logger.debug("detect: JS fuzzy fallback failed: %s", exc)

        return match, js_candidates

    async def _search_frames(self, page, strategies, all_texts):
        """Search child iframes for the element. Returns (match, candidates)."""
        try:
            frames = page.frames
        except Exception:
            return None, []
        for frame in frames:
            if frame == page.main_frame:
                continue
            try:
                # Playwright FrameLocator doesn't support get_by_role etc.
                # but Frame objects DO — they have the same locator API as Page.
                match, candidates = await self._run_detection(
                    frame, strategies, all_texts
                )
                if match:
                    # Tag the match so caller knows it came from an iframe
                    match['info']['_frame_url'] = frame.url
                    match['info']['_frame_name'] = frame.name
                    match['strategy'] = f"iframe:{match['strategy']}"
                    # Reduce confidence slightly — iframe match is less certain
                    match['confidence'] = max(match['confidence'] - 5, 1)
                    return match, candidates
            except Exception as exc:
                logger.debug("detect: frame search failed (%s): %s", frame.url, exc)
                continue
        return None, []

    def _build_strategies(self, all_texts: List[str]) -> List[Tuple[str, Any, int]]:
        """Build ordered list of (name, locator_factory, confidence) tuples."""
        strategies = []

        # 1. Exact CSS/XPath selector
        if self.selector:
            strategies.append((
                'selector', lambda p, s=self.selector: p.locator(s), 100
            ))

        # 2. Role + text (Playwright's most semantic locator)
        if self.role != 'any' and self.text:
            strategies.append((
                'role',
                lambda p, r=self.role, t=self.text: p.get_by_role(r, name=t),
                95
            ))

        # 3. Exact text
        if self.text:
            if self.match_mode in ('exact', 'best'):
                strategies.append((
                    'text_exact',
                    lambda p, t=self.text: p.get_by_text(t, exact=True),
                    90
                ))

        # 4. Label
        if self.text:
            strategies.append((
                'label',
                lambda p, t=self.text: p.get_by_label(t),
                88
            ))

        # 5. Placeholder
        if self.text:
            strategies.append((
                'placeholder',
                lambda p, t=self.text: p.get_by_placeholder(t),
                87
            ))

        # 6. Alt text
        if self.text:
            strategies.append((
                'alt_text',
                lambda p, t=self.text: p.get_by_alt_text(t),
                85
            ))

        # 7. Title
        if self.text:
            strategies.append((
                'title',
                lambda p, t=self.text: p.get_by_title(t),
                83
            ))

        # 8. Contains text
        if self.text and self.match_mode in ('contains', 'best'):
            strategies.append((
                'text_contains',
                lambda p, t=self.text: p.get_by_text(t, exact=False),
                78
            ))

        # 9. Alternative texts (exact → contains)
        for alt in self.alternatives:
            if self.match_mode in ('exact', 'best'):
                strategies.append((
                    'alt_exact',
                    lambda p, t=alt: p.get_by_text(t, exact=True),
                    75
                ))
            if self.match_mode in ('contains', 'best'):
                strategies.append((
                    'alt_contains',
                    lambda p, t=alt: p.get_by_text(t, exact=False),
                    65
                ))

        # 10. Role + alternative texts
        if self.role != 'any':
            for alt in self.alternatives:
                strategies.append((
                    'role_alt',
                    lambda p, r=self.role, t=alt: p.get_by_role(r, name=t),
                    70
                ))

        return strategies

    @staticmethod
    async def _get_element_info(locator) -> dict:
        """Extract element metadata from a Playwright locator."""
        try:
            return await locator.evaluate("""el => {
                const rect = el.getBoundingClientRect();
                return {
                    tag: el.tagName.toLowerCase(),
                    text: (el.textContent || '').trim().substring(0, 100),
                    id: el.id || null,
                    name: el.name || null,
                    type: el.type || null,
                    href: el.href || null,
                    ariaLabel: el.getAttribute('aria-label') || null,
                    placeholder: el.placeholder || null,
                    role: el.getAttribute('role') || null,
                    classes: el.className || null,
                    selector: el.id ? '#' + el.id
                        : (el.name ? el.tagName.toLowerCase() + '[name="' + el.name + '"]' : ''),
                    visible: rect.width > 0 && rect.height > 0,
                };
            }""")
        except Exception:
            return {}

    @staticmethod
    def _role_matches(info: dict, expected_role: str) -> bool:
        """Check if element info matches expected role."""
        tag = info.get('tag', '')
        el_role = info.get('role')
        el_type = info.get('type', '')

        # Explicit ARIA role match
        if el_role == expected_role:
            return True

        # Implicit role by tag
        implicit = {
            'button': ('button', {'submit', 'button'}),
            'link': ('a', set()),
            'textbox': (None, {'text', 'email', 'password', 'search', 'tel', 'url', 'number'}),
            'combobox': ('select', set()),
            'checkbox': (None, {'checkbox'}),
            'radio': (None, {'radio'}),
            'heading': (None, set()),
            'img': ('img', set()),
        }
        mapping = implicit.get(expected_role)
        if not mapping:
            return False

        tag_match, type_matches = mapping
        if expected_role == 'heading':
            return tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
        if expected_role == 'textbox':
            return tag in ('input', 'textarea') and (el_type in type_matches or tag == 'textarea')
        if tag_match and tag == tag_match:
            return True
        if type_matches and el_type in type_matches:
            return True
        return False
