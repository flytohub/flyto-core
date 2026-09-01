# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Login Module — Automated website authentication

Handles common login flows:
- Form-based login (username + password + submit)
- Auto-detect login form fields
- Wait for post-login redirect
- Verify login success
- Cookie persistence via persistent context

HOW FAR A LOGIN IS FOLLOWED

The module already computed a boolean called ``logged_in`` and returned it with
``status: "success"`` beside it, which is the shape this contract exists to
break up: one field that mixes "the step ran" with "the thing happened", and no
way to tell which of four different measurements produced it.

There are two real readings here and they are not the same kind of thing.

  ``page.url`` before and after the submit. A URL that moved is a change in the
  browser we did not write down ourselves -- it came from the page. That the
  move was caused by OUR submit is an inference of ours, so it travels as
  ``claim_by=inferred``.

  ``success_indicator`` -- a predicate the CALLER supplied. Either a CSS
  selector queried against the live DOM, or a fragment matched against the URL.
  This one is a contract: the caller said what "logged in" means here, so when
  it does not hold the answer is `failed` rather than `indeterminate`, exactly
  as `outcome.py` splits those two.

The caller's predicate is now read TWICE -- once before the form is filled and
once after -- and that read-before is the whole reason the rung can be trusted.
A ``success_indicator`` of ``/home`` on a page already at ``/home``, or a
``.dashboard`` element that was on the page the whole time, satisfies the
predicate without this step having done anything. Under the one rule this
contract runs on -- would this value be the same if the effect had not happened
-- a predicate that already held is not evidence, and it is reported as
`accepted` with the reason attached instead of as a green tick.

    caller's predicate holds, and did not hold before      OBSERVED (caller)
    caller's predicate holds, but held before too          OBSERVED if the URL
                                                           moved, else ACCEPTED
    caller's predicate does not hold                       FAILED (caller)
    no predicate declared, the URL moved                   OBSERVED (inferred)
    no predicate declared, the URL did not move            INDETERMINATE
    an MFA prompt appeared and nobody completed it         INDETERMINATE

VERIFIED is not claimed and no `postcondition=` is declared, even though this is
the one module in the browser group that evaluates a caller-supplied predicate
and so could reach for it. The predicate is too weak for the word: "an element
matching `.dashboard` exists" is satisfied by a login page that renders the
shell before authenticating, and `logged_in` is the single field a person reads
to decide whether an automation may proceed to spend money. `ceiling_for(None)`
therefore caps this module at OBSERVED, which is the right ceiling and not an
accident of the plumbing. The envelope's own ``postcondition`` field still names
the caller's predicate whenever one was given -- that field says which predicate
was EVALUATED, and dropping it would lose the only record of what the caller
meant by "logged in" -- while the metadata stays undeclared, which is what the
ratchet counts and what keeps VERIFIED out of reach.

The last URL-only case is INDETERMINATE rather than FAILED because a
single-page-application login changes no URL at all, and marking every correct
SPA login red would be the same defect in the other direction.
"""
import logging
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
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


def _indicator_is_a_url_pattern(indicator: str) -> bool:
    """The branch the module already used to decide how to read the indicator."""
    return indicator.startswith('/') or indicator.startswith('http')


async def _evaluate_success_indicator(page, indicator: str, url: str) -> Optional[bool]:
    """Whether the caller's predicate holds right now, or None if we could not ask.

    None is a third answer and not a false: a selector that raises leaves us
    unable to evaluate the contract at all, which is `indeterminate`, while a
    selector that matches nothing is the contract not holding, which is
    `failed`. Collapsing them would turn every malformed selector into a failed
    login.
    """
    if not indicator:
        return None
    if _indicator_is_a_url_pattern(indicator):
        return indicator in url
    try:
        return await page.query_selector(indicator) is not None
    except Exception:  # noqa: BLE001 - any failure means "cannot ask"
        return None


def _mfa_unresolved_outcome(*, url_changed: bool) -> Dict[str, Any]:
    """An MFA prompt appeared and nobody completed it inside the window.

    Not FAILED. The credentials may well have been accepted -- the prompt is
    what a site shows when they were -- and the session may be half-established.
    What we know is that we stopped waiting, which is the definition of the
    answer that is not a rung.
    """
    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[{
            'kind': 'mfa_prompt_unresolved',
            'url_changed': url_changed,
            'measured_by': 'a text and input-attribute scan of the page after the submit',
            'detail': (
                'The page looks like an MFA prompt and the breakpoint was not '
                'approved. The password may have been accepted -- that is when '
                'sites show this page -- so nothing here says the login failed, '
                'only that we stopped waiting.'
            ),
        }],
    )


def _login_outcome(
    *,
    url_before: str,
    url_after: str,
    indicator: str,
    indicator_before: Optional[bool],
    indicator_after: Optional[bool],
    mfa_detected: bool,
) -> Dict[str, Any]:
    """The rung this login attempt earned, and the readings that earned it."""
    url_changed = url_after != url_before
    effects: List[Dict[str, Any]] = [{
        'kind': 'page_url_moved' if url_changed else 'page_url_unchanged',
        'changed': url_changed,
        'measured_by': 'page.url, read before the form was filled and after the submit settled',
        'detail': (
            'The browser is showing a different address than it was before the '
            'credentials went in. That the submit caused it is our inference.'
        ) if url_changed else (
            'The browser is showing the same address it was before. A '
            'single-page-application login does exactly this, and so does a '
            'submit that went nowhere.'
        ),
    }]

    if mfa_detected:
        effects.append({
            'kind': 'mfa_prompt_completed',
            'measured_by': 'a text and input-attribute scan of the page after the submit',
            'detail': 'An MFA prompt was detected and a human approved the breakpoint.',
        })

    if not indicator:
        no_contract = {
            'kind': 'no_success_indicator_declared',
            'measured_by': None,
            'detail': (
                'The caller named nothing that would mean "logged in", so there '
                'is no contract to break and the URL reading is the only '
                'evidence there is.'
            ),
        }
        if url_changed:
            return envelope(
                Outcome.OBSERVED, claim_by=ClaimBy.INFERRED, effects=effects + [no_contract]
            )
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=effects + [no_contract, {
                'kind': 'nothing_observed_to_change',
                'predicate': 'page.url after the submit differs from page.url before it',
                'detail': (
                    'Nothing we can see moved. That reads the same whether the '
                    'credentials were rejected, the submit never fired, or the '
                    'site logged us in without navigating. We cannot say which.'
                ),
            }],
        )

    read_as = 'url fragment' if _indicator_is_a_url_pattern(indicator) else 'CSS selector'
    predicate = (
        f'success_indicator {indicator!r} appears in page.url after the login attempt'
        if read_as == 'url fragment' else
        f'an element matching success_indicator {indicator!r} is present after the login attempt'
    )
    contract = {
        'kind': 'success_indicator_evaluated',
        'read_as': read_as,
        'held_before': indicator_before,
        'held_after': indicator_after,
        'measured_by': (
            'the caller\'s success_indicator, matched against page.url before '
            'and after the login attempt'
            if read_as == 'url fragment' else
            'page.query_selector(success_indicator), run before and after the login attempt'
        ),
    }
    effects = effects + [contract]

    if indicator_after is None:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.CALLER,
            postcondition=predicate,
            effects=effects + [{
                'kind': 'success_indicator_not_evaluable',
                'detail': (
                    'The caller declared a contract and we could not evaluate '
                    'it -- the selector raised. Nothing here says the login '
                    'failed; it says we could not check.'
                ),
            }],
        )

    if indicator_after is False:
        return envelope(
            Outcome.FAILED,
            # CALLER: the caller said what "logged in" means here and it does
            # not hold. A contract was broken, which is failed and not
            # indeterminate -- see the two-axis argument in outcome.py.
            claim_by=ClaimBy.CALLER,
            postcondition=predicate,
            effects=effects + [{
                'kind': 'success_indicator_absent',
                'detail': (
                    'The thing the caller named as proof of a successful login '
                    'is not there after the attempt settled.'
                ),
            }],
        )

    if indicator_before is False:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.CALLER,
            postcondition=predicate,
            effects=effects + [{
                'kind': 'success_indicator_appeared',
                'detail': (
                    'It was not there before the credentials went in and it is '
                    'there now. The page gained the thing the caller named.'
                ),
            }],
        )

    already_there = {
        'kind': 'success_indicator_was_already_present',
        'detail': (
            'The caller\'s predicate holds, and it held before this step ran '
            'too -- an already-authenticated session, or a shell the site '
            'renders either way. That reading would be identical had this step '
            'done nothing, so on its own it is not evidence of a login.'
        ) if indicator_before else (
            'The caller\'s predicate holds now. Whether it held beforehand '
            'could not be evaluated, so it is not known to be evidence of this '
            'step.'
        ),
    }

    if url_changed:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.CALLER,
            postcondition=predicate,
            effects=effects + [already_there],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.CALLER,
        postcondition=predicate,
        effects=effects + [already_there],
    )


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
    can_connect_to=['browser.*', 'flow.*', 'ai.*', 'llm.*', 'agent.*'],
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
        'outcome':      {'type': 'object',  'description': (
            'How far this login was followed: observed when the page gained the '
            'caller\'s success_indicator or the URL moved, failed when a '
            'declared success_indicator is absent, accepted when the indicator '
            'was already satisfied before the attempt, indeterminate when '
            'nothing was declared and nothing moved.'
        )},
    },
    examples=[
        {'name': 'Auto-detect login form', 'params': {'username': 'team@flyto2.com', 'password': 'secret'}},
        {'name': 'With custom selectors', 'params': {'username': 'admin', 'password': 'pass', 'username_selector': '#user', 'password_selector': '#pass', 'submit_selector': '#login-btn'}},
    ],
    author='Flyto2 Team', license='MIT', timeout_ms=30000,
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

        # The caller's predicate, read BEFORE anything is typed. Without this
        # reading a `success_indicator` that was already satisfied -- a URL we
        # were already on, an element the site renders logged-in or not -- would
        # be reported as proof of a login that may never have happened.
        indicator_before = await _evaluate_success_indicator(
            page, self.success_indicator, url_before
        )

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
                        "url_changed": page.url != url_before,
                        "mfa_detected": True,
                        "fields_found": detection,
                        "outcome": _mfa_unresolved_outcome(
                            url_changed=page.url != url_before
                        ),
                    }

                # After user completed MFA, wait for navigation
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass
                url_after = page.url
                # Recomputed: `url_changed` was measured before the MFA
                # breakpoint, and the navigation that MFA completion causes
                # happens after it. Left stale, this field reported "the URL did
                # not change" on precisely the flows where it always does.
                url_changed = url_after != url_before
            except ImportError:
                logger.warning("Breakpoint manager unavailable, MFA cannot be completed automatically")

        # Step 6: Verify login
        logged_in = url_after != url_before  # Basic heuristic

        # The same predicate, read again now. `None` means it could not be
        # evaluated at all, in which case the heuristic above stands -- which is
        # what this module did before, kept deliberately so the rung is the only
        # thing that changed.
        indicator_after = await _evaluate_success_indicator(
            page, self.success_indicator, url_after
        )
        if self.success_indicator and indicator_after is not None:
            logged_in = indicator_after

        # Post-login: refresh hints for Element Picker (page likely changed)
        result = {
            "status": "success",
            "logged_in": logged_in,
            "url_after": url_after,
            "url_changed": url_changed,
            "mfa_detected": mfa_detected,
            "fields_found": detection,
            "outcome": _login_outcome(
                url_before=url_before,
                url_after=url_after,
                indicator=self.success_indicator,
                indicator_before=indicator_before,
                indicator_after=indicator_after,
                mfa_detected=mfa_detected,
            ),
        }
        browser._snapshot_since_nav = True
        hints = await browser.get_hints(force=True)
        for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
            if hints.get(key):
                result[key] = hints[key]
        return result
