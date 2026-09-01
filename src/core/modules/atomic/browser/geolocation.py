# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Geolocation Module

Mock browser geolocation.

`location` WAS THE THREE NUMBERS THE CALLER PASSED IN

``{"latitude": self.latitude, "longitude": self.longitude, "accuracy":
self.accuracy}`` is ``self.params``, re-keyed. It is the same dict whether the
context adopted the position, whether ``grant_permissions`` took, or whether the
page will ever be told anything at all. `browser.viewport`'s trap, in degrees.

The measurement that is not that is the one thing this module exists to affect:
what ``navigator.geolocation`` HANDS TO THE PAGE. A page asked for its position
is the entire product, so the read-back is that same API, called in the page
after the mock is installed.

    the page's Geolocation API returns the mocked coordinates   OBSERVED
    it returns some other position                              INDETERMINATE
    it errors, or the page could not be asked                   ACCEPTED

The value cannot read the same with and without the effect: on a context with no
mock and no grant, ``getCurrentPosition`` invokes the ERROR callback
(PERMISSION_DENIED) rather than returning coordinates, and a machine with real
location services returns the machine's position, not San Francisco.

ACCEPTED, NOT INDETERMINATE, FOR THE ERROR CASE, and the reason is measured
rather than assumed. Chromium refuses the Geolocation API outright on a
non-secure origin -- ``about:blank`` included:

    context.grant_permissions(['geolocation']); context.set_geolocation(...)
    about:blank            -> error 1: 'Only secure origins are allowed'
    http://127.0.0.1:PORT  -> {lat: 37.7749, lon: -122.4194, acc: 100}

Setting a mock before navigating anywhere is the ordinary way to use this
module, and it works -- the position is held on the context and delivered once
the page reaches a secure origin. An error from a page we have not navigated yet
therefore says nothing about the mock; it says we cannot look. Calling that
INDETERMINATE would put a warning on the correct usage.
"""
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field
from ...schema.constants import FieldGroup


#: Ask the page where it thinks it is. ``page.evaluate`` awaits the promise, so
#: the callback-based API can be read like a value. The inner timeout is short
#: because a mocked position is answered from the browser process and needs no
#: hardware; anything slower than this is not going to arrive.
_READ_POSITION = """() => new Promise((resolve) => {
    if (!navigator.geolocation) { resolve({error: 'no Geolocation API in this page'}); return; }
    navigator.geolocation.getCurrentPosition(
        (pos) => resolve({
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracy: pos.coords.accuracy
        }),
        (err) => resolve({error: 'code ' + err.code + ': ' + err.message}),
        {timeout: 3000, maximumAge: 0}
    );
})"""


async def _read_position(page) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(position, None)`` when the page answered with coordinates, else ``(None, why)``."""
    if page is None:
        return None, 'no page to ask'
    try:
        answer = await page.evaluate(_READ_POSITION)
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
    if not isinstance(answer, dict) or 'latitude' not in answer:
        reason = (answer or {}).get('error') if isinstance(answer, dict) else None
        return None, reason or 'the page returned no coordinates'
    return answer, None


def _geolocation_outcome(
    *,
    requested: Dict[str, Any],
    reported: Optional[Dict[str, Any]],
    read_error: Optional[str],
) -> Dict[str, Any]:
    """The rung this mock earned, from what the page's own API reports."""
    requested_effect = {
        'kind': 'geolocation_requested',
        'latitude': requested['latitude'],
        'longitude': requested['longitude'],
        'accuracy': requested['accuracy'],
        'measured_by': None,
        'detail': (
            'The caller\'s three parameters. No browser call contributes to '
            'them: they read identically whether the context adopted the '
            'position or dropped it.'
        ),
    }

    if reported is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                requested_effect,
                {
                    'kind': 'geolocation_not_observed',
                    'measured_by': None,
                    'reason': read_error or 'the page did not answer with a position',
                    'detail': (
                        'grant_permissions() and set_geolocation() returned '
                        'without raising and the page was not able to tell us '
                        'where it thinks it is. Chromium refuses the Geolocation '
                        'API on a non-secure origin, about:blank included, so '
                        'setting the mock before navigating lands here and is '
                        'still the ordinary way to use this module.'
                    ),
                },
            ],
        )

    matches = (
        _close(reported.get('latitude'), requested['latitude'])
        and _close(reported.get('longitude'), requested['longitude'])
    )
    observed_effect = {
        'kind': 'geolocation_reported_by_page',
        'latitude': reported.get('latitude'),
        'longitude': reported.get('longitude'),
        'accuracy': reported.get('accuracy'),
        'measured_by': (
            'page.evaluate of navigator.geolocation.getCurrentPosition, read '
            'after the mock was installed'
        ),
        'detail': (
            'The position the page is served when it asks. Without the mock '
            'this call reaches the error callback instead.'
        ),
    }

    if matches:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: the predicate is ours. No caller declared "the page must
            # be told exactly these coordinates".
            claim_by=ClaimBy.INFERRED,
            effects=[requested_effect, observed_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            requested_effect,
            observed_effect,
            {
                'kind': 'geolocation_differs',
                'predicate': 'the page reports the mocked latitude and longitude',
                'detail': (
                    'The page was served a position and it is not the one that '
                    'was set. A second mock installed after this one, or a page '
                    'holding a cached fix, both do this. Indeterminate rather '
                    'than failed: no postcondition was declared and the '
                    'comparison is this module\'s own.'
                ),
            },
        ],
    )


def _close(reported: Any, requested: Any) -> bool:
    """Degrees compared with a tolerance, not with ``==``.

    The coordinates survive the CDP round trip exactly today. An exact equality
    between a JS number and a Python float is still the wrong thing to write
    down: the failure it would produce reads as "the browser ignored the mock"
    when it means "the last decimal moved".
    """
    try:
        return abs(float(reported) - float(requested)) < 1e-6
    except (TypeError, ValueError):
        return False


@register_module(
    module_id='browser.geolocation',
    version='1.0.0',
    category='browser',
    tags=['browser', 'geolocation', 'location', 'gps', 'ssrf_protected'],
    label='Mock Geolocation',
    label_key='modules.browser.geolocation.label',
    description='Mock browser geolocation',
    description_key='modules.browser.geolocation.description',
    icon='MapPin',
    color='#0D6EFD',

    # Connection types
    input_types=['browser', 'page'],
    output_types=['object'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        field(
            'latitude',
            type='number',
            label='Latitude',
            label_key='modules.browser.geolocation.params.latitude.label',
            placeholder='37.7749',
            description='Latitude coordinate (-90 to 90)',
            required=True,
            min=-90,
            max=90,
            group=FieldGroup.BASIC,
        ),
        field(
            'longitude',
            type='number',
            label='Longitude',
            label_key='modules.browser.geolocation.params.longitude.label',
            placeholder='-122.4194',
            description='Longitude coordinate (-180 to 180)',
            required=True,
            min=-180,
            max=180,
            group=FieldGroup.BASIC,
        ),
        field(
            'accuracy',
            type='number',
            label='Accuracy (meters)',
            label_key='modules.browser.geolocation.params.accuracy.label',
            description='Position accuracy in meters',
            default=100,
            min=0,
            max=100000,
            step=10,
            group=FieldGroup.ADVANCED,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.geolocation.output.status.description'},
        'location': {'type': 'object', 'description': 'The location',
                'description_key': 'modules.browser.geolocation.output.location.description'},
        'reported_location': {'type': 'object',
                'description': 'The position the page itself reports, or null when it could not be asked',
                'description_key': 'modules.browser.geolocation.output.reported_location.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far the mock was followed: observed when the page\'s '
                    'own Geolocation API returns the mocked coordinates, '
                    'accepted when the page could not be asked'
                ),
                'description_key': 'modules.browser.geolocation.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Set location to San Francisco',
            'params': {'latitude': 37.7749, 'longitude': -122.4194}
        },
        {
            'name': 'Set location with high accuracy',
            'params': {'latitude': 51.5074, 'longitude': -0.1278, 'accuracy': 10}
        },
        {
            'name': 'Set location to Tokyo',
            'params': {'latitude': 35.6762, 'longitude': 139.6503}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserGeolocationModule(BaseModule):
    """Mock Geolocation Module"""

    module_name = "Mock Geolocation"
    module_description = "Mock browser geolocation"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'latitude' not in self.params:
            raise ValueError("Missing required parameter: latitude")
        if 'longitude' not in self.params:
            raise ValueError("Missing required parameter: longitude")

        self.latitude = self.params['latitude']
        self.longitude = self.params['longitude']
        self.accuracy = self.params.get('accuracy', 100)

        # Validate ranges
        if self.latitude < -90 or self.latitude > 90:
            raise ValueError(f"Latitude must be between -90 and 90, got: {self.latitude}")
        if self.longitude < -180 or self.longitude > 180:
            raise ValueError(f"Longitude must be between -180 and 180, got: {self.longitude}")
        if self.accuracy < 0:
            raise ValueError(f"Accuracy must be positive, got: {self.accuracy}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context

        # Grant geolocation permission and set location
        await context.grant_permissions(['geolocation'])
        await context.set_geolocation({
            'latitude': self.latitude,
            'longitude': self.longitude,
            'accuracy': self.accuracy
        })

        requested = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy": self.accuracy,
        }
        reported, read_error = await _read_position(getattr(browser, '_page', None))

        return {
            "status": "success",
            "location": requested,
            # What the page is actually served, when it could be asked. Absent
            # rather than echoed when it could not: a copy of `location` here
            # would be the same trap one key over.
            "reported_location": reported,
            "outcome": _geolocation_outcome(
                requested=requested, reported=reported, read_error=read_error,
            ),
        }
