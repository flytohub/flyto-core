# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Login Module — Automated website authentication

Handles common login flows:
- Form-based login (username + password + submit)
- Auto-detect login form fields
- Wait for post-login redirect
- Verify login success
- Cookie persistence via persistent context
"""
import logging
from typing import Any
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)

_LOGIN_JS = r"""
async (options) => {
    const username = options.username || '';
    const password = options.password || '';
    const submitSelector = options.submit_selector || '';
    const usernameSelector = options.username_selector || '';
    const passwordSelector = options.password_selector || '';
    const successIndicator = options.success_indicator || '';
    const waitMs = options.wait_ms || 3000;

    // ── Auto-detect form fields ──
    function findField(hints) {
        for (const hint of hints) {
            const el = document.querySelector(hint);
            if (el && el.offsetParent !== null) return el;  // visible
        }
        return null;
    }

    const usernameField = usernameSelector
        ? document.querySelector(usernameSelector)
        : findField([
            'input[name="username"]', 'input[name="email"]', 'input[name="login"]',
            'input[name="user"]', 'input[name="userid"]', 'input[name="account"]',
            'input[type="email"]',
            'input[autocomplete="username"]', 'input[autocomplete="email"]',
            'input[id*="user" i]', 'input[id*="email" i]', 'input[id*="login" i]',
            'input[placeholder*="email" i]', 'input[placeholder*="user" i]',
          ]);

    const passwordField = passwordSelector
        ? document.querySelector(passwordSelector)
        : findField([
            'input[type="password"]',
            'input[name="password"]', 'input[name="pass"]', 'input[name="passwd"]',
            'input[autocomplete="current-password"]',
          ]);

    const submitButton = submitSelector
        ? document.querySelector(submitSelector)
        : findField([
            'button[type="submit"]', 'input[type="submit"]',
            'button:has(> span)', // React-style buttons
            'form button', 'form [role="button"]',
            'button[class*="login" i]', 'button[class*="sign" i]', 'button[class*="submit" i]',
            '[data-testid*="login" i]', '[data-testid*="submit" i]',
          ]);

    return {
        username_found: !!usernameField,
        password_found: !!passwordField,
        submit_found: !!submitButton,
        username_selector: usernameField ? (usernameField.id ? '#' + usernameField.id : usernameField.name ? `[name="${usernameField.name}"]` : '') : '',
        password_selector: passwordField ? (passwordField.id ? '#' + passwordField.id : passwordField.name ? `[name="${passwordField.name}"]` : '') : '',
        submit_selector: submitButton ? (submitButton.id ? '#' + submitButton.id : submitButton.textContent?.trim()?.substring(0, 30) || '') : '',
    };
}
"""


@register_module(
    module_id='browser.login',
    version='1.0.0',
    category='browser',
    tags=['browser', 'auth', 'login', 'session', 'form'],
    label='Login',
    label_key='modules.browser.login.label',
    description='Auto-detect and fill login forms. Handles username + password + submit with post-login verification.',
    description_key='modules.browser.login.description',
    icon='LogIn',
    color='#0EA5E9',
    input_types=['page'],
    output_types=['page'],
    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*'],
    params_schema=compose(
        field('username', type='string', label='Username / Email',
              description='Login username or email.',
              required=True, format='email',
              group='basic'),
        field('password', type='string', label='Password',
              description='Login password.',
              required=True, format='password',
              group='basic'),
        field('success_indicator', type='string', label='Success indicator',
              description='CSS selector or URL pattern to verify login succeeded. Leave empty for auto-detect (URL change).',
              required=False, default='',
              placeholder='.dashboard, /home',
              group='basic'),
        field('username_selector', type='string', label='Username field selector',
              description='CSS selector for username input. Leave empty for auto-detect.',
              required=False, default='',
              group='advanced'),
        field('password_selector', type='string', label='Password field selector',
              description='CSS selector for password input. Leave empty for auto-detect.',
              required=False, default='',
              group='advanced'),
        field('submit_selector', type='string', label='Submit button selector',
              description='CSS selector for submit button. Leave empty for auto-detect.',
              required=False, default='',
              group='advanced'),
        field('wait_ms', type='number', label='Wait after submit (ms)',
              description='Wait for redirect/page load after clicking submit.',
              default=5000, min=1000, max=30000, step=1000,
              group='advanced'),
    ),
    output_schema={
        'logged_in':    {'type': 'boolean', 'description': 'Whether login appears successful'},
        'url_after':    {'type': 'string',  'description': 'URL after login attempt'},
        'url_changed':  {'type': 'boolean', 'description': 'Whether URL changed after login'},
        'fields_found': {'type': 'object',  'description': 'Which form fields were auto-detected'},
    },
    examples=[
        {'name': 'Auto-detect login form', 'params': {'username': 'user@example.com', 'password': 'secret'}},
        {'name': 'With custom selectors', 'params': {'username': 'admin', 'password': 'pass', 'username_selector': '#user', 'password_selector': '#pass', 'submit_selector': '#login-btn'}},
    ],
    author='Flyto Team', license='MIT', timeout_ms=30000,
    required_permissions=["browser.read", "browser.write"],
)
class BrowserLoginModule(BaseModule):
    module_name = "Login"
    required_permission = "browser.write"

    def validate_params(self) -> None:
        if not self.params.get('username'):
            raise ValueError("username is required")
        if not self.params.get('password'):
            raise ValueError("password is required")
        self.username = self.params['username']
        self.password = self.params['password']
        self.success_indicator = self.params.get('success_indicator', '')
        self.username_selector = self.params.get('username_selector', '')
        self.password_selector = self.params.get('password_selector', '')
        self.submit_selector = self.params.get('submit_selector', '')
        self.wait_ms = self.params.get('wait_ms', 5000)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        url_before = page.url

        # Step 1: Detect form fields
        detection = await page.evaluate(_LOGIN_JS, {
            'username_selector': self.username_selector,
            'password_selector': self.password_selector,
            'submit_selector': self.submit_selector,
        })

        # Resolve selectors
        user_sel = self.username_selector or detection.get('username_selector', '')
        pass_sel = self.password_selector or detection.get('password_selector', '')

        if not detection['username_found']:
            raise RuntimeError("Could not find username/email input field on page")
        if not detection['password_found']:
            raise RuntimeError("Could not find password input field on page")

        # Step 2: Fill form
        if user_sel:
            await page.fill(user_sel, self.username)
        else:
            # Fallback: click and type into the detected field
            await page.evaluate("""(username) => {
                const fields = ['input[name="username"]','input[name="email"]','input[type="email"]','input[autocomplete="username"]'];
                for (const s of fields) { const f = document.querySelector(s); if (f) { f.focus(); f.value = username; f.dispatchEvent(new Event('input', {bubbles:true})); break; } }
            }""", self.username)

        if pass_sel:
            await page.fill(pass_sel, self.password)
        else:
            await page.fill('input[type="password"]', self.password)

        # Step 3: Submit
        submit_sel = self.submit_selector
        if not submit_sel and detection['submit_found']:
            # Use auto-detected submit
            submit_sel = 'button[type="submit"], input[type="submit"], form button'

        if submit_sel:
            try:
                await page.click(submit_sel, timeout=5000)
            except Exception:
                # Fallback: press Enter
                await page.press('input[type="password"]', 'Enter')
        else:
            await page.press('input[type="password"]', 'Enter')

        # Step 4: Wait for navigation
        try:
            await page.wait_for_load_state('networkidle', timeout=self.wait_ms)
        except Exception:
            await page.wait_for_timeout(min(self.wait_ms, 3000))

        # Step 5: Detect MFA / 2FA prompt
        url_after = page.url
        url_changed = url_after != url_before

        mfa_detected = await page.evaluate(r"""() => {
            const text = document.body?.innerText?.toLowerCase() || '';

            // Exclude password reset / email verification contexts
            const isResetFlow = /(?:reset.*password|forgot.*password|password.*reset|create.*password|new.*password)/i.test(text);
            if (isResetFlow) return false;

            // MFA-specific input fields (strict: otp, 2fa, mfa, totp, one-time-code)
            const mfaInputs = document.querySelectorAll(
                'input[name*="otp" i], input[name*="2fa" i], input[name*="mfa" i], '
                + 'input[name*="totp" i], input[autocomplete="one-time-code"], '
                + 'input[inputmode="numeric"][maxlength="6"], input[inputmode="numeric"][maxlength="4"]'
            );
            if (mfaInputs.length > 0) return true;

            // Text-based detection (strict patterns only)
            const hasMfaText = /(?:two.?factor|2.?step|authenticator app|security key|one.?time.*(?:password|code|token)|enter.*(?:verification|otp|2fa|mfa).*code)/i.test(text);
            return hasMfaText;
        }""")

        if mfa_detected:
            logger.info("MFA/2FA prompt detected, requesting user interaction")
            # Fall back to breakpoint so user can complete MFA manually
            try:
                from ....engine.breakpoints import get_breakpoint_manager, ApprovalMode
                manager = get_breakpoint_manager()

                screenshot_b64 = ''
                try:
                    import base64
                    raw = await page.screenshot(type='jpeg', quality=60)
                    screenshot_b64 = base64.b64encode(raw).decode('ascii')
                except Exception:
                    pass

                request = await manager.create_breakpoint(
                    execution_id=self.context.get('execution_id', 'unknown'),
                    step_id=self.context.get('step_id', 'unknown'),
                    workflow_id=self.context.get('workflow_id'),
                    title='MFA / 2FA Required',
                    description='Please complete the verification in the browser, then click Approve.',
                    required_approvers=[],
                    approval_mode=ApprovalMode.FIRST,
                    timeout_seconds=300,  # 5 minutes for user to complete MFA
                    context_snapshot={
                        'url': url_after,
                        'screenshot_base64': screenshot_b64,
                        'screenshot_media_type': 'image/jpeg',
                        'mfa_detected': True,
                    },
                    custom_fields=[],
                    metadata={'step_name': self.context.get('step_name'), 'mfa': True},
                )
                result = await manager.wait_for_resolution(request.breakpoint_id, check_timeout=True)

                from ....engine.breakpoints import BreakpointStatus
                if result.status != BreakpointStatus.APPROVED:
                    return {
                        "status": "mfa_timeout",
                        "logged_in": False,
                        "url_after": page.url,
                        "url_changed": url_changed,
                        "mfa_detected": True,
                        "fields_found": detection,
                    }

                # After user completed MFA, wait for navigation
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass
                url_after = page.url
            except ImportError:
                logger.warning("Breakpoint manager unavailable, MFA cannot be completed automatically")

        # Step 6: Verify login
        logged_in = url_after != url_before  # Basic heuristic

        if self.success_indicator:
            if self.success_indicator.startswith('/') or self.success_indicator.startswith('http'):
                logged_in = self.success_indicator in url_after
            else:
                try:
                    el = await page.query_selector(self.success_indicator)
                    logged_in = el is not None
                except Exception:
                    pass

        # Post-login: refresh hints for Element Picker (page likely changed)
        result = {
            "status": "success",
            "logged_in": logged_in,
            "url_after": url_after,
            "url_changed": url_changed,
            "mfa_detected": mfa_detected,
            "fields_found": detection,
        }
        browser._snapshot_since_nav = True
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
