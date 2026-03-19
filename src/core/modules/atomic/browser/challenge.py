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
"""
import logging
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup

logger = logging.getLogger(__name__)

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
    can_connect_to=['browser.*', 'flow.*', 'data.*'],

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
              ],
              group='basic'),
        field('captcha_api_key', type='string',
              label='Captcha API Key',
              description='API key for the captcha solving service',
              format='password',
              required=False,
              showIf={"captcha_provider": {"$in": ["2captcha", "capsolver"]}},
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
    },
    examples=[
        {'name': 'Default (15s auto-wait, then ask human)', 'params': {}},
        {'name': 'Skip auto-wait, always ask human', 'params': {'auto_wait_seconds': 0, 'human_fallback': True}},
        {'name': 'Auto-only, no human fallback', 'params': {'auto_wait_seconds': 30, 'human_fallback': False}},
    ],
    author='Flyto Team',
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
                    return {
                        "status": "human_resolved",
                        "challenge_type": challenge_type,
                        "wait_seconds": elapsed,
                        "required_human": True,
                    }
                else:
                    # Human approved but page didn't change — might need retry
                    return {
                        "status": "human_resolved",
                        "challenge_type": challenge_type,
                        "wait_seconds": elapsed,
                        "required_human": True,
                    }
            else:
                elapsed = round(time.monotonic() - t0, 1)
                return {
                    "status": "timeout",
                    "challenge_type": challenge_type,
                    "wait_seconds": elapsed,
                    "required_human": True,
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
            }


