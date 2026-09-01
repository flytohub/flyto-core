# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP GET Request Module

Simplified GET request for API calls.

HOW FAR THIS MODULE FOLLOWS REALITY

ACCEPTED, and the argument is `http.request`'s: a status line is the other side
reporting on its own work. Somebody received this request and chose a reply,
which is more than DISPATCHED can say and is exactly what ACCEPTED means. It is
not OBSERVED, because OBSERVED is a measurement of the world and nothing here
reads anything back -- there is no second request and no comparison, only the
answer to the very message we sent.

The 2xx test does not lift that. It partitions the peer's own claim into two
buckets; it does not check the claim against anything.

ONE RETURN, THREE RAISES, and the raises carry nothing. This module signals
failure by raising `NetworkError` -- for a non-2xx status, for an SSRF refusal
and for any transport error -- and an exception has no payload for an envelope
to live in. So the rungs that belong to those paths cannot be attached here:
an SSRF refusal is FAILED (nothing left us) and a timeout is INDETERMINATE (the
peer may have received it), and neither is expressible while the paths raise.
That is a real gap in this module, written down rather than papered over.
`http.request` returns error dicts instead and does attach them.
"""

import logging
from typing import Any, Dict, List

from ...registry import register_module
from ...errors import ValidationError, NetworkError, ModuleError
from ...schema import compose, presets
from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import (
    guarded_client_session,
    validate_url_with_env_config,
    SSRFError,
    ssrf_protection_enabled,
    guarded_aiohttp_request,
)

logger = logging.getLogger(__name__)


def _observed_effects(response, body: Any) -> List[Dict[str, Any]]:
    """What this request actually measured, with the provenance of each field.

    `bytes_received` is populated only when the body is still bytes. This
    module's parser hands back `str` for text and a parsed object for JSON, and
    neither has a byte count: `len()` over the decoded string is characters,
    and over a dict it is a number of keys. Reporting either as a byte count
    would be a lie of exactly the shape this contract exists to stop, so the
    field is null on those paths.

    `declared_content_length` is named for what it is -- the peer's claim about
    how much it meant to send -- and is not evidence of what arrived.
    """
    declared = response.headers.get('Content-Length')
    return [
        {
            'kind': 'http_status_received',
            'status': response.status,
            'reason': response.reason or '',
            'measured_by': 'response.status, read off the reply',
        },
        {
            'kind': 'response_body_read',
            'body_type': type(body).__name__,
            'bytes_received': (
                len(body) if isinstance(body, (bytes, bytearray)) else None
            ),
            'declared_content_length': (
                int(declared) if isinstance(declared, str) and declared.isdigit() else None
            ),
            'measured_by': 'len(body) when the body is bytes; otherwise nothing',
        },
    ]


def _append_query_params(url: str, query: dict) -> str:
    """Append query parameters to URL."""
    from urllib.parse import urlencode, urlparse, urlunparse

    parsed = urlparse(url)
    separator = '&' if parsed.query else ''
    new_query = parsed.query + separator + urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


async def _parse_response_body(response) -> Any:
    """Parse response body, attempting JSON for JSON content types."""
    content_type = response.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        try:
            return await response.json()
        except Exception:
            return await response.text()
    return await response.text()


@register_module(
    module_id='http.get',
    version='1.0.0',
    category='http',
    subcategory='client',
    tags=['api', 'http', 'get', 'request', 'atomic', 'ssrf_protected'],
    label='HTTP GET',
    label_key='modules.http.get.label',
    description='Send HTTP GET request to an API endpoint',
    description_key='modules.http.get.description',
    icon='Download',
    color='#3B82F6',

    input_types=['string'],
    output_types=['object', 'json'],
    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=60000,
    required_permissions=["network.access"],
    retryable=True,
    max_retries=3,
    requires_credentials=True,
    credential_keys=['API_KEY'],

    params_schema=compose(
        presets.URL(required=True, placeholder='https://api.example.com/data', description='Target URL'),
        presets.HEADERS(),
        presets.QUERY_PARAMS(),
        presets.TIMEOUT_S(default=30),
        presets.VERIFY_SSL(default=True),
        presets.SSRF_PROTECTION(),
    ),
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the operation succeeded',
               'description_key': 'modules.http.get.output.ok.description'},
        'status': {'type': 'number', 'description': 'HTTP status code',
                   'description_key': 'modules.http.get.output.status.description'},
        'body': {'type': 'any', 'description': 'Response body content',
                 'description_key': 'modules.http.get.output.body.description'},
        'headers': {'type': 'object', 'description': 'Response headers',
                    'description_key': 'modules.http.get.output.headers.description'},
        'outcome': {
            'type': 'object',
            'description': (
                "Outcome envelope. Rung 'accepted': the peer answered with a "
                'status line. Nothing here reads the resource back, so no '
                'change to it was observed. Present on 2xx only -- every other '
                'path raises'
            ),
            'description_key': 'modules.http.get.output.outcome.description'}
    }
)
async def http_get(context: Dict[str, Any]) -> Dict[str, Any]:
    """Send HTTP GET request."""
    try:
        import aiohttp
    except ImportError:
        raise ModuleError("aiohttp required. Install: pip install aiohttp")

    params = context['params']
    url = params.get('url')
    if not url:
        raise ValidationError("Missing required parameter: url", field="url")

    headers = params.get('headers', {})
    query = params.get('query', {})
    timeout_s = params.get('timeout', 30)
    verify_ssl = params.get('verify_ssl', True)

    if ssrf_protection_enabled():
        try:
            validate_url_with_env_config(url)
        except SSRFError as e:
            logger.warning(f"SSRF protection blocked GET to: {url}")
            raise NetworkError(str(e), url=url, status_code=0)

    if query:
        url = _append_query_params(url, query)

    try:
        ssl_param = None if verify_ssl else False
        timeout = aiohttp.ClientTimeout(total=timeout_s)
        async with guarded_client_session(timeout=timeout) as session:
            # SECURITY: revalidate every redirect hop through the SSRF guard so a
            # public URL cannot 302 into internal space (GHSA-c9hr-64h3-gxpc).
            response = await guarded_aiohttp_request(
                session, 'GET', url, headers=headers, ssl=ssl_param)
            try:
                body = await _parse_response_body(response)
                if 200 <= response.status < 300:
                    return {
                        'ok': True,
                        'data': {
                            'status': response.status,
                            'body': body,
                            'headers': dict(response.headers),
                            'outcome': envelope(
                                Outcome.ACCEPTED,
                                # NONE: no caller declared an expected outcome
                                # and this module infers none, so there is no
                                # expectation that could have been broken.
                                claim_by=ClaimBy.NONE,
                                effects=_observed_effects(response, body),
                            ),
                        },
                    }
                raise NetworkError(f"HTTP {response.status} error", url=url, status_code=response.status)
            finally:
                response.release()
    except NetworkError:
        raise
    except Exception as e:
        logger.error(f"HTTP GET failed: {e}")
        raise NetworkError(str(e), url=url)
