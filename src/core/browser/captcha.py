# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Captcha Solver — API-based solving via 2Captcha or CapSolver

Supports:
- reCAPTCHA v2/v3
- hCaptcha
- Cloudflare Turnstile

Flow:
1. Detect captcha type + extract sitekey from page
2. Submit task to solving service
3. Poll until solved
4. Inject solution token + submit
"""
import asyncio
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Sitekey Extraction JS ────────────────────────────────────────

_EXTRACT_CAPTCHA_INFO_JS = r"""
() => {
    const info = { type: null, sitekey: null, action: null, url: window.location.href };

    // Cloudflare Turnstile (highest priority — most specific selector)
    const cfEl = document.querySelector('.cf-turnstile, [data-sitekey][data-callback]');
    if (cfEl) {
        info.type = 'turnstile';
        info.sitekey = cfEl.getAttribute('data-sitekey');
        return info;
    }

    // hCaptcha (check BEFORE reCAPTCHA — both use [data-sitekey],
    // but .h-captcha class and hcaptcha iframe are unambiguous)
    const hcapClass = document.querySelector('.h-captcha');
    const hcapIframe = document.querySelector('iframe[src*="hcaptcha.com"]');
    if (hcapClass || hcapIframe) {
        info.type = 'hcaptcha';
        if (hcapClass) info.sitekey = hcapClass.getAttribute('data-sitekey');
        return info;
    }

    // reCAPTCHA v3 (check before v2 — v3 is script-based, v2 is element-based)
    const recapScript = document.querySelector('script[src*="recaptcha/api.js"]');
    if (recapScript) {
        const src = recapScript.getAttribute('src');
        const match = src.match(/render=([^&]+)/);
        if (match && match[1] !== 'explicit') {
            info.type = 'recaptcha_v3';
            info.sitekey = match[1];
            info.action = 'verify';
            return info;
        }
    }

    // reCAPTCHA v2 (last — broadest selector)
    const recapV2 = document.querySelector('.g-recaptcha');
    if (recapV2) {
        info.type = 'recaptcha_v2';
        info.sitekey = recapV2.getAttribute('data-sitekey');
        return info;
    }

    return info;
}
"""

# ── Token Injection JS ──────────────────────────────────────────

_INJECT_TOKEN_JS = {
    'recaptcha_v2': r"""
        (token) => {
            // Set response textarea
            const textarea = document.getElementById('g-recaptcha-response');
            if (textarea) {
                textarea.style.display = 'block';
                textarea.value = token;
            }
            // Call callback if exists
            const widget = document.querySelector('.g-recaptcha');
            if (widget) {
                const cb = widget.getAttribute('data-callback');
                if (cb && typeof window[cb] === 'function') {
                    window[cb](token);
                    return { injected: true, callback: cb };
                }
            }
            // Try submitting the form
            const form = document.querySelector('form');
            if (form) {
                form.submit();
                return { injected: true, callback: 'form_submit' };
            }
            return { injected: !!textarea, callback: null };
        }
    """,
    'recaptcha_v3': r"""
        (token) => {
            const textarea = document.getElementById('g-recaptcha-response');
            if (textarea) textarea.value = token;
            // v3 usually auto-submits via callback
            if (typeof ___grecaptcha_cfg !== 'undefined') {
                const clients = ___grecaptcha_cfg.clients;
                for (const cid in clients) {
                    const client = clients[cid];
                    for (const key in client) {
                        const widget = client[key];
                        if (widget && widget.callback) {
                            widget.callback(token);
                            return { injected: true, callback: 'v3_callback' };
                        }
                    }
                }
            }
            return { injected: !!textarea, callback: null };
        }
    """,
    'hcaptcha': r"""
        (token) => {
            const textarea = document.querySelector('[name="h-captcha-response"], [name="g-recaptcha-response"]');
            if (textarea) textarea.value = token;
            const iframe = document.querySelector('iframe[src*="hcaptcha"]');
            if (iframe) {
                const widget = document.querySelector('.h-captcha');
                if (widget) {
                    const cb = widget.getAttribute('data-callback');
                    if (cb && typeof window[cb] === 'function') {
                        window[cb](token);
                        return { injected: true, callback: cb };
                    }
                }
            }
            const form = document.querySelector('form');
            if (form) { form.submit(); return { injected: true, callback: 'form_submit' }; }
            return { injected: !!textarea, callback: null };
        }
    """,
    'turnstile': r"""
        (token) => {
            const input = document.querySelector('[name="cf-turnstile-response"]');
            if (input) input.value = token;
            // Turnstile callback
            if (typeof turnstile !== 'undefined' && turnstile.getResponse) {
                // Can't set directly, but try form submit
            }
            const form = document.querySelector('#challenge-form, form');
            if (form) { form.submit(); return { injected: true, callback: 'form_submit' }; }
            return { injected: !!input, callback: null };
        }
    """,
}


class CaptchaSolver:
    """API-based captcha solver supporting 2Captcha and CapSolver."""

    PROVIDERS = ('2captcha', 'capsolver')

    def __init__(self, provider: str, api_key: str):
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Use: {self.PROVIDERS}")
        if not api_key:
            raise ValueError("api_key is required")
        self.provider = provider
        self.api_key = api_key
        self._stats = {'solved': 0, 'failed': 0, 'total_time': 0.0}

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    async def detect(self, page) -> Dict[str, Any]:
        """Detect captcha type and extract sitekey from page."""
        try:
            return await page.evaluate(_EXTRACT_CAPTCHA_INFO_JS)
        except Exception as e:
            logger.warning(f"Captcha detection failed: {e}")
            return {'type': None, 'sitekey': None, 'url': None}

    async def solve(self, page, captcha_info: Optional[Dict] = None) -> Dict[str, Any]:
        """Detect, solve, and inject captcha solution.

        Args:
            page: Playwright page
            captcha_info: Pre-detected captcha info (optional, will detect if not given)

        Returns:
            Dict with status, type, solve_time, etc.
        """
        import time

        if captcha_info is None:
            captcha_info = await self.detect(page)

        captcha_type = captcha_info.get('type')
        sitekey = captcha_info.get('sitekey')
        page_url = captcha_info.get('url', page.url)

        if not captcha_type:
            return {'status': 'no_captcha', 'type': None, 'solve_time': 0}

        if not sitekey:
            return {'status': 'error', 'type': captcha_type,
                    'error': 'Could not extract sitekey', 'solve_time': 0}

        logger.info(f"Solving {captcha_type} (sitekey={sitekey[:16]}...) via {self.provider}")
        t0 = time.monotonic()

        try:
            # Submit task to solving service
            task_id = await self._submit_task(captcha_type, sitekey, page_url)
            if not task_id:
                self._stats['failed'] += 1
                return {'status': 'error', 'type': captcha_type,
                        'error': 'Failed to submit task', 'solve_time': 0}

            # Poll for solution
            token = await self._poll_result(task_id)
            if not token:
                self._stats['failed'] += 1
                return {'status': 'error', 'type': captcha_type,
                        'error': 'Solve timed out', 'solve_time': round(time.monotonic() - t0, 1)}

            # Inject solution
            inject_js = _INJECT_TOKEN_JS.get(captcha_type)
            if inject_js:
                result = await page.evaluate(inject_js, token)
                logger.info(f"Token injected: {result}")
            else:
                logger.warning(f"No injection JS for type: {captcha_type}")

            solve_time = round(time.monotonic() - t0, 1)
            self._stats['solved'] += 1
            self._stats['total_time'] += solve_time

            # Wait for page to process the token
            await asyncio.sleep(2)

            return {
                'status': 'solved',
                'type': captcha_type,
                'solve_time': solve_time,
                'provider': self.provider,
            }

        except Exception as e:
            self._stats['failed'] += 1
            solve_time = round(time.monotonic() - t0, 1)
            logger.error(f"Captcha solve failed: {e}")
            return {'status': 'error', 'type': captcha_type,
                    'error': str(e), 'solve_time': solve_time}

    # ── Provider APIs ────────────────────────────────────────────

    async def _submit_task(self, captcha_type: str, sitekey: str, page_url: str) -> Optional[str]:
        if self.provider == '2captcha':
            return await self._submit_2captcha(captcha_type, sitekey, page_url)
        elif self.provider == 'capsolver':
            return await self._submit_capsolver(captcha_type, sitekey, page_url)
        return None

    async def _poll_result(self, task_id: str) -> Optional[str]:
        if self.provider == '2captcha':
            return await self._poll_2captcha(task_id)
        elif self.provider == 'capsolver':
            return await self._poll_capsolver(task_id)
        return None

    # ── 2Captcha ─────────────────────────────────────────────────

    async def _submit_2captcha(self, captcha_type, sitekey, page_url) -> Optional[str]:
        params = {
            'key': self.api_key,
            'method': 'userrecaptcha',
            'googlekey': sitekey,
            'pageurl': page_url,
            'json': '1',
        }

        if captcha_type == 'hcaptcha':
            params['method'] = 'hcaptcha'
            params['sitekey'] = sitekey
            del params['googlekey']
        elif captcha_type == 'turnstile':
            params['method'] = 'turnstile'
            params['sitekey'] = sitekey
            del params['googlekey']
        elif captcha_type == 'recaptcha_v3':
            params['version'] = 'v3'
            params['action'] = 'verify'
            params['min_score'] = '0.3'

        # Use POST to avoid leaking API key in URL/access logs
        resp = await asyncio.to_thread(
            self._http_post,
            'https://2captcha.com/in.php',
            params,
        )
        if resp and resp.get('status') == 1:
            return resp.get('request')
        logger.error(f"2Captcha submit failed: status={resp.get('status') if resp else None}")
        return None

    async def _poll_2captcha(self, task_id: str, timeout: int = 120) -> Optional[str]:
        # Use POST to avoid leaking API key in URL/access logs
        params = {
            'key': self.api_key,
            'action': 'get',
            'id': task_id,
            'json': '1',
        }
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            resp = await asyncio.to_thread(
                self._http_post,
                'https://2captcha.com/res.php',
                params,
            )
            if resp and resp.get('status') == 1:
                return resp.get('request')
            if resp and 'ERROR' in str(resp.get('request', '')):
                logger.error(f"2Captcha error: {resp.get('request')}")
                return None
        return None

    # ── CapSolver ────────────────────────────────────────────────

    async def _submit_capsolver(self, captcha_type, sitekey, page_url) -> Optional[str]:
        type_map = {
            'recaptcha_v2': 'ReCaptchaV2TaskProxyLess',
            'recaptcha_v3': 'ReCaptchaV3TaskProxyLess',
            'hcaptcha': 'HCaptchaTaskProxyLess',
            'turnstile': 'AntiTurnstileTaskProxyLess',
        }

        task_type = type_map.get(captcha_type, 'ReCaptchaV2TaskProxyLess')
        payload = {
            'clientKey': self.api_key,
            'task': {
                'type': task_type,
                'websiteURL': page_url,
                'websiteKey': sitekey,
            },
        }

        if captcha_type == 'recaptcha_v3':
            payload['task']['pageAction'] = 'verify'
            payload['task']['minScore'] = 0.3

        resp = await asyncio.to_thread(
            self._http_post,
            'https://api.capsolver.com/createTask',
            payload,
        )
        if resp and resp.get('errorId') == 0:
            return resp.get('taskId')
        logger.error(f"CapSolver submit failed: {resp}")
        return None

    async def _poll_capsolver(self, task_id: str, timeout: int = 120) -> Optional[str]:
        payload = {
            'clientKey': self.api_key,
            'taskId': task_id,
        }
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            resp = await asyncio.to_thread(
                self._http_post,
                'https://api.capsolver.com/getTaskResult',
                payload,
            )
            if resp and resp.get('status') == 'ready':
                solution = resp.get('solution', {})
                return (
                    solution.get('gRecaptchaResponse')
                    or solution.get('token')
                    or solution.get('text')
                )
            if resp and resp.get('errorId', 0) != 0:
                logger.error(f"CapSolver error: {resp}")
                return None
        return None

    # ── HTTP Helpers ─────────────────────────────────────────────

    @staticmethod
    def _http_get(url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Flyto/1.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"HTTP GET failed: {e}")
            return None

    @staticmethod
    def _http_post(url: str, payload: dict, form_encoded: bool = False) -> Optional[dict]:
        try:
            if form_encoded or 'clientKey' not in payload:
                # Form-encoded for 2Captcha API
                data = urllib.parse.urlencode(payload).encode()
                content_type = 'application/x-www-form-urlencoded'
            else:
                # JSON for CapSolver API
                data = json.dumps(payload).encode()
                content_type = 'application/json'
            req = urllib.request.Request(
                url, data=data,
                headers={'Content-Type': content_type, 'User-Agent': 'Flyto/1.0'},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error(f"HTTP POST failed: {e}")
            return None
