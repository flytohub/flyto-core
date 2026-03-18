# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Readability Module — Smart Article Extraction

Extracts the main article content from any webpage:
- News sites, blogs, documentation, forums
- Zero cost (no LLM), runs entirely in-browser via JS
- Multi-strategy: metadata → semantic selectors → text density analysis
- Customizable: override selectors, add clean rules, adjust thresholds

Works like Firefox Reader Mode but as a workflow module.
"""
from typing import Any, Dict, List, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field


# ---------------------------------------------------------------------------
# Extraction JS — injected into the page via Playwright evaluate()
# ---------------------------------------------------------------------------
# This is a self-contained function. No external dependencies.
# Strategies (in order):
#   1. <meta> / OpenGraph / JSON-LD metadata
#   2. Semantic selectors (article, [role=main], known CMS classes)
#   3. Text density scoring (largest clean text block)
# ---------------------------------------------------------------------------

_EXTRACT_JS = r"""
(options) => {
    const opts = options || {};
    const customSelector = opts.selector || '';
    const customTitleSelector = opts.title_selector || '';
    const extraCleanSelectors = opts.clean_selectors || [];
    const minLen = opts.min_content_length || 80;
    const includeImages = opts.include_images !== false;
    const includeLinks = opts.include_links === true;

    // ── Helpers ──────────────────────────────────────────────────
    function getMeta(names) {
        for (const n of names) {
            const el = document.querySelector(
                `meta[property="${n}"], meta[name="${n}"]`
            );
            if (el && el.content) return el.content.trim();
        }
        return '';
    }

    /** Word-boundary class check — avoids [class*="nav"] matching "unavailable" */
    function hasClassWord(el, word) {
        const cls = ' ' + (el.className || '') + ' ';
        const id = ' ' + (el.id || '') + ' ';
        const re = new RegExp('[\\s_-]' + word + '[\\s_-]|^' + word + '[\\s_-]|[\\s_-]' + word + '$|^' + word + '$');
        return re.test(cls) || re.test(id);
    }

    /** Check if element is noise by role/tag/class heuristic */
    function isNoise(el) {
        const tag = el.tagName?.toLowerCase() || '';
        if (['script','style','noscript','svg','iframe','nav','footer','header'].includes(tag)) return true;
        const role = el.getAttribute('role') || '';
        if (['navigation','banner','contentinfo','complementary'].includes(role)) return true;
        const words = ['nav','menu','sidebar','footer','header','comment','comments',
                       'advert','ads','social','share','related','recommend',
                       'newsletter','subscribe','popup','modal','cookie','consent',
                       'gdpr','privacy','breadcrumb','pagination','toolbar','widget',
                       'banner','promo','author-bio','byline-block','tag-list'];
        for (const w of words) { if (hasClassWord(el, w)) return true; }
        return false;
    }

    // ── 1. Metadata ──────────────────────────────────────────────
    let jsonLd = {};
    try {
        for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
            const raw = JSON.parse(s.textContent);
            const items = Array.isArray(raw) ? raw
                        : raw['@graph'] ? raw['@graph']
                        : [raw];
            for (const item of items) {
                if (item['@type'] && /Article|NewsArticle|BlogPosting|Report|WebPage/i.test(item['@type'])) {
                    jsonLd = item; break;
                }
            }
            if (jsonLd['@type']) break;
        }
    } catch (_) {}

    // Author: JSON-LD > meta > byline element
    let author = '';
    if (jsonLd.author) {
        author = typeof jsonLd.author === 'string' ? jsonLd.author
               : Array.isArray(jsonLd.author) ? jsonLd.author.map(a => a.name || a).join(', ')
               : jsonLd.author.name || '';
    }
    if (!author) author = getMeta(['author', 'article:author', 'twitter:creator', 'citation_author']);
    if (!author) {
        const byline = document.querySelector('[class*="byline"], [class*="author-name"], [rel="author"], .author');
        if (byline) author = byline.textContent.replace(/^by\s+/i, '').trim();
    }

    // Date: JSON-LD > meta > <time> > text pattern
    let date = jsonLd.datePublished || jsonLd.dateModified || '';
    if (!date) date = getMeta(['article:published_time', 'date', 'publishdate', 'DC.date.issued', 'citation_publication_date']);
    if (!date) {
        const timeEl = document.querySelector('time[datetime]');
        if (timeEl) date = timeEl.getAttribute('datetime');
    }

    const meta = {
        title: customTitleSelector
            ? (document.querySelector(customTitleSelector)?.textContent?.trim() || '')
            : (jsonLd.name || jsonLd.headline || getMeta(['og:title', 'twitter:title'])
               || document.querySelector('h1')?.textContent?.trim()
               || document.title || ''),
        author: author,
        date: date,
        description: jsonLd.description || getMeta(['og:description', 'twitter:description', 'description']) || '',
        site_name: getMeta(['og:site_name', 'application-name']) || '',
        image: jsonLd.image?.url || jsonLd.image || getMeta(['og:image', 'twitter:image']) || '',
        language: document.documentElement.lang || getMeta(['og:locale']) || '',
    };

    // ── 2. Find content element (unified scoring — no hardcoded waterfall) ──

    // Total page text length (for "too broad" detection)
    const totalPageText = document.body?.textContent?.trim().length || 1;

    /** Score any element as a content candidate.
     *  Pure heuristic — works on sites we've never seen before.
     *  Known patterns (semantic tags, schema.org) are bonuses, not gates. */
    function scoreElement(el) {
        const text = el.textContent || '';
        const textLen = text.trim().length;
        if (textLen < minLen) return -1;

        // ── Too broad? Skip elements that are basically the whole page ──
        const pageCoverage = textLen / totalPageText;
        if (pageCoverage > 0.9) return -1;

        let score = 0;

        // ── Paragraph blocks (<p>, or div-leaf for SPA sites) ──
        const pTags = el.querySelectorAll('p');
        let blockCount = pTags.length;
        let blockTextLen = 0;
        pTags.forEach(p => { blockTextLen += p.textContent.trim().length; });

        // SPA fallback: divs with direct text content (React/Vue render to divs)
        if (blockCount === 0) {
            el.querySelectorAll('div').forEach(d => {
                const childDivText = Array.from(d.querySelectorAll('div'))
                    .reduce((s, cd) => s + cd.textContent.trim().length, 0);
                const ownText = d.textContent.trim().length - childDivText;
                if (ownText > 40) { blockTextLen += ownText; blockCount++; }
            });
        }

        // Base: paragraph/block text (not raw textLen — avoids rewarding noise children)
        score += blockTextLen * 1.0;
        score += blockCount * 30;

        // Small base for total text (tiebreaker, not dominant)
        score += textLen * 0.02;

        // ── Link density penalty (navigation = high link density) ──
        const links = el.querySelectorAll('a');
        const linkTextLen = Array.from(links).reduce((s, a) => s + a.textContent.trim().length, 0);
        const linkDensity = textLen > 0 ? linkTextLen / textLen : 0;
        if (linkDensity > 0.65) return -1;
        score *= (1 - linkDensity);

        // ── Semantic tag bonus (universal, not CMS-specific) ──
        const tag = el.tagName?.toLowerCase() || '';
        if (tag === 'article') score += 300;
        if (tag === 'main') score += 200;
        if (tag === 'section') score += 50;

        const role = el.getAttribute('role') || '';
        if (role === 'main') score += 200;
        if (role === 'article') score += 300;

        // Schema.org markup bonus
        if (el.getAttribute('itemprop') === 'articleBody') score += 500;
        if (el.closest('[itemtype*="Article"]')) score += 100;

        // ── Class/ID hint bonus (soft signal) ──
        // Only match content-specific words, NOT generic ones like "text" (Tailwind: text-gray-500)
        const cls = (el.className || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        const combined = cls + ' ' + id;
        if (/\b(content|body|entry|article|post|prose|story)\b/.test(combined)) score += 150;

        // ── Noise: multiplicative penalty (scales with text, not fixed) ──
        if (isNoise(el)) score *= 0.05;

        // ── Specificity bonus: prefer deeper (more precise) elements ──
        // Depth 1-2 = wrapper (penalty), 3-8 = sweet spot (bonus), 9+ = neutral
        let depth = 0;
        let parent = el;
        while (parent = parent.parentElement) depth++;
        if (depth <= 2) score *= 0.5;           // Too broad (body > wrapper)
        else if (depth <= 8) score += depth * 15; // Sweet spot — more specific = better
        // depth > 8: no modifier (deep but OK)

        return score;
    }

    let contentEl = null;

    // User override — only hard gate
    if (customSelector) {
        try {
            contentEl = document.querySelector(customSelector);
        } catch (_) {}
    }

    // Universal scoring: score ALL candidate containers, pick the best
    if (!contentEl) {
        let bestScore = 0;
        for (const el of document.querySelectorAll('div, section, article, main, [role="main"], [role="article"]')) {
            const score = scoreElement(el);
            if (score > bestScore) { bestScore = score; contentEl = el; }
        }
    }

    // ── 3. Clean and extract ─────────────────────────────────────

    let content = '';
    let contentHtml = '';
    let images = [];
    let links = [];
    let videos = [];

    if (contentEl) {
        const clone = contentEl.cloneNode(true);

        // Remove noise using word-boundary checks (not substring match)
        clone.querySelectorAll('*').forEach(el => {
            if (isNoise(el)) el.remove();
        });
        // Also remove user-specified selectors
        for (const sel of extraCleanSelectors) {
            try { clone.querySelectorAll(sel).forEach(el => el.remove()); } catch (_) {}
        }

        // Extract images (handle lazy-load: data-src, data-lazy-src, srcset)
        if (includeImages) {
            clone.querySelectorAll('img, picture source').forEach(img => {
                const src = img.src
                    || img.getAttribute('data-src')
                    || img.getAttribute('data-lazy-src')
                    || img.getAttribute('data-original')
                    || '';
                const srcset = img.getAttribute('srcset') || '';
                const bestSrc = src || (srcset ? srcset.split(',')[0].trim().split(/\s+/)[0] : '');
                if (bestSrc && !bestSrc.startsWith('data:')) {
                    images.push({
                        src: bestSrc,
                        alt: img.alt || '',
                        width: img.naturalWidth || img.width || 0,
                        height: img.naturalHeight || img.height || 0,
                    });
                }
            });
        }

        // Extract videos
        clone.querySelectorAll('video[src], video source[src], iframe[src]').forEach(v => {
            const src = v.src || v.getAttribute('src') || '';
            if (src && /youtube|vimeo|dailymotion|wistia|\.mp4|\.webm/i.test(src)) {
                videos.push({ src, type: v.tagName.toLowerCase() === 'iframe' ? 'embed' : 'video' });
            }
        });

        // Extract links
        if (includeLinks) {
            clone.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                const text = a.textContent.trim();
                if (href && text && !href.startsWith('javascript:')) {
                    links.push({ href, text });
                }
            });
        }

        // ── Text extraction with code block preservation ──
        // Pre/code blocks: preserve whitespace formatting
        const preBlocks = new Set();
        clone.querySelectorAll('pre, code').forEach(el => {
            const marker = '\n```\n' + el.textContent + '\n```\n';
            el.textContent = marker;
            preBlocks.add(el);
        });

        // Build content from semantic blocks
        const BLOCK_TAGS = 'p, h1, h2, h3, h4, h5, h6, li, blockquote, pre, td, th, figcaption, dt, dd';
        const blocks = clone.querySelectorAll(BLOCK_TAGS);
        if (blocks.length > 0) {
            content = Array.from(blocks)
                .map(b => b.textContent.trim())
                .filter(t => t.length > 0)
                .join('\n\n');
        }

        // Fallback: walk text nodes directly (handles div-only sites)
        if (!content || content.length < minLen) {
            const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT, null);
            const chunks = [];
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (t.length > 0) chunks.push(t);
            }
            const fallback = chunks.join('\n');
            if (fallback.length > content.length) content = fallback;
        }

        contentHtml = clone.innerHTML;
    }

    // ── 4. Fallback title ────────────────────────────────────────
    if (!meta.title && contentEl) {
        const h1 = contentEl.querySelector('h1');
        if (h1) meta.title = h1.textContent.trim();
    }

    // ── 5. Excerpt ───────────────────────────────────────────────
    const excerpt = meta.description || content.substring(0, 300).replace(/\n/g, ' ').trim();

    return {
        title: meta.title,
        author: meta.author,
        date: meta.date,
        content: content,
        html: contentHtml,
        excerpt: excerpt.length > 300 ? excerpt.substring(0, 297) + '...' : excerpt,
        site_name: meta.site_name,
        image: meta.image,
        images: images,
        videos: videos,
        links: links,
        word_count: content ? content.split(/\s+/).filter(w => w.length > 0).length : 0,
        language: meta.language,
        url: window.location.href,
        content_found: content.length >= minLen,
    };
}
"""


@register_module(
    module_id='browser.readability',
    version='1.0.0',
    category='browser',
    tags=['browser', 'scraping', 'extract', 'article', 'readability', 'ssrf_protected'],
    label='Extract Article',
    label_key='modules.browser.readability.label',
    description='Smart article extraction — extracts title, author, date, and main content from any webpage. Works like Firefox Reader Mode.',
    description_key='modules.browser.readability.description',
    icon='FileText',
    color='#8B5CF6',

    input_types=['page'],
    output_types=['json'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*'],

    params_schema=compose(
        # ── Basic group (most users only touch these) ──
        field(
            'include_images',
            type='boolean',
            label='Include images',
            label_key='modules.browser.readability.params.include_images.label',
            description='Extract images from the article content.',
            required=False,
            default=True,
            group='basic',
        ),
        field(
            'include_links',
            type='boolean',
            label='Include links',
            label_key='modules.browser.readability.params.include_links.label',
            description='Extract links from the article content.',
            required=False,
            default=False,
            group='basic',
        ),
        field(
            'wait_ms',
            type='number',
            label='Wait before extract (ms)',
            label_key='modules.browser.readability.params.wait_ms.label',
            description='Wait for dynamic content to load before extracting. 0 = no wait.',
            required=False,
            default=0,
            min=0,
            max=30000,
            step=500,
            group='basic',
        ),
        # ── Advanced group (for known sites / custom selectors) ──
        field(
            'selector',
            type='string',
            label='Content selector',
            label_key='modules.browser.readability.params.selector.label',
            description='CSS selector for the content area. Leave empty for auto-detection.',
            description_key='modules.browser.readability.params.selector.description',
            required=False,
            default='',
            placeholder='article .post-content',
            group='advanced',
        ),
        field(
            'title_selector',
            type='string',
            label='Title selector',
            label_key='modules.browser.readability.params.title_selector.label',
            description='CSS selector for the article title. Leave empty for auto-detection (og:title → h1 → document.title).',
            required=False,
            default='',
            placeholder='h1.article-title',
            group='advanced',
        ),
        field(
            'min_content_length',
            type='number',
            label='Minimum content length',
            label_key='modules.browser.readability.params.min_content_length.label',
            description='Minimum character count to consider content valid.',
            required=False,
            default=80,
            min=0,
            max=1000,
            step=10,
            group='advanced',
        ),
        field(
            'clean_selectors',
            type='array',
            label='Extra clean selectors',
            label_key='modules.browser.readability.params.clean_selectors.label',
            description='Additional CSS selectors to remove from content (e.g., site-specific ads or widgets).',
            required=False,
            default=[],
            items={'type': 'string', 'placeholder': '.ad-wrapper'},
            group='advanced',
        ),
        field(
            'ai_fallback',
            type='boolean',
            label='AI fallback',
            label_key='modules.browser.readability.params.ai_fallback.label',
            description='When heuristic extraction fails (content_found=false), fall back to LLM extraction. Requires AI provider configured.',
            required=False,
            default=False,
            group='advanced',
        ),
    ),
    output_schema={
        'title':         {'type': 'string',  'description': 'Article title'},
        'author':        {'type': 'string',  'description': 'Author name'},
        'date':          {'type': 'string',  'description': 'Publication date (ISO 8601 or raw)'},
        'content':       {'type': 'string',  'description': 'Clean article text (paragraphs separated by \\n\\n)', 'format': 'markdown'},
        'html':          {'type': 'string',  'description': 'Cleaned HTML of the content area', 'format': 'html'},
        'excerpt':       {'type': 'string',  'description': 'Short excerpt (first 300 chars or meta description)'},
        'site_name':     {'type': 'string',  'description': 'Website name'},
        'image':         {'type': 'string',  'description': 'Featured image URL', 'format': 'image'},
        'images':        {'type': 'array',   'description': 'All images in content [{src, alt, width, height}]', 'format': 'gallery'},
        'videos':        {'type': 'array',   'description': 'Embedded videos [{src, type}]'},
        'links':         {'type': 'array',   'description': 'All links in content [{href, text}]'},
        'word_count':    {'type': 'number',  'description': 'Word count of extracted content'},
        'language':      {'type': 'string',  'description': 'Page language code'},
        'url':           {'type': 'string',  'description': 'Page URL'},
        'content_found': {'type': 'boolean', 'description': 'Whether meaningful content was detected'},
    },
    examples=[
        {
            'name': 'Auto-extract article (default)',
            'params': {},
        },
        {
            'name': 'Extract with custom selector (WordPress)',
            'params': {
                'selector': '.entry-content',
                'include_images': True,
            },
        },
        {
            'name': 'News site with ads to remove',
            'params': {
                'clean_selectors': ['.ad-wrapper', '.promo-box', '.paywall-overlay'],
                'wait_ms': 1000,
            },
        },
        {
            'name': 'Extract with custom title selector',
            'params': {
                'title_selector': '.article-headline h1',
                'selector': '.article-body',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.read"],
)
class BrowserReadabilityModule(BaseModule):
    """Smart article extraction from any webpage."""

    module_name = "Extract Article"
    module_description = "Extract article content using readability heuristics"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.selector = self.params.get('selector', '')
        self.title_selector = self.params.get('title_selector', '')
        self.include_images = self.params.get('include_images', True)
        self.include_links = self.params.get('include_links', False)
        self.min_content_length = self.params.get('min_content_length', 80)
        self.clean_selectors = self.params.get('clean_selectors', [])
        self.wait_ms = self.params.get('wait_ms', 0)
        self.ai_fallback = self.params.get('ai_fallback', False)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Optional wait for dynamic content (SPAs, lazy-loaded articles)
        if self.wait_ms > 0:
            await page.wait_for_timeout(self.wait_ms)

        # Inject extraction script and run
        options = {
            'selector': self.selector,
            'title_selector': self.title_selector,
            'include_images': self.include_images,
            'include_links': self.include_links,
            'min_content_length': self.min_content_length,
            'clean_selectors': self.clean_selectors,
        }

        result = await page.evaluate(_EXTRACT_JS, options)

        # AI fallback: when heuristic fails, use LLM to extract from raw page text
        if self.ai_fallback and not result.get('content_found'):
            ai_result = await self._ai_extract(page, result)
            if ai_result:
                result = {**result, **ai_result, 'extraction_method': 'ai'}
            else:
                result['extraction_method'] = 'heuristic_failed'
        else:
            result['extraction_method'] = 'heuristic'

        return {
            "status": "success" if result.get('content_found') else "no_content",
            **result,
        }

    async def _ai_extract(self, page, heuristic_result: dict) -> dict:
        """Fall back to LLM when heuristic extraction fails."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Get page text via snapshot (broader than heuristic content)
            raw_text = await page.evaluate("() => document.body?.innerText?.substring(0, 8000) || ''")
            if len(raw_text.strip()) < 50:
                return None

            # Try to use ai.extract module if available
            try:
                from core.modules.registry import ModuleRegistry
                AiExtractModule = ModuleRegistry.get('ai.extract')
                if not AiExtractModule:
                    raise ImportError("ai.extract not registered")

                ai_module = AiExtractModule({
                    'text': raw_text,
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'title': {'type': 'string', 'description': 'Article title'},
                            'author': {'type': 'string', 'description': 'Author name'},
                            'content': {'type': 'string', 'description': 'Main article content, excluding navigation, ads, comments, and footer'},
                            'date': {'type': 'string', 'description': 'Publication date'},
                        },
                    },
                    'instructions': 'Extract the main article content from this webpage text. Exclude navigation menus, ads, sidebars, comments, and footer. Return the full article body.',
                }, self.context)
                ai_module.validate_params()
                ai_result = await ai_module.execute()

                extracted = ai_result.get('extracted') or ai_result.get('data') or {}
                if isinstance(extracted, dict) and extracted.get('content'):
                    content = extracted['content']
                    return {
                        'title': extracted.get('title') or heuristic_result.get('title', ''),
                        'author': extracted.get('author') or heuristic_result.get('author', ''),
                        'date': extracted.get('date') or heuristic_result.get('date', ''),
                        'content': content,
                        'word_count': len(content.split()),
                        'content_found': True,
                    }
            except (ImportError, Exception) as e:
                logger.debug("AI fallback via ai.extract failed: %s", e)

            return None

        except Exception as e:
            logger.debug("AI fallback failed: %s", e)
            return None
