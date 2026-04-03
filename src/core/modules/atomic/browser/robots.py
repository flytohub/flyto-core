# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Robots Module — robots.txt compliance + sitemap discovery

Fetches and parses robots.txt for any site:
- Check if a URL is allowed/disallowed for scraping
- Extract sitemap URLs
- Get crawl-delay directive
- Respectful scraping by default
"""
import logging
import re
from typing import Any
from urllib.parse import urlparse, urljoin
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)

_ROBOTS_JS = r"""
async (options) => {
    const baseUrl = options.base_url || window.location.origin;
    const checkUrl = options.check_url || '';
    const userAgent = options.user_agent || '*';

    // Fetch robots.txt
    let robotsTxt = '';
    try {
        const resp = await fetch(baseUrl + '/robots.txt');
        if (resp.ok) robotsTxt = await resp.text();
    } catch(e) {
        return { exists: false, allowed: true, reason: 'robots.txt not found or fetch failed' };
    }

    if (!robotsTxt.trim()) {
        return { exists: false, allowed: true, reason: 'robots.txt empty or missing' };
    }

    // Parse robots.txt
    const lines = robotsTxt.split('\n').map(l => l.trim());
    let currentAgent = '';
    const rules = {};     // { agent: [{type, path}] }
    const sitemaps = [];
    let crawlDelay = 0;

    for (const line of lines) {
        if (line.startsWith('#') || line === '') continue;
        const [directive, ...rest] = line.split(':');
        const key = directive.trim().toLowerCase();
        const value = rest.join(':').trim();

        if (key === 'user-agent') {
            currentAgent = value.toLowerCase();
            if (!rules[currentAgent]) rules[currentAgent] = [];
        } else if (key === 'disallow' && currentAgent) {
            rules[currentAgent].push({ type: 'disallow', path: value });
        } else if (key === 'allow' && currentAgent) {
            rules[currentAgent].push({ type: 'allow', path: value });
        } else if (key === 'sitemap') {
            sitemaps.push(value);
        } else if (key === 'crawl-delay' && currentAgent) {
            const d = parseFloat(value);
            if (!isNaN(d)) crawlDelay = Math.max(crawlDelay, d);
        }
    }

    // Check if URL is allowed
    let allowed = true;
    let matchedRule = '';

    if (checkUrl) {
        const urlPath = new URL(checkUrl, baseUrl).pathname;
        // Check agent-specific rules, then wildcard
        const agentKey = userAgent.toLowerCase();
        const ruleSets = [rules[agentKey], rules['*']].filter(Boolean);

        for (const ruleSet of ruleSets) {
            let bestMatch = '';
            let bestType = 'allow';

            for (const rule of ruleSet) {
                if (!rule.path) continue;
                // Convert robots.txt pattern to regex
                const pattern = rule.path
                    .replace(/[.+?^${}()|[\]\\]/g, '\\$&')
                    .replace(/\*/g, '.*');
                const re = new RegExp('^' + pattern);
                if (re.test(urlPath) && rule.path.length > bestMatch.length) {
                    bestMatch = rule.path;
                    bestType = rule.type;
                }
            }

            if (bestMatch) {
                allowed = bestType === 'allow';
                matchedRule = bestType + ': ' + bestMatch;
                break;
            }
        }
    }

    return {
        exists: true,
        allowed: allowed,
        matched_rule: matchedRule,
        crawl_delay: crawlDelay,
        sitemaps: sitemaps,
        rule_count: Object.values(rules).reduce((s, r) => s + r.length, 0),
    };
}
"""


@register_module(
    module_id='browser.robots',
    version='1.0.0',
    category='browser',
    tags=['browser', 'robots', 'compliance', 'sitemap', 'crawl'],
    label='Check Robots.txt',
    label_key='modules.browser.robots.label',
    description='Check robots.txt compliance and discover sitemaps. Verify if a URL is allowed for scraping.',
    description_key='modules.browser.robots.description',
    icon='ShieldCheck',
    color='#22C55E',
    input_types=['page'],
    output_types=['json'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'ai.*', 'llm.*'],
    params_schema=compose(
        field('check_url', type='string', label='URL to check',
              description='Specific URL to check if allowed. Empty = just parse robots.txt.',
              required=False, default='', placeholder='https://example.com/api/data',
              group='basic'),
        field('user_agent', type='string', label='User agent name',
              description='Bot name to check rules for (e.g., "Googlebot", "*").',
              default='*', required=False,
              group='basic'),
    ),
    output_schema={
        'exists':       {'type': 'boolean', 'description': 'Whether robots.txt exists'},
        'allowed':      {'type': 'boolean', 'description': 'Whether the URL is allowed for scraping'},
        'matched_rule': {'type': 'string',  'description': 'The robots.txt rule that matched'},
        'crawl_delay':  {'type': 'number',  'description': 'Crawl-delay in seconds (0 if not set)'},
        'sitemaps':     {'type': 'array',   'description': 'Sitemap URLs found in robots.txt'},
        'rule_count':   {'type': 'number',  'description': 'Total number of rules parsed'},
    },
    examples=[
        {'name': 'Check if URL is allowed', 'params': {'check_url': '/api/data'}},
        {'name': 'Just get sitemaps', 'params': {}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=15000,
    required_permissions=["browser.read"],
)
class BrowserRobotsModule(BaseModule):
    module_name = "Check Robots.txt"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.check_url = self.params.get('check_url', '')
        self.user_agent = self.params.get('user_agent', '*')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        base_url = await page.evaluate("() => window.location.origin")

        result = await page.evaluate(_ROBOTS_JS, {
            'base_url': base_url,
            'check_url': self.check_url,
            'user_agent': self.user_agent,
        })

        return {"status": "success", **result}
