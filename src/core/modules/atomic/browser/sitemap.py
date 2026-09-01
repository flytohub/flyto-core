# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Sitemap Module — Parse sitemap.xml and extract URLs

Fetches and parses XML sitemaps:
- Standard sitemap.xml
- Sitemap index files (nested sitemaps)
- Extract URLs with lastmod, changefreq, priority
- Filter by pattern

HOW FAR THIS MODULE FOLLOWS REALITY

This module fetches a URL from inside the page, so `http.request`'s reasoning
applies before anything else: a 2xx is the server reporting on itself. What
this module then does with the response is the part that can be observed --
URLs are parsed out of an XML document the server actually sent, and a URL in
the result is a ``<loc>`` element that existed in it.

    at least one URL parsed        OBSERVED -- those entries were in the document
    zero URLs, server answered     ACCEPTED
    zero URLs, no answer at all    INDETERMINATE

The three-way split is why the page script now returns ``http_status`` and
``fetch_failed`` at all. Before, a 404 and a DNS failure both arrived as
``count: 0`` with a string in ``error``, and a caller could not tell "this site
publishes no sitemap" from "we never reached the site". The first is a real
answer to lean on; the second is the timeout case `outcome.py` insists is
INDETERMINATE and never FAILED, because nothing here knows whether the document
exists.

The middle case covers more than a 404 and is deliberately not split further: a
200 whose body is not XML, a valid sitemap with no ``<url>`` entries, and a
``url_pattern`` that filtered every entry away all land there. Zero URLs reads
identically across all of them, which is the `database.query` empty-read, and
``error`` and ``http_status`` ride in the effect for the consumer who needs to
know which.

WHY A BARE STATUS IS ONLY ACCEPTED HERE, when `browser.goto` calls one
OBSERVED. For a navigation the status IS the effect -- a document response
arrived for that navigation, and there is nothing else to see. Here the effect
is a set of URLs, and a 404 contains none of them: it tells us the server
answered, which is the definition of ACCEPTED, and nothing whatsoever about
what this site publishes.

ONE GAP, named rather than papered over: when the fetched document is an INDEX
and a child sitemap cannot be fetched, the index itself was read successfully,
so ``fetch_failed`` is false and the rung does not become indeterminate. The
count of unreachable children travels as ``child_fetch_failures`` instead. A
run that read the index and reached none of its children reports ACCEPTED with
that count non-zero, which is the honest description: we know the index exists
and we know nothing about what it points at.
"""
import logging
from typing import Any, Dict

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _sitemap_outcome(
    *,
    urls: int,
    is_index: bool,
    status: Any,
    fetch_failed: bool,
    error: str,
    child_sitemaps: Any,
    child_fetch_failures: Any,
) -> Dict[str, Any]:
    """The rung this fetch earned, from what came back rather than from what was asked."""
    if urls > 0:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'sitemap_urls_parsed',
                'count': urls,
                'is_index': is_index,
                'http_status': status,
                'child_sitemaps': child_sitemaps,
                'child_fetch_failures': child_fetch_failures,
                'measured_by': (
                    'len() over the <loc> elements DOMParser found in the XML '
                    'the server returned'
                ),
            }],
        )

    if fetch_failed:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'sitemap_not_fetched',
                'measured_by': None,
                'reason': error or 'the fetch did not complete',
                'detail': (
                    'No response came back at all -- a transport failure, a '
                    'CORS block, or a request that never completed. Whether '
                    'this site publishes a sitemap is not known, which is why '
                    'this is indeterminate rather than an empty result.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'no_sitemap_urls',
            'http_status': status,
            'is_index': is_index,
            'child_sitemaps': child_sitemaps,
            'child_fetch_failures': child_fetch_failures,
            'error': error,
            'measured_by': None,
            'detail': (
                'The server answered and no URL came out. That reads the same '
                'whether the sitemap is missing, is not XML, holds no entries, '
                'or had every entry removed by url_pattern, so it is not an '
                'observation of the site.'
            ),
        }],
    )


_SITEMAP_JS = r"""
async (options) => {
    const sitemapUrl = options.sitemap_url || (window.location.origin + '/sitemap.xml');
    const urlPattern = options.url_pattern || '';
    const maxUrls = options.max_urls || 0;
    const followIndex = options.follow_index !== false;

    const pattern = urlPattern ? new RegExp(urlPattern) : null;

    async function parseSitemap(url) {
        try {
            const resp = await fetch(url);
            // `http_status` and `fetch_failed` exist so the caller can tell a
            // server
            // that answered from a request that never got one. A 404 is an
            // answer; a DNS failure, a CORS block or a dropped connection is
            // not, and the two must not both arrive as "0 urls".
            if (!resp.ok) return { urls: [], is_index: false, error: `HTTP ${resp.status}`, http_status: resp.status, fetch_failed: false };
            const text = await resp.text();

            const parser = new DOMParser();
            const doc = parser.parseFromString(text, 'text/xml');

            // Check for parse error
            if (doc.querySelector('parsererror')) {
                return { urls: [], is_index: false, error: 'XML parse error', http_status: resp.status, fetch_failed: false };
            }

            // Use getElementsByTagName (ignores XML namespaces, unlike querySelector)
            const sitemapTags = doc.getElementsByTagName('sitemap');
            if (sitemapTags.length > 0) {
                const locs = [];
                for (const sm of sitemapTags) {
                    const loc = sm.getElementsByTagName('loc')[0];
                    if (loc) locs.push(loc.textContent.trim());
                }
                if (locs.length > 0) {
                    return { urls: locs, is_index: true, http_status: resp.status, fetch_failed: false };
                }
            }

            // Regular sitemap
            const urlTags = doc.getElementsByTagName('url');
            const urls = [];
            for (const urlTag of urlTags) {
                const locEl = urlTag.getElementsByTagName('loc')[0];
                const loc = locEl?.textContent?.trim() || '';
                if (!loc) continue;
                if (pattern && !pattern.test(loc)) continue;
                if (maxUrls > 0 && urls.length >= maxUrls) break;

                const lastmodEl = urlTag.getElementsByTagName('lastmod')[0];
                const changefreqEl = urlTag.getElementsByTagName('changefreq')[0];
                const priorityEl = urlTag.getElementsByTagName('priority')[0];

                urls.push({
                    url: loc,
                    lastmod: lastmodEl?.textContent?.trim() || '',
                    changefreq: changefreqEl?.textContent?.trim() || '',
                    priority: parseFloat(priorityEl?.textContent?.trim() || '0') || 0,
                });
            }

            return { urls, is_index: false, http_status: resp.status, fetch_failed: false };
        } catch(e) {
            return { urls: [], is_index: false, error: e.message, http_status: 0, fetch_failed: true };
        }
    }

    const result = await parseSitemap(sitemapUrl);

    // If sitemap index, follow child sitemaps
    if (result.is_index && followIndex) {
        const allUrls = [];
        let childFailures = 0;
        for (const childUrl of result.urls) {
            if (maxUrls > 0 && allUrls.length >= maxUrls) break;
            const child = await parseSitemap(childUrl);
            if (child.fetch_failed) childFailures++;
            if (!child.is_index) {
                for (const u of child.urls) {
                    if (maxUrls > 0 && allUrls.length >= maxUrls) break;
                    allUrls.push(u);
                }
            }
        }
        return {
            urls: allUrls,
            count: allUrls.length,
            is_index: true,
            child_sitemaps: result.urls.length,
            child_fetch_failures: childFailures,
            error: '',
            http_status: result.http_status,
            // The index itself was fetched. A child that could not be is
            // reported separately, because "we read an index and could not
            // read what it pointed at" is not the same answer as "we could
            // not reach the sitemap at all".
            fetch_failed: false,
        };
    }

    return {
        urls: result.urls,
        count: result.urls.length,
        is_index: false,
        child_sitemaps: 0,
        child_fetch_failures: 0,
        error: result.error || '',
        http_status: result.http_status || 0,
        fetch_failed: result.fetch_failed === true,
    };
}
"""


@register_module(
    module_id='browser.sitemap',
    version='1.0.0',
    category='browser',
    tags=['browser', 'sitemap', 'crawl', 'urls', 'seo'],
    label='Parse Sitemap',
    label_key='modules.browser.sitemap.label',
    description='Parse sitemap.xml and extract URLs. Supports sitemap index files and URL filtering.',
    description_key='modules.browser.sitemap.description',
    icon='Map',
    color='#3B82F6',
    input_types=['page'],
    output_types=['array', 'json'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'array.*', 'ai.*', 'llm.*', 'agent.*'],
    params_schema=compose(
        field('sitemap_url', type='string', label='Sitemap URL',
              description='Full URL to sitemap.xml. Leave empty to use current site\'s /sitemap.xml.',
              required=False, default='', placeholder='https://example.com/sitemap.xml',
              group='basic'),
        field('url_pattern', type='string', label='URL filter',
              description='Regex to filter URLs (e.g., "/blog/", "/products/"). Empty = all URLs.',
              required=False, default='',
              group='basic'),
        field('max_urls', type='number', label='Max URLs',
              description='Maximum URLs to return. 0 = all.',
              default=0, min=0, max=50000,
              group='basic'),
        field('follow_index', type='boolean', label='Follow index',
              description='If sitemap is an index, automatically follow child sitemaps.',
              default=True,
              group='advanced'),
    ),
    output_schema={
        'urls':            {'type': 'array',   'description': 'URLs found [{url, lastmod, changefreq, priority}]'},
        'count':           {'type': 'number',  'description': 'Number of URLs found'},
        'is_index':        {'type': 'boolean', 'description': 'Whether the sitemap was an index file'},
        'child_sitemaps':  {'type': 'number',  'description': 'Number of child sitemaps (if index)'},
        'child_fetch_failures': {'type': 'number', 'description': 'Child sitemaps that could not be fetched'},
        'http_status':     {'type': 'number',  'description': 'HTTP status of the sitemap fetch (0 when no response came back)'},
        'fetch_failed':    {'type': 'boolean', 'description': 'True when no response came back at all (transport failure, not a 404)'},
        'outcome':         {'type': 'object',
                            'description': (
                                'How far this fetch was followed: "observed" '
                                'when URLs were parsed out of the document the '
                                'server sent, "accepted" when the server '
                                'answered with none, "indeterminate" when no '
                                'response came back at all.'
                            )},
    },
    examples=[
        {'name': 'Parse site sitemap', 'params': {}},
        {'name': 'Filter blog posts', 'params': {'url_pattern': '/blog/', 'max_urls': 100}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read"],
)
class BrowserSitemapModule(BaseModule):
    module_name = "Parse Sitemap"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.sitemap_url = self.params.get('sitemap_url', '')
        self.url_pattern = self.params.get('url_pattern', '')
        self.max_urls = self.params.get('max_urls', 0)
        self.follow_index = self.params.get('follow_index', True)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        result = await browser.page.evaluate(_SITEMAP_JS, {
            'sitemap_url': self.sitemap_url,
            'url_pattern': self.url_pattern,
            'max_urls': self.max_urls,
            'follow_index': self.follow_index,
        })

        # The page script's field is `http_status`, not `status`: "status" was
        # already this module's operation field, and a fetch that answered 404
        # arriving as ``status: 404`` beside ``status: 'success'`` would be one
        # of them silently winning.
        return {
            "status": "success",
            **result,
            "outcome": _sitemap_outcome(
                urls=result.get('count') or 0,
                is_index=bool(result.get('is_index')),
                status=result.get('http_status'),
                fetch_failed=bool(result.get('fetch_failed')),
                error=result.get('error') or '',
                child_sitemaps=result.get('child_sitemaps'),
                child_fetch_failures=result.get('child_fetch_failures'),
            ),
        }
