# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""What a browser SESSION module can honestly say it measured.

Four modules start a browser (`browser.launch`, `browser.ensure`,
`browser.connect`, `browser.pool` create) and three end one (`browser.release`,
`browser.pool` close / close_all). Before this file, every one of them reported
its own parameters back:

    browser.launch    {"browser_type": self.browser_type, "headless":
                       self.headless, "viewport": self.viewport,
                       "behavior": self.behavior, "message": "Browser launched
                       successfully"}
    browser.connect   {"connected": True, "browser_type": "chromium"}
    browser.ensure    {"message": "Browser launched successfully"}
    browser.pool      {"count": len(_browser_pool)}   # our own dict
    browser.release   {"message": "Browser closed successfully"}

Not one of those values is read from a browser. ``browser_type`` is the string
the caller typed; ``connected: True`` is a literal; ``count`` is the size of a
module-global dictionary that would be identical if every driver in it were
dead. They are `file.write`'s ``bytes_written`` with a browser attached.

THE TWO PLAYWRIGHT VALUES, AND WHY ONLY ONE OF THEM IS EVIDENCE OF A LAUNCH

``Browser.is_connected()`` (``playwright/_impl/_browser.py:128``) returns
``self._is_connected``, a plain attribute set to ``True`` in ``__init__`` and
flipped to ``False`` only by ``_on_close`` when a disconnect event arrives from
the driver. So the two directions are not symmetric evidence:

    False   a real event travelled from the browser process to us. Evidence.
    True    the value the attribute was born with. It is `browser.storage`'s
            literal `True`, one indirection away. A browser SIGKILLed a
            millisecond ago still reads `True` until the event is processed.

That asymmetry decides how this file is used. `browser.close` already rests its
OBSERVED on the False direction, and `browser.release` and `browser.pool` do the
same here. Nothing in this file claims a rung from ``is_connected() is True``.

``Browser.version`` (``_browser.py:247``) is the other value, and it is the
opposite kind: ``self._initializer["version"]``, built by the Playwright driver
from the browser's own protocol handshake. Measured on this machine, a launched
Chromium reports ``151.0.7922.34`` there, the DevTools ``/json/version``
endpoint of the same process reports ``HeadlessChrome/151.0.7922.34``, and
``navigator.userAgent`` inside its first page reports the same version again.
It is not derived from any parameter we passed: ask for ``browser_type:
'chromium'`` and get a string naming the build that actually started.

WOULD THIS VALUE BE THE SAME IF THE EFFECT HAD NOT HAPPENED? There would be no
Browser object to read it from, which is the ACCEPTED branch below. So a version
string is evidence that a browser process exists and identified itself — which
is what a launch claims and what nothing in these modules measured before.

PERSISTENT CONTEXT. ``BrowserDriver._launch_persistent`` sets ``_browser = None``
in so many words, and `browser.close` records that as a case it cannot measure.
It does not have to be: measured on Playwright 1.62, a context returned by
``launch_persistent_context`` has a ``.browser`` that is a real Browser object
reporting the same version. Asking the context second is what lets the default
desktop launch path be measured at all — and on a machine where that is not so,
``read_engine`` returns the reason and the rung drops to ACCEPTED rather than
guessing.

WHY THIS FILE HANDS BACK PARTS AND NOT FINISHED ENVELOPES

``started_claim`` and ``closed_claim`` return ``(rung, claim_by, effect)`` and
leave the ``envelope(...)`` call to the module. The measurement is shared
because measuring the same thing five ways is how the five modules came to
disagree in the first place; the CLAIM is not, because it belongs at the return
site where a reader is deciding whether to believe it. It also keeps every
declaring module importing ``core.engine.outcome`` itself, which is what the
declaration ratchet counts.
"""

from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome


def browser_object(driver: Any) -> Any:
    """The Playwright ``Browser`` behind a driver, or None when there is none.

    ``driver._browser`` first, then ``driver._context.browser`` for the
    persistent-context path that leaves the first one None. Any failure to look
    is None, never an exception: not being able to measure is not a failure of
    the thing being measured.
    """
    direct = getattr(driver, '_browser', None)
    if direct is not None:
        return direct
    context = getattr(driver, '_context', None)
    if context is None:
        return None
    try:
        return context.browser
    except Exception:  # noqa: BLE001 - any failure means "cannot look"
        return None


def read_engine(driver: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """``(engine, version, None)`` when the process identified itself, else
    ``(None, None, why)``."""
    found = browser_object(driver)
    if found is None:
        return None, None, (
            'no Browser object to ask: neither the driver nor its context has one'
        )
    try:
        version = found.version
        engine = found.browser_type.name
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
    if not version:
        return engine, None, 'the Browser object reports an empty version string'
    return engine, version, None


def started_claim(
    *,
    engine: Optional[str],
    version: Optional[str],
    requested_engine: Optional[str],
    reason: Optional[str],
) -> Tuple[Outcome, ClaimBy, Dict[str, Any]]:
    """The rung a started browser session earned, and the reading that earned it.

        the process reported a version   OBSERVED
        nothing to ask, or asking failed ACCEPTED

    ``requested_engine`` rides beside the measured one on purpose. They are
    different facts and this is the module that can tell them apart: a caller
    asking for ``chromium`` may be served Playwright's bundled build, system
    Chrome, or Edge, because ``BrowserDriver._chromium_channel_candidates``
    falls through ``(None, "chrome", "msedge")`` when no channel is pinned.
    ``browser_type.name`` is still ``chromium`` for all three — Playwright names
    the launcher, not the channel — so the version string is the only part of
    this that changes when a different binary starts.
    """
    if version is None:
        return Outcome.ACCEPTED, ClaimBy.NONE, {
            'kind': 'browser_process_not_identified',
            'requested_engine': requested_engine,
            'measured_by': None,
            'reason': reason,
            'detail': (
                'launch() returned without raising, so a browser was started '
                'as far as Playwright is concerned. Nothing was read back out '
                'of the process, so what started, and whether it is still '
                'there, is not established here.'
            ),
        }

    return Outcome.OBSERVED, ClaimBy.NONE, {
        'kind': 'browser_process_identified',
        'engine': engine,
        'version': version,
        'requested_engine': requested_engine,
        'measured_by': (
            'Browser.version — the version string the browser process '
            'reported through the DevTools protocol handshake'
        ),
        'detail': (
            'A process that did not exist now exists and named its own build. '
            'This is not derived from any launch parameter: the requested '
            'engine is carried separately so the two can disagree. Whether the '
            'process is still alive a moment later is a different question and '
            'is not claimed — Browser.is_connected() is born True and is not '
            'evidence.'
        ),
    }


def observe_disconnected(browser_obj: Any) -> Tuple[Optional[bool], Optional[str]]:
    """``(disconnected, None)`` when Playwright could be asked, ``(None, why)`` else.

    The same shape `browser.close` uses, kept here so `browser.release` and
    `browser.pool` measure teardown the same way rather than three ways.
    """
    if browser_obj is None:
        return None, 'no Browser object to ask (persistent context, or never launched)'
    try:
        return not browser_obj.is_connected(), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


def closed_claim(
    *,
    disconnected: Optional[bool],
    reason: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[Outcome, ClaimBy, Dict[str, Any]]:
    """The rung a teardown earned, from Playwright's own connection state.

        the connection is gone        OBSERVED    a disconnect event arrived
        the connection is still live  INDETERMINATE
        nothing to ask                ACCEPTED

    Still-connected is INDETERMINATE and not FAILED for `browser.close`'s
    reason: teardown is asynchronous at the process level, so a browser that has
    been asked to exit and has not finished reads exactly like one that refused.
    """
    detail = dict(extra or {})

    if disconnected is None:
        return Outcome.ACCEPTED, ClaimBy.NONE, {
            'kind': 'browser_state_not_observed',
            'measured_by': None,
            'reason': reason,
            'detail': (
                'close() returned. BrowserDriver.close swallows a failure or a '
                'timeout at every teardown step and returns the same value '
                'either way, so its return is an acknowledgement and not a '
                'finding.'
            ),
            **detail,
        }

    if disconnected:
        return Outcome.OBSERVED, ClaimBy.NONE, {
            'kind': 'browser_disconnected',
            'measured_by': 'Browser.is_connected() on the object held across close()',
            'detail': (
                'Playwright no longer has a live connection to the browser '
                'process — the flag is only ever cleared by a disconnect event '
                'arriving from it. Whether the OS process has fully exited, '
                'and whether the profile directory was cleaned up, are not '
                'measured here.'
            ),
            **detail,
        }

    return Outcome.INDETERMINATE, ClaimBy.INFERRED, {
        'kind': 'browser_still_connected',
        'predicate': 'not Browser.is_connected()',
        'measured_by': 'Browser.is_connected() on the object held across close()',
        'detail': (
            'close() reported success and the connection is still live. '
            'Teardown is asynchronous, so a browser that has been asked to '
            'exit and has not finished reads the same as one that refused. We '
            'cannot say which, only that "closed successfully" is not '
            'established.'
        ),
        **detail,
    }
