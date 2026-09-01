# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Emulate Module - Device Emulation

Emulate mobile devices, tablets, and custom viewports.
Uses Playwright's device descriptors and viewport settings.

Works across all browsers (Chromium, Firefox, WebKit).

THE RETURN VALUE WAS THE `settings` DICT THIS FILE HAD JUST BUILT

``{"device": ..., "viewport": settings['viewport'], "user_agent":
settings['user_agent'], "is_mobile": ..., "device_scale_factor": ...}`` — every
one of those keys is read out of the dict assembled twenty lines earlier from a
preset table and the caller's overrides. Not one of them came from the browser.
It is `browser.viewport`'s trap with five fields instead of two: the payload is
byte-identical whether Chromium adopted the emulation or ignored it entirely.

The question this module has to answer is not "what did we send" but WHAT DOES
THE PAGE REPORT ABOUT ITSELF — that is the whole product. A site fingerprints
`navigator.userAgent`, `window.devicePixelRatio` and `navigator.maxTouchPoints`,
so those three are both the effect and the measurement, read back out of the
page after the emulation is applied:

    read back, and all three agree with what was requested   OBSERVED
    read back, and at least one disagrees                    INDETERMINATE
    the page could not be asked                              ACCEPTED

A partial agreement is INDETERMINATE and not OBSERVED, which is the one place
this differs from `browser.type`. There, a changed field proves the keystrokes
landed. Here the agreeing properties routinely agree for free — a desktop preset
asks for ``device_scale_factor=1`` and ``has_touch=False``, which is what a
plain Chromium already reports — so "two of three match" is not evidence that
this call did anything. Only the full set is.

WHY `window.innerWidth` IS NOT IN THE PREDICATE, measured rather than assumed.
It is the obvious candidate and it is wrong. Under ``is_mobile=True`` Chromium
reports the LAYOUT viewport, not the emulated device width, and a page with no
``<meta name=viewport>`` gets the 980px fallback:

    new_context(viewport={'width': 390, 'height': 844}, is_mobile=True)
    -> window.innerWidth == 980        (about:blank, and a page without the meta)
    -> window.innerWidth == 1560       (the same page at device_scale_factor 3)

Putting that in the predicate would mark every correct phone emulation
INDETERMINATE — the `browser.hover` failure exactly. The reading is still
carried in the effect, because it is a true fact about the page; it is simply
not the thing that decides the rung. `browser.viewport` may compare against
``innerWidth`` because it never touches ``is_mobile``.

WHAT THE READ-BACK CAUGHT. ``_emulate_via_cdp`` — the persistent-context path —
sent three ``Emulation.*`` overrides and then detached the CDP session in a
``finally``. Detaching a session REVERTS every override it installed. Measured
on the Chromium this repo drives:

    setUserAgentOverride + setDeviceMetricsOverride, then evaluate
        -> ua 'FAKE-UA/9.9', devicePixelRatio 3, maxTouchPoints 1
    cdp.detach(), then evaluate
        -> ua 'Mozilla/5.0 (Macintosh...HeadlessChrome/151', dpr 1, maxTouch 0

So in persistent-context mode this module applied nothing but the raw viewport
size, returned ``status: "success"`` and the full echoed settings, and every
request went out with the real Chromium fingerprint — the one thing a caller
runs device emulation to avoid. The session is now kept attached for the life of
the emulation and detached only when a later call replaces it.
"""
from typing import Any, Dict, List, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ....utils import enforce_outbound_url
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup


#: What the page says about itself. Every field here is answered by the document,
#: not by Playwright's record of what it was asked for: ``page.viewport_size``
#: replays the argument it was handed and is therefore not in this script.
_READ_EMULATION = """() => ({
    user_agent: navigator.userAgent,
    device_scale_factor: window.devicePixelRatio,
    max_touch_points: navigator.maxTouchPoints,
    inner_width: window.innerWidth,
    inner_height: window.innerHeight
})"""


async def _read_emulation(page) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(reading, None)`` when the page could be asked, ``(None, why)`` when not.

    Failing here is not a failure of the emulation: a page that closed, a
    navigation in flight, or a context torn down underneath us all land in the
    except. All that is lost is our ability to look.
    """
    try:
        return await page.evaluate(_READ_EMULATION), None
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"


def _emulate_outcome(
    *,
    settings: Dict[str, Any],
    reading: Optional[Dict[str, Any]],
    read_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this emulation earned, from what the page reports about itself."""
    requested_effect = {
        'kind': 'emulation_requested',
        'user_agent': settings['user_agent'],
        'device_scale_factor': settings['device_scale_factor'],
        'has_touch': settings['has_touch'],
        'is_mobile': settings['is_mobile'],
        'viewport': dict(settings['viewport']),
        'measured_by': None,
        'detail': (
            'The settings dict this module built from the preset table and the '
            'caller overrides. No browser call contributes to it: it reads '
            'identically whether the emulation was adopted or ignored.'
        ),
    }

    if reading is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                requested_effect,
                {
                    'kind': 'emulation_not_observed',
                    'measured_by': None,
                    'reason': read_error or 'the page could not be evaluated',
                    'detail': (
                        'Playwright accepted the emulation and did not raise. '
                        'The page was not asked what it now reports, so nothing '
                        'followed the settings into the browser.'
                    ),
                },
            ],
        )

    reported_touch = bool(reading.get('max_touch_points') or 0)
    agreement = {
        'user_agent': reading.get('user_agent') == settings['user_agent'],
        'device_scale_factor': _close(
            reading.get('device_scale_factor'), settings['device_scale_factor']
        ),
        'has_touch': reported_touch == bool(settings['has_touch']),
    }
    disagreed = sorted(name for name, held in agreement.items() if not held)

    observed_effect = {
        'kind': 'emulation_reported_by_page',
        'user_agent': reading.get('user_agent'),
        'device_scale_factor': reading.get('device_scale_factor'),
        'max_touch_points': reading.get('max_touch_points'),
        'agreement': agreement,
        'measured_by': (
            'page.evaluate of navigator.userAgent, window.devicePixelRatio and '
            'navigator.maxTouchPoints, read after the emulation was applied'
        ),
        'detail': (
            'What the document says about itself, which is what a site '
            'fingerprints. These three are the predicate.'
        ),
    }

    layout_effect = {
        'kind': 'layout_viewport_reported',
        'inner_width': reading.get('inner_width'),
        'inner_height': reading.get('inner_height'),
        'requested_width': settings['viewport']['width'],
        'requested_height': settings['viewport']['height'],
        'measured_by': 'page.evaluate of window.innerWidth / window.innerHeight',
        'detail': (
            'Reported, never compared. Under is_mobile these are the LAYOUT '
            'viewport -- a page with no viewport meta tag reports 980 for a '
            'device emulated at 390 -- so an equality here would mark every '
            'correct phone emulation as unconfirmed.'
        ),
    }

    if not disagreed:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: the predicate is ours. No caller asked for "the page must
            # report exactly this user agent".
            claim_by=ClaimBy.INFERRED,
            effects=[requested_effect, observed_effect, layout_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            requested_effect,
            observed_effect,
            layout_effect,
            {
                'kind': 'emulation_not_reflected',
                'predicate': (
                    'the page reports the requested user agent, device scale '
                    'factor and touch support'
                ),
                'disagreed': disagreed,
                'detail': (
                    'At least one emulated property is not what the page '
                    'reports. The properties that do agree may agree for free -- '
                    'a desktop preset asks for the scale factor and touch '
                    'support a plain Chromium already has -- so a partial match '
                    'is not evidence this call changed anything. Indeterminate '
                    'rather than failed: no postcondition was declared, the '
                    "comparison is this module's own, and a browser that "
                    'refuses an override is not the same as a broken one.'
                ),
            },
        ],
    )


def _close(reported: Any, requested: Any) -> bool:
    """Float-tolerant equality for ``devicePixelRatio``.

    The preset table carries 2.625 and 2.75; those survive the CDP round trip
    exactly today, but an exact ``==`` between a JS number and a Python float is
    the kind of thing that starts failing on a browser upgrade and reads as a
    broken emulation rather than as a rounding difference.
    """
    try:
        return abs(float(reported) - float(requested)) < 1e-6
    except (TypeError, ValueError):
        return False


# Device presets based on Playwright's device descriptors
DEVICE_PRESETS = {
    # iPhones
    'iphone_12': {
        'viewport': {'width': 390, 'height': 844},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'iphone_14': {
        'viewport': {'width': 390, 'height': 844},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'iphone_14_pro_max': {
        'viewport': {'width': 430, 'height': 932},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'iphone_se': {
        'viewport': {'width': 375, 'height': 667},
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },

    # Android phones
    'pixel_7': {
        'viewport': {'width': 412, 'height': 915},
        'user_agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
        'device_scale_factor': 2.625,
        'is_mobile': True,
        'has_touch': True,
    },
    'pixel_5': {
        'viewport': {'width': 393, 'height': 851},
        'user_agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36',
        'device_scale_factor': 2.75,
        'is_mobile': True,
        'has_touch': True,
    },
    'galaxy_s21': {
        'viewport': {'width': 360, 'height': 800},
        'user_agent': 'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },
    'galaxy_s23': {
        'viewport': {'width': 360, 'height': 780},
        'user_agent': 'Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
        'device_scale_factor': 3,
        'is_mobile': True,
        'has_touch': True,
    },

    # Tablets
    'ipad_pro': {
        'viewport': {'width': 1024, 'height': 1366},
        'user_agent': 'Mozilla/5.0 (iPad; CPU OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },
    'ipad_mini': {
        'viewport': {'width': 768, 'height': 1024},
        'user_agent': 'Mozilla/5.0 (iPad; CPU OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },
    'galaxy_tab_s8': {
        'viewport': {'width': 800, 'height': 1280},
        'user_agent': 'Mozilla/5.0 (Linux; Android 12; SM-X800) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36',
        'device_scale_factor': 2,
        'is_mobile': True,
        'has_touch': True,
    },

    # Desktop
    'desktop_chrome': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_firefox': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_safari': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'device_scale_factor': 2,
        'is_mobile': False,
        'has_touch': False,
    },
    'desktop_edge': {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },

    # Special viewports
    'laptop': {
        'viewport': {'width': 1366, 'height': 768},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'device_scale_factor': 1,
        'is_mobile': False,
        'has_touch': False,
    },
    'macbook_pro': {
        'viewport': {'width': 1440, 'height': 900},
        'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        'device_scale_factor': 2,
        'is_mobile': False,
        'has_touch': False,
    },
}


@register_module(
    module_id='browser.emulate',
    version='1.0.0',
    category='browser',
    tags=['browser', 'emulation', 'device', 'mobile', 'viewport', 'responsive'],
    label='Device Emulation',
    label_key='modules.browser.emulate.label',
    description='Emulate mobile devices, tablets, and custom viewports',
    description_key='modules.browser.emulate.description',
    icon='Smartphone',
    color='#8B5CF6',

    # Connection types
    input_types=['browser'],
    output_types=['browser', 'page'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'element.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field(
            'device',
            type='select',
            label='Device',
            label_key='modules.browser.emulate.params.device.label',
            description='Device preset or "custom" for manual settings',
            required=True,
            options=[
                {'value': 'iphone_12', 'label': 'iPhone 12'},
                {'value': 'iphone_14', 'label': 'iPhone 14'},
                {'value': 'iphone_14_pro_max', 'label': 'iPhone 14 Pro Max'},
                {'value': 'iphone_se', 'label': 'iPhone SE'},
                {'value': 'pixel_7', 'label': 'Pixel 7'},
                {'value': 'pixel_5', 'label': 'Pixel 5'},
                {'value': 'galaxy_s21', 'label': 'Galaxy S21'},
                {'value': 'galaxy_s23', 'label': 'Galaxy S23'},
                {'value': 'ipad_pro', 'label': 'iPad Pro'},
                {'value': 'ipad_mini', 'label': 'iPad Mini'},
                {'value': 'galaxy_tab_s8', 'label': 'Galaxy Tab S8'},
                {'value': 'desktop_chrome', 'label': 'Desktop Chrome'},
                {'value': 'desktop_firefox', 'label': 'Desktop Firefox'},
                {'value': 'desktop_safari', 'label': 'Desktop Safari'},
                {'value': 'desktop_edge', 'label': 'Desktop Edge'},
                {'value': 'laptop', 'label': 'Laptop (1366x768)'},
                {'value': 'macbook_pro', 'label': 'MacBook Pro'},
                {'value': 'custom', 'label': 'Custom'},
            ],
            group=FieldGroup.BASIC,
        ),
        field(
            'width',
            type='number',
            label='Width',
            label_key='modules.browser.emulate.params.width.label',
            description='Custom viewport width (for custom device)',
            required=False,
            min=320,
            max=3840,
            showIf={"device": {"$in": ["custom"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'height',
            type='number',
            label='Height',
            label_key='modules.browser.emulate.params.height.label',
            description='Custom viewport height (for custom device)',
            required=False,
            min=240,
            max=2160,
            showIf={"device": {"$in": ["custom"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'user_agent',
            type='string',
            label='User Agent',
            label_key='modules.browser.emulate.params.user_agent.label',
            description='Custom user agent string',
            required=False,
            placeholder='Mozilla/5.0...',
            showIf={"device": {"$in": ["custom"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'device_scale_factor',
            type='number',
            label='Device Scale Factor',
            label_key='modules.browser.emulate.params.device_scale_factor.label',
            description='Device pixel ratio (1-3)',
            required=False,
            min=1,
            max=3,
            showIf={"device": {"$in": ["custom"]}},
            group=FieldGroup.OPTIONS,
        ),
        field(
            'is_mobile',
            type='boolean',
            label='Mobile Mode',
            label_key='modules.browser.emulate.params.is_mobile.label',
            description='Enable mobile browser behavior',
            required=False,
            default=None,
            showIf={"device": {"$in": ["custom"]}},
            group=FieldGroup.ADVANCED,
        ),
        field(
            'has_touch',
            type='boolean',
            label='Touch Support',
            label_key='modules.browser.emulate.params.has_touch.label',
            description='Enable touch event support',
            required=False,
            default=None,
            showIf={"device": {"$in": ["custom"]}},
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.emulate.output.status.description'
        },
        'device': {
            'type': 'string',
            'description': 'Emulated device name',
            'description_key': 'modules.browser.emulate.output.device.description'
        },
        'viewport': {
            'type': 'object',
            'description': 'Applied viewport dimensions',
            'description_key': 'modules.browser.emulate.output.viewport.description'
        },
        'is_mobile': {
            'type': 'boolean',
            'description': 'Whether mobile mode is enabled',
            'description_key': 'modules.browser.emulate.output.is_mobile.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the emulation was followed: observed when the page '
                'reports the requested user agent, device scale factor and '
                'touch support, indeterminate when any of them differs, '
                'accepted when the page could not be asked'
            ),
            'description_key': 'modules.browser.emulate.output.outcome.description'
        },
    },
    examples=[
        {
            'name': 'Emulate iPhone 14',
            'params': {'device': 'iphone_14'}
        },
        {
            'name': 'Emulate iPad Pro',
            'params': {'device': 'ipad_pro'}
        },
        {
            'name': 'Custom mobile viewport',
            'params': {
                'device': 'custom',
                'width': 400,
                'height': 800,
                'is_mobile': True,
                'has_touch': True,
                'device_scale_factor': 2
            }
        },
        {
            'name': 'Desktop with custom user agent',
            'params': {
                'device': 'desktop_chrome',
                'user_agent': 'CustomBot/1.0'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.automation'],
)
class BrowserEmulateModule(BaseModule):
    """Device Emulation Module"""

    module_name = "Device Emulation"
    module_description = "Emulate mobile devices and viewports"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.device = self.params.get('device')
        if not self.device:
            raise ValueError("Missing required parameter: device")

        # Get device preset or use custom
        if self.device == 'custom':
            # Custom device requires width and height
            self.width = self.params.get('width')
            self.height = self.params.get('height')
            if not self.width or not self.height:
                raise ValueError("Custom device requires width and height")
            self.preset = None
        elif self.device in DEVICE_PRESETS:
            self.preset = DEVICE_PRESETS[self.device]
            self.width = self.params.get('width', self.preset['viewport']['width'])
            self.height = self.params.get('height', self.preset['viewport']['height'])
        else:
            raise ValueError(
                f"Unknown device: {self.device}. "
                f"Available: {', '.join(sorted(DEVICE_PRESETS.keys()))}, custom"
            )

        # Custom overrides
        self.user_agent = self.params.get('user_agent')
        self.is_mobile = self.params.get('is_mobile')
        self.has_touch = self.params.get('has_touch')
        self.device_scale_factor = self.params.get('device_scale_factor')

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Build emulation settings
        if self.preset:
            settings = {
                'viewport': {'width': self.width, 'height': self.height},
                'user_agent': self.user_agent or self.preset['user_agent'],
                'device_scale_factor': self.device_scale_factor or self.preset['device_scale_factor'],
                'is_mobile': self.is_mobile if self.is_mobile is not None else self.preset['is_mobile'],
                'has_touch': self.has_touch if self.has_touch is not None else self.preset['has_touch'],
            }
        else:
            # Custom device
            settings = {
                'viewport': {'width': self.width, 'height': self.height},
                'user_agent': self.user_agent or 'Mozilla/5.0 (compatible)',
                'device_scale_factor': self.device_scale_factor or 1,
                'is_mobile': self.is_mobile if self.is_mobile is not None else False,
                'has_touch': self.has_touch if self.has_touch is not None else False,
            }

        old_page = browser._page
        old_context = browser._context
        current_url = old_page.url if old_page else None

        if browser._browser is None:
            # Persistent context mode — can't create new context,
            # use CDP to apply device emulation on the existing page.
            return await self._emulate_via_cdp(browser, settings, current_url)

        try:
            # Regular mode — create new context with device emulation
            new_context = await browser._browser.new_context(
                viewport=settings['viewport'],
                user_agent=settings['user_agent'],
                device_scale_factor=settings['device_scale_factor'],
                is_mobile=settings['is_mobile'],
                has_touch=settings['has_touch'],
            )

            # Create new page
            new_page = await new_context.new_page()

            # Navigate to same URL if we had one
            if current_url and current_url != 'about:blank':
                # Defense in depth: current_url already passed the guard when
                # it was first navigated to, but a redirect or DNS change since
                # then makes re-navigation a fresh outbound request
                # (GHSA-pfg2-w999-497v is that TOCTOU).
                enforce_outbound_url(current_url)
                await new_page.goto(current_url)

            # Close old context (this also closes old page)
            await old_context.close()

            # Update browser references
            browser._context = new_context
            browser._page = new_page

            reading, read_error = await _read_emulation(new_page)

            return {
                "status": "success",
                "device": self.device,
                "viewport": settings['viewport'],
                "user_agent": settings['user_agent'],
                "is_mobile": settings['is_mobile'],
                "has_touch": settings['has_touch'],
                "device_scale_factor": settings['device_scale_factor'],
                "url": new_page.url,
                "outcome": _emulate_outcome(
                    settings=settings, reading=reading, read_error=read_error,
                ),
            }

        except Exception as e:
            # Try to restore old context on error
            browser._context = old_context
            browser._page = old_page
            raise RuntimeError(f"Failed to apply device emulation: {str(e)}") from e

    async def _emulate_via_cdp(self, browser, settings, current_url):
        """Apply device emulation via CDP for persistent context mode.

        The CDP session is deliberately NOT detached. ``Emulation.*`` overrides
        live on the session that installed them, and detaching reverts every one
        of them -- which is what the ``finally: await cdp.detach()`` that used to
        stand here did, immediately, on every call. See the module docstring for
        the measurement. A later emulation detaches the session it is replacing,
        so at most one is held per driver.
        """
        page = browser._page

        # Set viewport size (Playwright API)
        await page.set_viewport_size(settings['viewport'])

        # Replace the previous emulation before installing this one: detaching
        # afterwards would revert the overrides we are about to send.
        previous = getattr(browser, '_emulation_cdp', None)
        if previous is not None:
            try:
                await previous.detach()
            except Exception:  # noqa: BLE001 - a dead session is already gone
                pass
            browser._emulation_cdp = None

        # Use CDP session for user agent, touch, and device metrics
        cdp = await page.context.new_cdp_session(page)
        browser._emulation_cdp = cdp
        await cdp.send('Emulation.setUserAgentOverride', {
            'userAgent': settings['user_agent'],
        })
        await cdp.send('Emulation.setTouchEmulationEnabled', {
            'enabled': settings['has_touch'],
        })
        await cdp.send('Emulation.setDeviceMetricsOverride', {
            'width': settings['viewport']['width'],
            'height': settings['viewport']['height'],
            'deviceScaleFactor': settings['device_scale_factor'],
            'mobile': settings['is_mobile'],
        })

        # Reload to apply user agent change
        if current_url and current_url != 'about:blank':
            await page.reload()

        reading, read_error = await _read_emulation(page)

        return {
            "status": "success",
            "device": self.device,
            "viewport": settings['viewport'],
            "user_agent": settings['user_agent'],
            "is_mobile": settings['is_mobile'],
            "has_touch": settings['has_touch'],
            "device_scale_factor": settings['device_scale_factor'],
            "url": page.url,
            "outcome": _emulate_outcome(
                settings=settings, reading=reading, read_error=read_error,
            ),
        }
