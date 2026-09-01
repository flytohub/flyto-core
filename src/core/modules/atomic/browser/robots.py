# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Robots Module — robots.txt compliance + sitemap discovery

Fetches and parses robots.txt for any site:
- Check if a URL is allowed/disallowed for scraping
- Extract sitemap URLs
- Get crawl-delay directive
- Respectful scraping by default

HOW FAR THIS MODULE FOLLOWS REALITY

``allowed`` is the field every consumer of this module actually reads, and it is
the field least entitled to be trusted on its own. On the path where robots.txt
was parsed it is derived from real directives. On every other path it is the
literal ``true`` written into the early returns of the page script -- the same
value whether the site has no robots.txt, returned 503, or was never reached at
all. A compliance module that answers "yes, go ahead" identically for "there are
no rules" and "we could not find out" is the shape this contract exists to stop,
and no amount of care in the parser fixes it, because the parser never ran.

So the rung is decided by what came back, and ``claim_by`` records who is making
the claim about ``allowed``:

    robots.txt fetched with a body      OBSERVED, claim_by=none
        Directives were parsed out of a document the server sent. `rule_count`,
        `crawl_delay` and `sitemaps` are readings of that document.

    server answered, no usable body     ACCEPTED, claim_by=inferred
        A 404, a 503, or an empty file. The server answered -- that is what
        ACCEPTED means -- and `allowed: true` is now OUR inference from the
        absence of a document, not a reading of one.

    no answer at all                    INDETERMINATE, claim_by=inferred
        The fetch threw: DNS, CORS, a dropped connection, an `about:blank` page
        whose origin is "null". Whether this site permits scraping is not
        known. `outcome.py` is explicit that an inference of ours that may
        simply be wrong is indeterminate rather than failed.

WHY A BARE STATUS IS ONLY ACCEPTED HERE, when `browser.goto` calls one OBSERVED:
for a navigation the status IS the effect. Here the effect is a set of crawl
directives, and a 404 carries none of them.

A BUG THIS DOES NOT FIX, recorded because the envelope now makes it visible
rather than hiding it: RFC 9309 says a 5xx on robots.txt should be treated as
"disallow all", and this module reports ``allowed: true`` for a 503 exactly as
it does for a 404. Changing that is a change to what the module DOES and belongs
with whoever owns crawl policy; what changes here is that such a run no longer
comes back as an unqualified permission -- it comes back ACCEPTED with the
status in the effect and the claim attributed to us.
"""
import logging
import re
from typing import Any, Dict
from urllib.parse import urlparse, urljoin

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _robots_outcome(
    *,
    exists: bool,
    fetch_failed: bool,
    http_status: Any,
    body_bytes: Any,
    rule_count: Any,
    sitemaps: Any,
    allowed: Any,
    checked_url: str,
) -> Dict[str, Any]:
    """The rung this fetch earned, and who is claiming `allowed`."""
    if exists:
        return envelope(
            Outcome.OBSERVED,
            # NONE, not INFERRED: on this path `allowed` is derived from
            # directives that were actually read. The pattern-to-regex
            # translation is still ours, but it is applied to real rules.
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'robots_directives_parsed',
                'http_status': http_status,
                'bytes': body_bytes,
                'rule_count': rule_count,
                'sitemap_count': len(sitemaps) if isinstance(sitemaps, list) else None,
                'allowed': allowed,
                'checked_url': checked_url,
                'measured_by': (
                    'directives counted from the robots.txt body the server '
                    'returned to fetch()'
                ),
            }],
        )

    if fetch_failed:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'robots_not_fetched',
                'measured_by': None,
                'allowed_is_inferred': True,
                'detail': (
                    'No response came back at all. `allowed: true` on this path '
                    'is this module inferring permission from a request that '
                    'never completed -- it is not a reading of any rule, and it '
                    'is the same value a site that forbids everything would '
                    'produce here.'
                ),
            }],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'no_robots_directives',
            'http_status': http_status,
            'bytes': body_bytes,
            'measured_by': None,
            'allowed_is_inferred': True,
            'detail': (
                'The server answered and no usable robots.txt came back -- a '
                '404, a 5xx, or an empty file. `allowed: true` is this '
                'module\'s inference from that absence. For a 404 it is the '
                'standard reading; for a 5xx RFC 9309 says the opposite, and '
                'this module does not distinguish them. The status is carried '
                'here so a caller can.'
            ),
        }],
    )

_ROBOTS_JS = r"""
async (options) => {
    const baseUrl = options.base_url || window.location.origin;
    const checkUrl = options.check_url || '';
    const userAgent = options.user_agent || '*';

    // Fetch robots.txt
    //
    // `http_status`, `fetch_failed` and `bytes` exist so the caller can tell
    // apart three things that used to arrive identically as
    // `{exists: false, allowed: true}`: a server that answered 404 (there is
    // no robots.txt, and allowing is the standard reading), a server that
    // answered 503 (RFC 9309 says treat that as disallow), and a request that
    // never got an answer at all (we know nothing). `allowed` is unchanged on
    // all three paths; what is new is that the caller can now see which one it
    // is looking at instead of trusting a boolean that is inferred from the
    // absence of a document.
    let robotsTxt = '';
    let httpStatus = 0;
    try {
        const resp = await fetch(baseUrl + '/robots.txt');
        httpStatus = resp.status;
        if (resp.ok) robotsTxt = await resp.text();
    } catch(e) {
        return {
            exists: false, allowed: true,
            reason: 'robots.txt not found or fetch failed',
            matched_rule: '', crawl_delay: 0, sitemaps: [], rule_count: 0,
            http_status: 0, fetch_failed: true, bytes: 0,
        };
    }

    if (!robotsTxt.trim()) {
        return {
            exists: false, allowed: true,
            reason: 'robots.txt empty or missing',
            matched_rule: '', crawl_delay: 0, sitemaps: [], rule_count: 0,
            http_status: httpStatus, fetch_failed: false, bytes: robotsTxt.length,
        };
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
        http_status: httpStatus,
        fetch_failed: false,
        bytes: robotsTxt.length,
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
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'ai.*', 'llm.*', 'agent.*'],
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
        'http_status':  {'type': 'number',  'description': 'HTTP status of the robots.txt fetch (0 when no response came back)'},
        'fetch_failed': {'type': 'boolean', 'description': 'True when no response came back at all (transport failure, not a 404)'},
        'bytes':        {'type': 'number',  'description': 'Size of the robots.txt body that was read'},
        'outcome':      {'type': 'object',
                         'description': (
                             'How far this check was followed: "observed" when '
                             'directives were parsed out of a body the server '
                             'sent, "accepted" when the server answered with '
                             'none (allowed is then inferred from the absence), '
                             '"indeterminate" when no response came back.'
                         )},
    },
    examples=[
        {'name': 'Check if URL is allowed', 'params': {'check_url': '/api/data'}},
        {'name': 'Just get sitemaps', 'params': {}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=15000,
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

        return {
            "status": "success",
            **result,
            "outcome": _robots_outcome(
                exists=bool(result.get('exists')),
                fetch_failed=bool(result.get('fetch_failed')),
                http_status=result.get('http_status'),
                body_bytes=result.get('bytes'),
                rule_count=result.get('rule_count'),
                sitemaps=result.get('sitemaps'),
                allowed=result.get('allowed'),
                checked_url=self.check_url,
            ),
        }
