# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Challenge Module — Auto-detect and handle anti-bot challenges

Detects Cloudflare, hCaptcha, reCAPTCHA, and custom challenge pages.
Strategy:
  1. Check if current page is a challenge (by title/content patterns)
  2. If no challenge → pass through immediately
  3. If challenge detected → wait for auto-resolution (many challenges auto-resolve)
  4. If still blocked after timeout → trigger human-in-the-loop breakpoint
  5. Persistent context saves cookies → challenge only needs to be solved ONCE per site

Works with browser.interact breakpoint system for manual fallback.

HOW FAR A CLEARED CHALLENGE IS FOLLOWED

This module is unusual in the browser set: it barely acts, and it reads the live
page twice. That makes the before/after pair the whole story.

``_CHALLENGE_PATTERNS_JS`` reads ``document.title``, the URL and the first 500
characters of ``innerText`` out of the page. ``_CHECK_RESOLVED_JS`` reads the
title again and the body length. Both are the page's own state; neither restates
a parameter. So when detection says "this is a Cloudflare interstitial" and the
later check says "the title no longer matches and the body has real content in
it", two readings of the same page disagree, and the disagreement happened in
the browser.

    a challenge was detected, and the page later cleared      OBSERVED
    no challenge was detected at all                          ACCEPTED
    a challenge was detected and the page never cleared       INDETERMINATE

The rung is INFERRED throughout, and it is worth saying why rather than leaving
it in the enum: "cleared" is a heuristic this file wrote -- title-does-not-match
AND ``innerText.length > 100``. A challenge page that renders a long body under
an unfamiliar title reads as cleared, and a real page under 100 characters reads
as blocked. It is an observation of the page, not a verification of access, and
no `postcondition=` is declared because there is no predicate here anybody
promised.

ACCEPTED for "no challenge detected" is the `database.query` empty-read rule:
finding no matches reads identically whether the page truly had none or the
pattern list simply does not cover this site's interstitial, and this pattern
list is a hand-written five-case guess at an adversarial, changing target. The
module returning ``no_challenge`` is not evidence that the page is clean.

The last line is the one that changes what a consumer sees. ``status:
"human_resolved"`` was returned on two branches that differ in exactly the thing
a caller cares about -- one where ``_CHECK_RESOLVED_JS`` said the page had
cleared and one where it said it had not -- and the second is the more common
outcome of a human approving a breakpoint too early. The status is left alone,
because consumers switch on it; a ``page_changed`` field and the envelope now
carry the difference the status lost.
"""
import logging
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)


#: What cleared the page, for the record. The rung does not depend on it -- a
#: page that cleared, cleared -- but which route got there is the difference
#: between an automation that runs unattended and one that needs a person.
_ROUTE_DETAIL = {
    'auto_wait': 'the module waited and the page cleared on its own',
    'api_solver': 'a third-party solver was called and the page then cleared',
    'human': 'a human was shown the page and approved the breakpoint',
    'no_human_fallback': 'human fallback was switched off, so nothing else was tried',
}


def _no_challenge_outcome(title: Optional[str]) -> Dict[str, Any]:
    """Detection ran against the live page and matched none of its patterns."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'no_challenge_pattern_matched',
            'title': title,
            'measured_by': None,
            'detail': (
                'The live page was read and matched none of the five patterns '
                'this file knows. An empty match reads the same whether the '
                'page really has no interstitial or this site\'s interstitial '
                'is simply not in the list, so it is not evidence the page is '
                'clean. Nothing was done to the page either way.'
            ),
        }],
    )


def _challenge_outcome(
    *,
    challenge_type: str,
    resolved: bool,
    route: str,
    wait_seconds: float,
) -> Dict[str, Any]:
    """The rung a detected challenge earned, from the second reading of the page."""
    detection_effect = {
        'kind': 'challenge_detected',
        'challenge_type': challenge_type,
        'measured_by': 'document.title, location.href and body innerText, read from the live page',
        'detail': (
            'The page matched a known interstitial pattern before anything was '
            'tried. This reading is what the later one is compared against.'
        ),
    }

    if resolved:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: "cleared" is this file's own heuristic, not a contract
            # anybody declared. See the module docstring.
            claim_by=ClaimBy.INFERRED,
            effects=[detection_effect, {
                'kind': 'challenge_page_cleared',
                'route': route,
                'wait_seconds': wait_seconds,
                'measured_by': (
                    'document.title and body innerText length, re-read from the '
                    'same live page after the wait'
                ),
                'detail': (
                    f'Two readings of the same page disagree: {_ROUTE_DETAIL.get(route, route)}, '
                    'and the title no longer matches an interstitial while the '
                    'body now carries more than 100 characters. That is the '
                    'page having changed, not access having been verified.'
                ),
            }],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[detection_effect, {
            'kind': 'challenge_page_did_not_clear',
            'route': route,
            'wait_seconds': wait_seconds,
            'predicate': 'the title stops matching an interstitial and the body exceeds 100 characters',
            'measured_by': (
                'document.title and body innerText length, re-read from the '
                'same live page after the wait'
            ),
            'detail': (
                'The second reading looks like the first one. That reads the '
                'same whether the challenge is still blocking us, the site '
                'replaced it with a different wall, or the page cleared into '
                'something under 100 characters. We cannot say which, so this '
                'is indeterminate rather than failed.'
            ),
        }],
    )

# Known challenge page patterns (title, URL, or body content)
_CHALLENGE_PATTERNS_JS = r"""
(opts) => {
    const title = (document.title || '').toLowerCase();
    const url = window.location.href;
    const body = document.body?.innerText?.substring(0, 500)?.toLowerCase() || '';

    const challenges = [];

    // Cloudflare
    if (title.includes('just a moment') || title.includes('attention required') ||
        title.includes('checking your browser') || title.includes('please wait')) {
        challenges.push({
            type: 'cloudflare',
            has_turnstile: !!document.querySelector('iframe[src*="challenges.cloudflare"]'),
            has_checkbox: !!document.querySelector('#challenge-form, .cf-turnstile'),
        });
    }

    // hCaptcha
    if (document.querySelector('iframe[src*="hcaptcha.com"], .h-captcha')) {
        challenges.push({ type: 'hcaptcha' });
    }

    // reCAPTCHA
    if (document.querySelector('iframe[src*="recaptcha"], .g-recaptcha')) {
        challenges.push({ type: 'recaptcha' });
    }

    // Generic "verify you are human"
    if (body.includes('verify you are human') || body.includes('are you a robot') ||
        body.includes('please verify') || body.includes('bot detection')) {
        challenges.push({ type: 'generic_verify' });
    }

    // Access denied / 403
    if (document.querySelector('meta[http-equiv="refresh"]') && title.includes('denied')) {
        challenges.push({ type: 'access_denied' });
    }

    return {
        has_challenge: challenges.length > 0,
        challenges: challenges,
        title: document.title,
        url: window.location.href,
    };
}
"""

_CHECK_RESOLVED_JS = r"""
() => {
    const title = (document.title || '').toLowerCase();
    // Still on challenge page?
    if (title.includes('just a moment') || title.includes('attention required') ||
        title.includes('checking your browser') || title.includes('please wait')) {
        return false;
    }
    // Page has real content now?
    const bodyLen = document.body?.innerText?.trim()?.length || 0;
    return bodyLen > 100;
}
"""


@register_module(
    module_id='browser.challenge',
    version='1.0.0',
    category='browser',
    tags=['browser', 'cloudflare', 'captcha', 'challenge', 'anti-bot'],
    label='Handle Challenge',
    label_key='modules.browser.challenge.label',
    description='Auto-detect and handle anti-bot challenges (Cloudflare, CAPTCHA). Waits for auto-resolution, falls back to human-in-the-loop.',
    description_key='modules.browser.challenge.description',
    icon='Shield',
    color='#EF4444',

    input_types=['page'],
    output_types=['page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field('auto_wait_seconds', type='number',
              label='Auto-wait timeout (seconds)',
              description='How long to wait for the challenge to auto-resolve before trying API solver or human help. 0 = skip auto-wait.',
              default=15, min=0, max=120, step=5,
              group='basic'),

        # ── API Captcha Solving ──────────────────────────────────
        field('captcha_provider', type='select',
              label='Captcha Solver',
              description='Third-party API for automatic captcha solving. Leave empty to skip API solving.',
              default='',
              options=[
                  {'value': '', 'label': 'None (auto-wait + human only)'},
                  {'value': '2captcha', 'label': '2Captcha'},
                  {'value': 'capsolver', 'label': 'CapSolver'},
                  {'value': 'captchaai', 'label': 'CaptchaAI'},
              ],
              group='basic'),
        field('captcha_api_key', type='string',
              label='Captcha API Key',
              description='API key for the captcha solving service',
              format='password',
              required=False,
              showIf={"captcha_provider": {"$in": ["2captcha", "capsolver", "captchaai"]}},
              group='basic'),

        field('human_fallback', type='boolean',
              label='Human fallback',
              description='If auto-wait and API solver both fail, create a breakpoint for the user to solve manually.',
              default=True,
              group='basic'),
        field('human_timeout_seconds', type='number',
              label='Human timeout (seconds)',
              description='How long to wait for human to solve the challenge. 0 = wait indefinitely.',
              default=120, min=0, max=600, step=30,
              group='basic'),
    ),
    output_schema={
        'status':           {'type': 'string',  'description': 'Result: passed / no_challenge / auto_resolved / human_resolved / timeout'},
        'challenge_type':   {'type': 'string',  'description': 'Type of challenge detected (cloudflare, hcaptcha, recaptcha, generic_verify, none)'},
        'wait_seconds':     {'type': 'number',  'description': 'How long it took to resolve'},
        'required_human':   {'type': 'boolean', 'description': 'Whether human intervention was needed'},
        'page_changed':     {'type': 'boolean', 'description': 'Whether the page stopped reading as an interstitial. False on the human_resolved branch where a person approved but the page did not clear.'},
        'outcome':          {'type': 'object',  'description': (
            'How far the effect was followed: observed when a detected '
            'challenge page later read as cleared, indeterminate when it did '
            'not, accepted when no challenge pattern matched in the first place.'
        )},
    },
    examples=[
        {'name': 'Default (15s auto-wait, then ask human)', 'params': {}},
        {'name': 'Skip auto-wait, always ask human', 'params': {'auto_wait_seconds': 0, 'human_fallback': True}},
        {'name': 'Auto-only, no human fallback', 'params': {'auto_wait_seconds': 30, 'human_fallback': False}},
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=180000,  # 3 minutes max (challenge + human)
    required_permissions=["browser.read"],
)
class BrowserChallengeModule(BaseModule):
    """Handle anti-bot challenges with auto-wait + human fallback."""

    module_name = "Handle Challenge"
    module_description = "Detect and handle anti-bot challenges"
    required_permission = "browser.read"

    def validate_params(self) -> None:
        self.auto_wait = self.params.get('auto_wait_seconds', 15)
        self.captcha_provider = self.params.get('captcha_provider', '')
        self.captcha_api_key = self.params.get('captcha_api_key', '')
        self.human_fallback = self.params.get('human_fallback', True)
        self.human_timeout = self.params.get('human_timeout_seconds', 120)

        if self.captcha_provider and not self.captcha_api_key:
            raise ValueError(f"captcha_api_key is required when using {self.captcha_provider}")

    async def execute(self) -> Any:
        import asyncio
        import time

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page

        # Step 1: Detect challenge
        detection = await page.evaluate(_CHALLENGE_PATTERNS_JS, {})

        if not detection['has_challenge']:
            return {
                "status": "no_challenge",
                "challenge_type": "none",
                "wait_seconds": 0,
                "required_human": False,
                "page_changed": False,
                "outcome": _no_challenge_outcome(detection.get('title')),
            }

        challenge_type = detection['challenges'][0]['type'] if detection['challenges'] else 'unknown'
        logger.info("Challenge detected: %s on %s", challenge_type, detection['url'])

        # Step 2: Auto-wait for resolution
        t0 = time.monotonic()
        resolved = False

        if self.auto_wait > 0:
            logger.info("Waiting up to %ds for auto-resolution...", self.auto_wait)
            for _ in range(self.auto_wait):
                await asyncio.sleep(1)
                resolved = await page.evaluate(_CHECK_RESOLVED_JS)
                if resolved:
                    break

        if resolved:
            elapsed = round(time.monotonic() - t0, 1)
            logger.info("Challenge auto-resolved in %ss", elapsed)
            return {
                "status": "auto_resolved",
                "challenge_type": challenge_type,
                "wait_seconds": elapsed,
                "required_human": False,
                "page_changed": True,
                "outcome": _challenge_outcome(
                    challenge_type=challenge_type, resolved=True,
                    route='auto_wait', wait_seconds=elapsed,
                ),
            }

        # Step 3: API-based captcha solving
        if self.captcha_provider and self.captcha_api_key:
            logger.info("Attempting API-based solve via %s...", self.captcha_provider)
            try:
                from core.browser.captcha import CaptchaSolver
                solver = CaptchaSolver(self.captcha_provider, self.captcha_api_key)
                solve_result = await solver.solve(page)

                if solve_result['status'] == 'solved':
                    # Verify page changed after solving
                    await asyncio.sleep(2)
                    resolved = await page.evaluate(_CHECK_RESOLVED_JS)
                    elapsed = round(time.monotonic() - t0, 1)

                    if resolved:
                        logger.info("Challenge solved by %s in %ss", self.captcha_provider, elapsed)
                        return {
                            "status": "api_solved",
                            "challenge_type": challenge_type,
                            "wait_seconds": elapsed,
                            "required_human": False,
                            "solver_provider": self.captcha_provider,
                            "solver_time": solve_result.get('solve_time', 0),
                            "page_changed": True,
                            "outcome": _challenge_outcome(
                                challenge_type=challenge_type, resolved=True,
                                route='api_solver', wait_seconds=elapsed,
                            ),
                        }
                    else:
                        logger.warning("API solved but page didn't change, falling through...")
                else:
                    logger.warning("API solve failed: %s", solve_result.get('error', 'unknown'))
            except Exception as e:
                logger.error("API captcha solve error: %s", e)

        # Step 4: Human fallback via breakpoint
        if not self.human_fallback:
            elapsed = round(time.monotonic() - t0, 1)
            return {
                "status": "timeout",
                "challenge_type": challenge_type,
                "wait_seconds": elapsed,
                "required_human": False,
                "page_changed": False,
                "outcome": _challenge_outcome(
                    challenge_type=challenge_type, resolved=False,
                    route='no_human_fallback', wait_seconds=elapsed,
                ),
            }

        logger.info("Auto-wait failed. Requesting human intervention...")

        # Take screenshot for the breakpoint UI
        screenshot_b64 = ""
        try:
            screenshot_bytes = await page.screenshot(type="jpeg", quality=70)
            import base64
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
        except Exception:
            pass

        # Create breakpoint for human to solve
        try:
            from core.engine.breakpoints import get_breakpoint_manager, ApprovalMode
            manager = get_breakpoint_manager()

            execution_id = self.context.get('execution_id', 'manual')
            step_id = self.context.get('step_id', 'challenge')

            request = await manager.create_breakpoint(
                execution_id=execution_id,
                step_id=step_id,
                title=f"Challenge: {challenge_type}",
                description=f"Please solve the {challenge_type} challenge on {detection['url']}. "
                            f"The browser is waiting for you to complete the verification.",
                approval_mode=ApprovalMode.SINGLE,
                timeout_seconds=self.human_timeout or None,
                context_snapshot={
                    "challenge_type": challenge_type,
                    "url": detection['url'],
                    "screenshot_base64": screenshot_b64,
                },
            )

            # Wait for human to solve + approve
            result = await manager.wait_for_resolution(request.breakpoint_id)

            if result.approved:
                # Human solved it — verify page actually changed
                await asyncio.sleep(1)
                resolved = await page.evaluate(_CHECK_RESOLVED_JS)
                elapsed = round(time.monotonic() - t0, 1)

                if resolved:
                    logger.info("Challenge solved by human in %ss", elapsed)
                else:
                    # Human approved but page didn't change — might need retry.
                    logger.warning(
                        "Human approved the challenge breakpoint but the page "
                        "still reads as an interstitial after %ss", elapsed
                    )
                # `status` is deliberately the same on both branches: consumers
                # switch on it and narrowing it here would break them. What the
                # two branches disagree about -- whether the page actually
                # changed -- now travels in `page_changed` and in the rung,
                # instead of being lost.
                return {
                    "status": "human_resolved",
                    "challenge_type": challenge_type,
                    "wait_seconds": elapsed,
                    "required_human": True,
                    "page_changed": bool(resolved),
                    "outcome": _challenge_outcome(
                        challenge_type=challenge_type, resolved=bool(resolved),
                        route='human', wait_seconds=elapsed,
                    ),
                }
            else:
                elapsed = round(time.monotonic() - t0, 1)
                return {
                    "status": "timeout",
                    "challenge_type": challenge_type,
                    "wait_seconds": elapsed,
                    "required_human": True,
                    "page_changed": False,
                    "outcome": _challenge_outcome(
                        challenge_type=challenge_type, resolved=False,
                        route='human', wait_seconds=elapsed,
                    ),
                }

        except ImportError:
            # No breakpoint manager available — just wait and hope
            logger.warning("Breakpoint manager not available, waiting %ds...", self.human_timeout)
            for _ in range(min(self.human_timeout, 60)):
                await asyncio.sleep(1)
                resolved = await page.evaluate(_CHECK_RESOLVED_JS)
                if resolved:
                    break

            elapsed = round(time.monotonic() - t0, 1)
            return {
                "status": "human_resolved" if resolved else "timeout",
                "challenge_type": challenge_type,
                "wait_seconds": elapsed,
                "required_human": resolved,
                "page_changed": bool(resolved),
                "outcome": _challenge_outcome(
                    challenge_type=challenge_type, resolved=bool(resolved),
                    route='human', wait_seconds=elapsed,
                ),
            }


