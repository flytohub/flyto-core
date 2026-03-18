# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Sitemap Module — Parse sitemap.xml and extract URLs

Fetches and parses XML sitemaps:
- Standard sitemap.xml
- Sitemap index files (nested sitemaps)
- Extract URLs with lastmod, changefreq, priority
- Filter by pattern
"""
import logging
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)

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
            if (!resp.ok) return { urls: [], is_index: false, error: `HTTP ${resp.status}` };
            const text = await resp.text();

            const parser = new DOMParser();
            const doc = parser.parseFromString(text, 'text/xml');

            // Check for parse error
            if (doc.querySelector('parsererror')) {
                return { urls: [], is_index: false, error: 'XML parse error' };
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
                    return { urls: locs, is_index: true };
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

            return { urls, is_index: false };
        } catch(e) {
            return { urls: [], is_index: false, error: e.message };
        }
    }

    const result = await parseSitemap(sitemapUrl);

    // If sitemap index, follow child sitemaps
    if (result.is_index && followIndex) {
        const allUrls = [];
        for (const childUrl of result.urls) {
            if (maxUrls > 0 && allUrls.length >= maxUrls) break;
            const child = await parseSitemap(childUrl);
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
        };
    }

    return {
        urls: result.urls,
        count: result.urls.length,
        is_index: false,
        child_sitemaps: 0,
        error: result.error || '',
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
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'array.*'],
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
    },
    examples=[
        {'name': 'Parse site sitemap', 'params': {}},
        {'name': 'Filter blog posts', 'params': {'url_pattern': '/blog/', 'max_urls': 100}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=30000,
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

        return {"status": "success", **result}
