"""
Browser Login Module - Generic login flow handler

Handles common login patterns including:
- Username/password forms
- Wait for success indicator
- Handle login errors
- Support for "remember me" checkbox
- Two-factor authentication detection
"""
from typing import Any, Dict, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


@register_module(
    module_id='browser.login',
    version='1.0.0',
    category='browser',
    tags=['browser', 'login', 'auth', 'automation', 'ssrf_protected'],
    label='Login',
    label_key='modules.browser.login.label',
    description='Handle common login flows with success/failure detection',
    description_key='modules.browser.login.description',
    icon='LogIn',
    color='#10B981',

    input_types=['page'],
    output_types=['page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'flow.*'],

    params_schema=compose(
        field(
            'username',
            type='string',
            label='Username/Email',
            label_key='modules.browser.login.params.username.label',
            description='Username or email to login with',
            required=True,
            placeholder='username',
        ),
        field(
            'password',
            type='string',
            label='Password',
            label_key='modules.browser.login.params.password.label',
            description='Password for login',
            required=True,
            format='password',
            placeholder='********',
        ),
        field(
            'username_selector',
            type='string',
            label='Username Selector',
            label_key='modules.browser.login.params.username_selector.label',
            description='CSS selector for username/email field',
            placeholder='input[name="email"], #username',
            required=False,
        ),
        field(
            'password_selector',
            type='string',
            label='Password Selector',
            label_key='modules.browser.login.params.password_selector.label',
            description='CSS selector for password field',
            placeholder='input[type="password"], #password',
            required=False,
        ),
        field(
            'submit_selector',
            type='string',
            label='Submit Selector',
            label_key='modules.browser.login.params.submit_selector.label',
            description='CSS selector for submit button',
            placeholder='button[type="submit"], .login-btn',
            required=False,
        ),
        field(
            'success_selector',
            type='string',
            label='Success Indicator',
            label_key='modules.browser.login.params.success_selector.label',
            description='CSS selector that appears on successful login',
            placeholder='.dashboard, .user-menu, #logged-in',
            required=False,
        ),
        field(
            'error_selector',
            type='string',
            label='Error Indicator',
            label_key='modules.browser.login.params.error_selector.label',
            description='CSS selector for login error messages',
            placeholder='.error-message, .alert-danger',
            required=False,
        ),
        field(
            'remember_me',
            type='boolean',
            label='Remember Me',
            label_key='modules.browser.login.params.remember_me.label',
            description='Check "remember me" checkbox if present',
            default=False,
        ),
        field(
            'remember_me_selector',
            type='string',
            label='Remember Me Selector',
            label_key='modules.browser.login.params.remember_me_selector.label',
            description='CSS selector for remember me checkbox',
            placeholder='input[name="remember"], #remember-me',
            required=False,
        ),
        field(
            'timeout_ms',
            type='integer',
            label='Timeout (ms)',
            label_key='modules.browser.login.params.timeout_ms.label',
            description='Maximum time to wait for login result',
            default=30000,
            min=5000,
            max=120000,
        ),
        field(
            'delay_before_submit_ms',
            type='integer',
            label='Delay Before Submit (ms)',
            label_key='modules.browser.login.params.delay_before_submit_ms.label',
            description='Wait time before clicking submit (for page to settle)',
            default=500,
            min=0,
            max=5000,
        ),
    ),
    output_schema={
        'success': {
            'type': 'boolean',
            'description': 'Whether login was successful',
            'description_key': 'modules.browser.login.output.success.description'
        },
        'error_message': {
            'type': 'string',
            'description': 'Error message if login failed',
            'description_key': 'modules.browser.login.output.error_message.description'
        },
        'requires_2fa': {
            'type': 'boolean',
            'description': 'Whether 2FA is required',
            'description_key': 'modules.browser.login.output.requires_2fa.description'
        },
        'redirect_url': {
            'type': 'string',
            'description': 'URL after login attempt',
            'description_key': 'modules.browser.login.output.redirect_url.description'
        }
    },
    examples=[
        {
            'name': 'Basic login',
            'params': {
                'username': 'user@example.com',
                'password': '${secrets.PASSWORD}',
                'success_selector': '.dashboard'
            }
        },
        {
            'name': 'Login with custom selectors',
            'params': {
                'username': 'john_doe',
                'password': '${secrets.PASSWORD}',
                'username_selector': '#login-email',
                'password_selector': '#login-password',
                'submit_selector': '#login-button',
                'success_selector': '.user-profile',
                'error_selector': '.login-error'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=60000,
    required_permissions=['browser.automation'],
    handles_sensitive_data=True,
)
class BrowserLoginModule(BaseModule):
    """
    Generic login flow handler.

    Handles common login patterns with automatic field detection
    and success/failure verification.
    """

    module_name = "Login"
    module_description = "Handle common login flows"
    required_permission = "browser.automation"

    # Common selectors for auto-detection
    USERNAME_SELECTORS = [
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[name="user"]',
        'input[name="login"]',
        'input[id="email"]',
        'input[id="username"]',
        '#email',
        '#username',
    ]

    PASSWORD_SELECTORS = [
        'input[type="password"]',
        'input[name="password"]',
        'input[name="pass"]',
        '#password',
    ]

    SUBMIT_SELECTORS = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button.login',
        'button.signin',
        '.login-button',
        '.submit-button',
    ]

    TWO_FA_INDICATORS = [
        'input[name="otp"]',
        'input[name="code"]',
        'input[name="2fa"]',
        '.two-factor',
        '.mfa-input',
        '#verification-code',
    ]

    def validate_params(self) -> None:
        self.username = self.params.get('username')
        self.password = self.params.get('password')
        self.username_selector = self.params.get('username_selector')
        self.password_selector = self.params.get('password_selector')
        self.submit_selector = self.params.get('submit_selector')
        self.success_selector = self.params.get('success_selector')
        self.error_selector = self.params.get('error_selector')
        self.remember_me = self.params.get('remember_me', False)
        self.remember_me_selector = self.params.get('remember_me_selector')
        self.timeout_ms = self.params.get('timeout_ms', 30000)
        self.delay_before_submit_ms = self.params.get('delay_before_submit_ms', 500)

        if not self.username:
            raise ValueError("username is required")
        if not self.password:
            raise ValueError("password is required")

    async def execute(self) -> Dict[str, Any]:
        import asyncio

        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        try:
            # Find and fill username field
            username_sel = await self._find_selector(
                browser,
                self.username_selector,
                self.USERNAME_SELECTORS,
                'username'
            )
            await browser.type(username_sel, self.username)

            # Find and fill password field
            password_sel = await self._find_selector(
                browser,
                self.password_selector,
                self.PASSWORD_SELECTORS,
                'password'
            )
            await browser.type(password_sel, self.password)

            # Handle remember me checkbox
            if self.remember_me:
                await self._check_remember_me(browser)

            # Wait before submit
            if self.delay_before_submit_ms > 0:
                await asyncio.sleep(self.delay_before_submit_ms / 1000)

            # Click submit
            submit_sel = await self._find_selector(
                browser,
                self.submit_selector,
                self.SUBMIT_SELECTORS,
                'submit'
            )
            await browser.click(submit_sel)

            # Wait for result
            result = await self._wait_for_result(browser)

            return {
                'ok': True,
                'data': result
            }

        except Exception as e:
            return {
                'ok': False,
                'error': str(e),
                'data': {
                    'success': False,
                    'error_message': str(e),
                    'requires_2fa': False,
                    'redirect_url': None
                }
            }

    async def _find_selector(
        self,
        browser,
        custom_selector: Optional[str],
        fallback_selectors: list,
        field_name: str
    ) -> str:
        """Find working selector for a field."""
        if custom_selector:
            return custom_selector

        for selector in fallback_selectors:
            exists = await browser.evaluate(f'''
                document.querySelector("{selector}") !== null
            ''')
            if exists:
                return selector

        raise ValueError(f"Could not find {field_name} field. Please specify a custom selector.")

    async def _check_remember_me(self, browser) -> None:
        """Check the remember me checkbox if present."""
        selectors = [
            self.remember_me_selector,
            'input[name="remember"]',
            'input[name="remember_me"]',
            'input[type="checkbox"][id*="remember"]',
            '#remember-me',
        ]

        for selector in selectors:
            if not selector:
                continue
            try:
                exists = await browser.evaluate(f'''
                    document.querySelector("{selector}") !== null
                ''')
                if exists:
                    await browser.evaluate(f'''
                        const cb = document.querySelector("{selector}");
                        if (cb && !cb.checked) cb.click();
                    ''')
                    return
            except Exception:
                continue

    async def _wait_for_result(self, browser) -> Dict[str, Any]:
        """Wait for login result (success, error, or 2FA)."""
        import asyncio

        start_time = asyncio.get_event_loop().time()
        timeout_s = self.timeout_ms / 1000

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_s:
                return {
                    'success': False,
                    'error_message': 'Login timeout',
                    'requires_2fa': False,
                    'redirect_url': await browser.evaluate('window.location.href')
                }

            # Check for success indicator
            if self.success_selector:
                success = await browser.evaluate(f'''
                    document.querySelector("{self.success_selector}") !== null
                ''')
                if success:
                    return {
                        'success': True,
                        'error_message': None,
                        'requires_2fa': False,
                        'redirect_url': await browser.evaluate('window.location.href')
                    }

            # Check for error indicator
            if self.error_selector:
                error_el = await browser.evaluate(f'''
                    (() => {{
                        const el = document.querySelector("{self.error_selector}");
                        return el ? el.textContent.trim() : null;
                    }})()
                ''')
                if error_el:
                    return {
                        'success': False,
                        'error_message': error_el,
                        'requires_2fa': False,
                        'redirect_url': await browser.evaluate('window.location.href')
                    }

            # Check for 2FA
            for tfa_selector in self.TWO_FA_INDICATORS:
                tfa_present = await browser.evaluate(f'''
                    document.querySelector("{tfa_selector}") !== null
                ''')
                if tfa_present:
                    return {
                        'success': False,
                        'error_message': 'Two-factor authentication required',
                        'requires_2fa': True,
                        'redirect_url': await browser.evaluate('window.location.href')
                    }

            await asyncio.sleep(0.5)
