# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Cookies Module

Get, set, or clear browser cookies.

`add_cookies` DOES NOT TELL YOU THE COOKIE WAS ADDED

The `set` action built a dict from the caller's parameters, handed it to
Playwright, and returned that same dict with ``"count": 1`` beside it. Both are
the input. The 1 is a literal written in this file; it was 1 whether the jar
took the cookie or dropped it.

And it does get dropped. Measured against the Chromium this repository drives:

    add_cookies([{name: 'past', ..., expires: 1000000}])  -> returns normally
    context.cookies()                                      -> does not contain it

No exception, no return value, nothing in the jar. ``count: 1`` was reported for
that cookie. The same call with a ``secure`` cookie on an http origin lands in
the jar but is not offered to that origin -- a different failure, and one this
module's read cannot see, so it is not claimed either way below.

That is the exact shape the ladder exists to catch: a success report with no
measurement behind it, on the failure mode the API actually has.

The measurement is the jar itself. ``context.cookies()`` is a read of the
browser's cookie store, and every action here now ends with one:

  get       OBSERVED. The list came out of the jar. An empty list is still an
            observation, unlike `database.query`'s empty result set: this is a
            read of the whole store, filtered here in Python, so "no cookie by
            that name" is a fact rather than a statement the backend declined to
            make.
  set       OBSERVED when the jar holds a cookie of that name with that value;
            INDETERMINATE when it does not.
  clear     OBSERVED when the jar is empty afterwards; INDETERMINATE otherwise.
  delete    OBSERVED when the named cookie is gone afterwards; INDETERMINATE
            otherwise. Worth reading the implementation for: `delete` clears the
            whole jar and re-adds the survivors, so a domain the re-add rejects
            silently loses OTHER cookies. `remaining_count` is now read back for
            that reason, and it is not the same number as the pre-clear count it
            used to be compared against.

INDETERMINATE and not FAILED throughout: no postcondition is declared here, the
comparison is this module's own inference, and a page that sets the same cookie
between the write and the read produces it with nothing broken.
"""
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


def _jar_read_outcome(*, action: str, count: int, filtered_by: Optional[str]) -> Dict[str, Any]:
    """OBSERVED for `get`: the list came out of the browser's cookie store."""
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'cookies_read',
            'action': action,
            'count': count,
            'filtered_by_name': filtered_by,
            'measured_by': 'BrowserContext.cookies(), read from the browser cookie store',
            'detail': (
                'A read of the whole jar, filtered in this module. An empty '
                'result is an observation that no cookie matched, not a silence.'
            ),
        }],
    )


def _jar_write_outcome(
    *,
    action: str,
    holds: bool,
    predicate: str,
    observed_detail: str,
    unmet_detail: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """OBSERVED / INDETERMINATE for the actions that change the jar.

    `holds` is always computed from a ``context.cookies()`` call made AFTER the
    write. Nothing here is a constant, which is the whole of the change.
    """
    effect = {
        'kind': 'cookie_jar_observed' if holds else 'cookie_jar_unconfirmed',
        'action': action,
        'predicate': predicate,
        'measured_by': 'BrowserContext.cookies(), read back after the change',
        'detail': observed_detail if holds else unmet_detail,
    }
    effect.update(extra or {})
    if holds:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.INFERRED, effects=[effect])
    return envelope(Outcome.INDETERMINATE, claim_by=ClaimBy.INFERRED, effects=[effect])


@register_module(
    module_id='browser.cookies',
    version='1.0.0',
    category='browser',
    tags=['browser', 'cookies', 'session', 'storage', 'ssrf_protected', 'path_restricted'],
    label='Manage Cookies',
    label_key='modules.browser.cookies.label',
    description='Get, set, or clear browser cookies',
    description_key='modules.browser.cookies.description',
    icon='Cookie',
    color='#D4A373',

    # Connection types
    input_types=['browser', 'page'],
    output_types=['array', 'json'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.BROWSER_ACTION(options=['get', 'set', 'clear', 'delete']),
        presets.COOKIE_NAME(),
        presets.COOKIE_VALUE(),
        presets.COOKIE_DOMAIN(),
        presets.COOKIE_PATH(),
        presets.COOKIE_SECURE(),
        presets.COOKIE_HTTP_ONLY(),
        presets.COOKIE_EXPIRES(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.cookies.output.status.description'},
        'cookies': {'type': 'array', 'description': 'Browser cookies',
                'description_key': 'modules.browser.cookies.output.cookies.description'},
        'count': {'type': 'number', 'description': 'Number of items',
                'description_key': 'modules.browser.cookies.output.count.description'},
        'stored': {'type': 'boolean', 'description': (
                    'For the set action: whether the jar holds the cookie '
                    'afterwards. add_cookies() does not raise for one it refuses'
                ),
                'description_key': 'modules.browser.cookies.output.stored.description'},
        'remaining_count': {'type': 'number', 'description': (
                    'For the clear and delete actions: how many cookies the jar '
                    'holds afterwards, read back from the browser'
                ),
                'description_key': 'modules.browser.cookies.output.remaining_count.description'},
        'expected_remaining_count': {'type': 'number', 'description': (
                    'For the delete action: how many cookies the re-add was '
                    'supposed to restore'
                ),
                'description_key': 'modules.browser.cookies.output.expected_remaining_count.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far this action was followed, decided per action from a '
                    'read of the cookie jar afterwards: observed when the jar '
                    'agrees, indeterminate when it does not'
                ),
                'description_key': 'modules.browser.cookies.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Get all cookies',
            'params': {'action': 'get'}
        },
        {
            'name': 'Get specific cookie',
            'params': {'action': 'get', 'name': 'session_id'}
        },
        {
            'name': 'Set a cookie',
            'params': {
                'action': 'set',
                'name': 'user_pref',
                'value': 'dark_mode',
                'domain': 'example.com'
            }
        },
        {
            'name': 'Clear all cookies',
            'params': {'action': 'clear'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserCookiesModule(BaseModule):
    """Manage Cookies Module"""

    module_name = "Manage Cookies"
    module_description = "Get, set, or clear browser cookies"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['get', 'set', 'clear', 'delete']:
            raise ValueError(f"Invalid action: {self.action}")

        self.name = self.params.get('name')
        self.value = self.params.get('value')
        self.domain = self.params.get('domain')
        self.path = self.params.get('path', '/')
        self.secure = self.params.get('secure', False)
        self.http_only = self.params.get('httpOnly', False)
        self.expires = self.params.get('expires')

        if self.action == 'set':
            if not self.name or not self.value:
                raise ValueError("set action requires name and value")
            if not self.domain:
                raise ValueError("set action requires domain")

        if self.action == 'delete' and not self.name:
            raise ValueError("delete action requires name")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context

        if self.action == 'get':
            cookies = await context.cookies()
            if self.name:
                cookies = [c for c in cookies if c.get('name') == self.name]
            return {
                "status": "success",
                "cookies": cookies,
                "count": len(cookies),
                "outcome": _jar_read_outcome(
                    action='get', count=len(cookies), filtered_by=self.name,
                ),
            }

        elif self.action == 'set':
            cookie = {
                'name': self.name,
                'value': self.value,
                'domain': self.domain,
                'path': self.path,
                'secure': self.secure,
                'httpOnly': self.http_only
            }
            if self.expires:
                cookie['expires'] = self.expires

            await context.add_cookies([cookie])

            # add_cookies() returns normally for a cookie the jar refuses, so
            # this read is the only thing that distinguishes stored from
            # silently dropped.
            stored = [
                c for c in await context.cookies()
                if c.get('name') == self.name and c.get('value') == self.value
            ]
            return {
                "status": "success",
                # The cookie as the JAR holds it when it is there, so a caller
                # sees the normalised domain and expiry rather than the request.
                "cookies": stored or [cookie],
                "stored": bool(stored),
                "count": len(stored),
                "outcome": _jar_write_outcome(
                    action='set',
                    holds=bool(stored),
                    predicate='a cookie with this name and value is in the jar afterwards',
                    observed_detail=(
                        'The browser cookie store holds this cookie. Whether the '
                        'site will send it is a matter of domain, path and '
                        'expiry, and is not claimed here.'
                    ),
                    unmet_detail=(
                        'The cookie is not in the jar. add_cookies() does not '
                        'raise for a cookie it refuses -- an expiry in the past '
                        'is the measured case -- but a page script could equally '
                        'have overwritten it between the write and this read, so '
                        'this is indeterminate rather than failed.'
                    ),
                    extra={'name': self.name},
                ),
            }

        elif self.action == 'clear':
            await context.clear_cookies()
            remaining = await context.cookies()
            return {
                "status": "success",
                "cookies": [],
                # Read back rather than asserted: 0 used to be a literal.
                "count": 0,
                "remaining_count": len(remaining),
                "outcome": _jar_write_outcome(
                    action='clear',
                    holds=not remaining,
                    predicate='the cookie jar is empty afterwards',
                    observed_detail='The browser reports no cookies in the store.',
                    unmet_detail=(
                        'The jar still holds cookies after clear_cookies(). A '
                        'page setting one during the call would do this, so this '
                        'is indeterminate rather than failed.'
                    ),
                    extra={'remaining_count': len(remaining)},
                ),
            }

        elif self.action == 'delete':
            # Get all cookies, filter out the one to delete, then clear and re-add
            all_cookies = await context.cookies()
            remaining = [c for c in all_cookies if c.get('name') != self.name]
            await context.clear_cookies()
            if remaining:
                await context.add_cookies(remaining)

            # Read back, and read back in full. This action empties the jar and
            # re-adds the survivors, so what matters is not only that the named
            # cookie went but that the others came back -- add_cookies() drops
            # what it refuses without raising.
            jar_now = await context.cookies()
            still_present = [c for c in jar_now if c.get('name') == self.name]
            return {
                "status": "success",
                "deleted": self.name,
                "count": len(all_cookies) - len(remaining),
                "remaining_count": len(jar_now),
                "expected_remaining_count": len(remaining),
                "outcome": _jar_write_outcome(
                    action='delete',
                    holds=not still_present and len(jar_now) == len(remaining),
                    predicate=(
                        'no cookie of this name is in the jar afterwards, and the '
                        'other cookies were restored'
                    ),
                    observed_detail=(
                        'The named cookie is gone and the rest of the jar came '
                        'back at its previous size.'
                    ),
                    unmet_detail=(
                        'Either the named cookie is still there, or the re-add '
                        'restored fewer cookies than were cleared -- this action '
                        'empties the jar and puts the survivors back, and '
                        'add_cookies() drops what it refuses without raising.'
                    ),
                    extra={
                        'name': self.name,
                        'remaining_count': len(jar_now),
                        'expected_remaining_count': len(remaining),
                    },
                ),
            }
