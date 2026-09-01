# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Performance Module - Web Vitals and Performance Metrics

Collects Web Vitals (LCP, FCP, CLS, TTFB) and other performance metrics
using the Performance API via JavaScript injection.

Works across all browsers (Chromium, Firefox, WebKit).

THE NUMBERS ARE REAL. `status: "success"` WAS NOT.

Unusually for this sweep, what this module reports about its own effect is a
measurement and not an echo. ``navEntry.responseStart``, ``fcpEntry.startTime``,
the ``layout-shift`` entries — the browser computed each of those while the page
loaded, and no parameter of this module contributes to any of them. What was
missing is a way for a consumer to tell that apart from the two payloads that
carry no measurement at all and were shaped identically:

    metrics came back                    OBSERVED
    the filter left nothing              ACCEPTED
    page.evaluate raised                 FAILED

The middle case is `database.query`'s empty read. ``{}`` is what a caller gets
when the requested metric names are ones this page has no entry for -- an LCP on
a page with no contentful paint, a ``fid`` with no user input, ``jsHeapUsed``
outside Chrome. It reads the same whether the page had nothing to report or the
evaluation returned junk, so it claims only that the page answered.

The last case is the one that mattered most. ``except Exception`` returned
``{"status": "error", "metrics": {}}`` -- indistinguishable from a filtered-out
empty result to anything reading `metrics`, and a `status` string is not
something the outcome contract can read. FAILED is correct and is not a matter
of policy: `outcome.py` defines it as "the execution itself raised", and this is
the branch that catches the raise.

WHAT OBSERVED DOES NOT SAY. These are the page's own numbers about the page as
it currently stands. A metric absent from the returned dict is absent because
the browser had no entry for it, which is not the same as zero, and this module
does not invent one -- `_calculate_ratings` correspondingly rates only the keys
that are present.
"""
from typing import Any, Dict, List, Optional
import asyncio

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup


def _metrics_outcome(*, metrics: Dict[str, Any], requested: List[str]) -> Dict[str, Any]:
    """OBSERVED for numbers the browser produced, ACCEPTED for an empty answer."""
    names = sorted(metrics)
    if names:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'performance_metrics_read',
                'count': len(names),
                'metrics': names,
                'requested': list(requested),
                'measured_by': (
                    'page.evaluate of the Performance API -- PerformanceNavigation'
                    'Timing, paint, layout-shift and first-input entries the '
                    'browser recorded during the page load'
                ),
                'detail': (
                    'Timings the browser computed. No parameter of this module '
                    'contributes to them. A metric missing from this list is '
                    'missing because the browser had no entry for it, which is '
                    'not the same as zero.'
                ),
            }],
        )
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'no_performance_metrics',
            'requested': list(requested),
            'measured_by': None,
            'detail': (
                'The page answered and there is nothing in the answer. That '
                'reads the same whether this page has no entry for the '
                'requested metrics -- an LCP with no contentful paint, a fid '
                'with no user input -- or the evaluation returned something '
                'unusable, so it is not an observation of the page.'
            ),
        }],
    )


def _metrics_failed_outcome(*, error: str, requested: List[str]) -> Dict[str, Any]:
    """FAILED for the branch that catches the raise."""
    return envelope(
        Outcome.FAILED,
        # CALLER: metrics were asked for and none were collected. This is not an
        # inference that may be wrong -- an exception was caught here.
        claim_by=ClaimBy.CALLER,
        effects=[{
            'kind': 'performance_collection_raised',
            'requested': list(requested),
            'error': error[:300],
            'measured_by': 'the exception raised out of page.evaluate',
            'detail': (
                'Collection raised and the empty metrics dict beside this is a '
                'literal in the module. Without this, an error and a page with '
                'nothing to report were the same payload.'
            ),
        }],
    )


# JavaScript to collect performance metrics
PERFORMANCE_SCRIPT = """
() => {
    const metrics = {};

    // Navigation Timing API (always available)
    const timing = performance.timing || {};
    const navEntry = performance.getEntriesByType('navigation')[0] || {};

    // Basic timing metrics
    if (navEntry.domContentLoadedEventEnd) {
        metrics.domContentLoaded = navEntry.domContentLoadedEventEnd;
    } else if (timing.domContentLoadedEventEnd && timing.navigationStart) {
        metrics.domContentLoaded = timing.domContentLoadedEventEnd - timing.navigationStart;
    }

    if (navEntry.loadEventEnd) {
        metrics.load = navEntry.loadEventEnd;
    } else if (timing.loadEventEnd && timing.navigationStart) {
        metrics.load = timing.loadEventEnd - timing.navigationStart;
    }

    // TTFB (Time to First Byte)
    if (navEntry.responseStart) {
        metrics.ttfb = navEntry.responseStart;
    } else if (timing.responseStart && timing.navigationStart) {
        metrics.ttfb = timing.responseStart - timing.navigationStart;
    }

    // First Contentful Paint (FCP)
    const fcpEntry = performance.getEntriesByName('first-contentful-paint')[0];
    if (fcpEntry) {
        metrics.fcp = fcpEntry.startTime;
    }

    // Largest Contentful Paint (LCP) - requires PerformanceObserver
    // We'll check if any LCP entries exist
    const lcpEntries = performance.getEntriesByType('largest-contentful-paint');
    if (lcpEntries && lcpEntries.length > 0) {
        const lastEntry = lcpEntries[lcpEntries.length - 1];
        metrics.lcp = lastEntry.startTime;
        metrics.lcpElement = lastEntry.element ? lastEntry.element.tagName : null;
    }

    // Cumulative Layout Shift (CLS)
    const layoutShiftEntries = performance.getEntriesByType('layout-shift');
    if (layoutShiftEntries && layoutShiftEntries.length > 0) {
        let clsValue = 0;
        let sessionValue = 0;
        let sessionEntries = [];

        for (const entry of layoutShiftEntries) {
            if (!entry.hadRecentInput) {
                if (sessionEntries.length > 0 &&
                    entry.startTime - sessionEntries[sessionEntries.length - 1].startTime < 1000 &&
                    entry.startTime - sessionEntries[0].startTime < 5000) {
                    sessionValue += entry.value;
                    sessionEntries.push(entry);
                } else {
                    if (sessionValue > clsValue) {
                        clsValue = sessionValue;
                    }
                    sessionValue = entry.value;
                    sessionEntries = [entry];
                }
            }
        }
        if (sessionValue > clsValue) {
            clsValue = sessionValue;
        }
        metrics.cls = clsValue;
    }

    // First Input Delay (FID) - from first-input entry if available
    const fidEntry = performance.getEntriesByType('first-input')[0];
    if (fidEntry) {
        metrics.fid = fidEntry.processingStart - fidEntry.startTime;
    }

    // Resource count and size
    const resources = performance.getEntriesByType('resource');
    metrics.resourceCount = resources.length;
    metrics.resourceTotalSize = resources.reduce((total, r) => total + (r.transferSize || 0), 0);

    // JS heap size (Chrome only)
    if (performance.memory) {
        metrics.jsHeapUsed = performance.memory.usedJSHeapSize;
        metrics.jsHeapTotal = performance.memory.totalJSHeapSize;
    }

    return metrics;
}
"""

# JavaScript to set up PerformanceObserver for better metrics collection
SETUP_OBSERVERS_SCRIPT = """
() => {
    // Store metrics globally for later retrieval
    window.__flyto_perf_metrics = window.__flyto_perf_metrics || {
        lcp: null,
        cls: 0,
        fid: null,
        lcpElement: null
    };

    // LCP Observer
    if ('PerformanceObserver' in window) {
        try {
            const lcpObserver = new PerformanceObserver((entryList) => {
                const entries = entryList.getEntries();
                const lastEntry = entries[entries.length - 1];
                window.__flyto_perf_metrics.lcp = lastEntry.startTime;
                window.__flyto_perf_metrics.lcpElement = lastEntry.element ? lastEntry.element.tagName : null;
            });
            lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
        } catch (e) {}

        // CLS Observer
        try {
            let clsValue = 0;
            let sessionValue = 0;
            let sessionEntries = [];

            const clsObserver = new PerformanceObserver((entryList) => {
                for (const entry of entryList.getEntries()) {
                    if (!entry.hadRecentInput) {
                        if (sessionEntries.length > 0 &&
                            entry.startTime - sessionEntries[sessionEntries.length - 1].startTime < 1000 &&
                            entry.startTime - sessionEntries[0].startTime < 5000) {
                            sessionValue += entry.value;
                            sessionEntries.push(entry);
                        } else {
                            if (sessionValue > clsValue) {
                                clsValue = sessionValue;
                            }
                            sessionValue = entry.value;
                            sessionEntries = [entry];
                        }
                    }
                }
                if (sessionValue > clsValue) {
                    clsValue = sessionValue;
                }
                window.__flyto_perf_metrics.cls = clsValue;
            });
            clsObserver.observe({ type: 'layout-shift', buffered: true });
        } catch (e) {}

        // FID Observer
        try {
            const fidObserver = new PerformanceObserver((entryList) => {
                const entry = entryList.getEntries()[0];
                window.__flyto_perf_metrics.fid = entry.processingStart - entry.startTime;
            });
            fidObserver.observe({ type: 'first-input', buffered: true });
        } catch (e) {}
    }

    return true;
}
"""

# Get stored observer metrics
GET_OBSERVER_METRICS_SCRIPT = """
() => {
    return window.__flyto_perf_metrics || {};
}
"""


@register_module(
    module_id='browser.performance',
    version='1.0.0',
    category='browser',
    tags=['browser', 'performance', 'metrics', 'web-vitals', 'lcp', 'fcp', 'cls'],
    label='Performance Metrics',
    label_key='modules.browser.performance.label',
    description='Collect Web Vitals (LCP, FCP, CLS, TTFB) and performance metrics',
    description_key='modules.browser.performance.description',
    icon='Gauge',
    color='#10B981',

    # Connection types
    input_types=['page'],
    output_types=['json'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field(
            'metrics',
            type='array',
            label='Metrics to Collect',
            label_key='modules.browser.performance.params.metrics.label',
            description='Which metrics to collect (default: all)',
            required=False,
            default=['all'],
            items={"type": "string"},
            group=FieldGroup.BASIC,
        ),
        field(
            'timeout_ms',
            type='number',
            label='Wait Time (ms)',
            label_key='modules.browser.performance.params.timeout_ms.label',
            description='Time to wait for metrics collection (for LCP, CLS)',
            required=False,
            default=3000,
            min=0,
            max=30000,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'setup_observers',
            type='boolean',
            label='Setup Observers',
            label_key='modules.browser.performance.params.setup_observers.label',
            description='Install PerformanceObservers for better metric tracking',
            required=False,
            default=True,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.performance.output.status.description'
        },
        'metrics': {
            'type': 'object',
            'description': 'Collected performance metrics',
            'description_key': 'modules.browser.performance.output.metrics.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the collection was followed: "observed" when the '
                'browser returned metrics, "accepted" when the answer was '
                'empty, "failed" when collection raised'
            ),
            'description_key': 'modules.browser.performance.output.outcome.description'
        },
    },
    examples=[
        {
            'name': 'Collect all metrics',
            'params': {'metrics': ['all'], 'timeout_ms': 5000}
        },
        {
            'name': 'Collect only Core Web Vitals',
            'params': {'metrics': ['lcp', 'fcp', 'cls']}
        },
        {
            'name': 'Quick timing check',
            'params': {'metrics': ['ttfb', 'domContentLoaded', 'load'], 'timeout_ms': 0}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.automation'],
)
class BrowserPerformanceModule(BaseModule):
    """Performance Metrics Module for Web Vitals collection"""

    module_name = "Performance Metrics"
    module_description = "Collect Web Vitals and performance metrics"
    required_permission = "browser.automation"

    # Available metrics
    AVAILABLE_METRICS = {
        'lcp', 'fcp', 'cls', 'fid', 'ttfb',
        'domContentLoaded', 'load',
        'resourceCount', 'resourceTotalSize',
        'jsHeapUsed', 'jsHeapTotal',
        'lcpElement'
    }

    def validate_params(self) -> None:
        self.metrics_filter = self.params.get('metrics', ['all'])
        self.timeout_ms = self.params.get('timeout_ms', 3000)
        self.setup_observers = self.params.get('setup_observers', True)

        # Validate metric names
        if 'all' not in self.metrics_filter:
            for m in self.metrics_filter:
                if m not in self.AVAILABLE_METRICS:
                    raise ValueError(
                        f"Invalid metric: {m}. "
                        f"Available: {', '.join(sorted(self.AVAILABLE_METRICS))}"
                    )

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        try:
            # Setup observers for better metrics (if enabled)
            if self.setup_observers:
                await page.evaluate(SETUP_OBSERVERS_SCRIPT)

            # Wait for metrics to be collected (LCP needs user interaction or page to settle)
            if self.timeout_ms > 0:
                await asyncio.sleep(self.timeout_ms / 1000)

            # Collect metrics via Performance API
            raw_metrics = await page.evaluate(PERFORMANCE_SCRIPT)

            # Merge with observer metrics if available
            if self.setup_observers:
                observer_metrics = await page.evaluate(GET_OBSERVER_METRICS_SCRIPT)
                # Observer metrics take precedence (more accurate)
                if observer_metrics.get('lcp') is not None:
                    raw_metrics['lcp'] = observer_metrics['lcp']
                if observer_metrics.get('lcpElement') is not None:
                    raw_metrics['lcpElement'] = observer_metrics['lcpElement']
                if observer_metrics.get('cls') is not None:
                    raw_metrics['cls'] = observer_metrics['cls']
                if observer_metrics.get('fid') is not None:
                    raw_metrics['fid'] = observer_metrics['fid']

            # Filter metrics if specific ones requested
            if 'all' not in self.metrics_filter:
                raw_metrics = {
                    k: v for k, v in raw_metrics.items()
                    if k in self.metrics_filter
                }

            # Round floating point values
            metrics = {}
            for key, value in raw_metrics.items():
                if value is None:
                    metrics[key] = None
                elif isinstance(value, float):
                    # Round to 2 decimal places for timing, 4 for CLS
                    if key == 'cls':
                        metrics[key] = round(value, 4)
                    else:
                        metrics[key] = round(value, 2)
                else:
                    metrics[key] = value

            # Add rating for Web Vitals
            ratings = self._calculate_ratings(metrics)

            return {
                "status": "success",
                "metrics": metrics,
                "ratings": ratings,
                "url": page.url,
                "outcome": _metrics_outcome(
                    metrics=metrics, requested=self.metrics_filter,
                ),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "metrics": {},
                "outcome": _metrics_failed_outcome(
                    error=str(e), requested=self.metrics_filter,
                ),
            }

    def _calculate_ratings(self, metrics: Dict[str, Any]) -> Dict[str, str]:
        """
        Calculate ratings based on Google's Web Vitals thresholds.

        Good / Needs Improvement / Poor thresholds:
        - LCP: 2500ms / 4000ms
        - FCP: 1800ms / 3000ms
        - CLS: 0.1 / 0.25
        - FID: 100ms / 300ms
        - TTFB: 800ms / 1800ms
        """
        ratings = {}

        # LCP rating
        if metrics.get('lcp') is not None:
            lcp = metrics['lcp']
            if lcp <= 2500:
                ratings['lcp'] = 'good'
            elif lcp <= 4000:
                ratings['lcp'] = 'needs-improvement'
            else:
                ratings['lcp'] = 'poor'

        # FCP rating
        if metrics.get('fcp') is not None:
            fcp = metrics['fcp']
            if fcp <= 1800:
                ratings['fcp'] = 'good'
            elif fcp <= 3000:
                ratings['fcp'] = 'needs-improvement'
            else:
                ratings['fcp'] = 'poor'

        # CLS rating
        if metrics.get('cls') is not None:
            cls = metrics['cls']
            if cls <= 0.1:
                ratings['cls'] = 'good'
            elif cls <= 0.25:
                ratings['cls'] = 'needs-improvement'
            else:
                ratings['cls'] = 'poor'

        # FID rating
        if metrics.get('fid') is not None:
            fid = metrics['fid']
            if fid <= 100:
                ratings['fid'] = 'good'
            elif fid <= 300:
                ratings['fid'] = 'needs-improvement'
            else:
                ratings['fid'] = 'poor'

        # TTFB rating
        if metrics.get('ttfb') is not None:
            ttfb = metrics['ttfb']
            if ttfb <= 800:
                ratings['ttfb'] = 'good'
            elif ttfb <= 1800:
                ratings['ttfb'] = 'needs-improvement'
            else:
                ratings['ttfb'] = 'poor'

        return ratings
