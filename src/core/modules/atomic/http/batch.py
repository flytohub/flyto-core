# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
HTTP Batch Module

Execute N HTTP requests in sequence (for timing-sensitive probes) or parallel,
capturing per-request status, body, headers, duration_ms, and label. Designed
for pentest blueprints that need baseline + payload comparison (SQL injection,
XSS reflected, auth bypass).

HOW FAR THIS MODULE FOLLOWS REALITY

The envelope is PER REQUEST, not per batch, and that is forced by the shape of
the result as much as by honesty. `data` here is a list, so
`wrap_legacy_result` turns each entry into its own Item and every sibling key
at the top level -- `count`, `failed_count`, `total_duration_ms` -- is already
discarded on the way out of a step. A batch-level envelope written beside them
could never be read. Each entry, on the other hand, survives as an item, and
`step_executor._outcome_payloads` walks list entries, so `step_outcome` sees
all of them and reports the weakest. A batch is exactly as confirmed as its
least confirmed request, which is the rule that function already applies.

Per request, two answers:

    a status line came back    ACCEPTED
        The peer received the probe and chose a reply. `bytes_received` here
        IS a byte count -- this module reads `response.read()` and decodes
        afterwards, so the count is taken over the wire payload rather than
        over a decoded string.

    no response was read       INDETERMINATE
        A timeout, a client error or any other transport failure. Whether the
        peer received and acted on the request is not known, so a retry may
        repeat an effect that already happened. Never FAILED: nothing here
        refused to send.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import (
    guarded_client_session,
    validate_url_with_env_config,
    SSRFError,
    ssrf_protection_enabled,
    guarded_aiohttp_request,
)


logger = logging.getLogger(__name__)


def _normalize_body(body: Any) -> str:
    """Coerce response body to a string for pattern matching."""
    if body is None:
        return ""
    if isinstance(body, (bytes, bytearray)):
        try:
            return body.decode("utf-8", errors="replace")
        except Exception:
            return str(body)
    if isinstance(body, str):
        return body
    try:
        import json
        return json.dumps(body, ensure_ascii=False)
    except Exception:
        return str(body)


async def _execute_single_request(
    session, req: Dict[str, Any], timeout_s: int, verify_ssl: bool
) -> Dict[str, Any]:
    """Execute one HTTP request from the batch spec, always returning a dict."""
    import aiohttp

    method = (req.get("method") or "GET").upper()
    url = req.get("url") or ""
    headers = dict(req.get("headers") or {})
    body = req.get("body")
    label = req.get("label")

    kwargs: Dict[str, Any] = {
        "headers": headers,
        "ssl": None if verify_ssl else False,
        "allow_redirects": req.get("follow_redirects", True),
    }
    if body is not None and method in ("POST", "PUT", "PATCH", "DELETE"):
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        else:
            kwargs["data"] = body

    # SECURITY: revalidate every redirect hop through the SSRF guard so a public
    # URL cannot 302 into internal space (GHSA-c9hr-64h3-gxpc).
    _follow = kwargs.pop("allow_redirects", True)
    start = time.time()
    try:
        response = await guarded_aiohttp_request(
            session, method, url, max_redirects=(5 if _follow else 0), **kwargs)
        try:
            raw_body = await response.read()
            try:
                text_body = raw_body.decode("utf-8", errors="replace")
            except Exception:
                text_body = str(raw_body)
            duration_ms = int((time.time() - start) * 1000)
            status = response.status
            return {
                "label": label,
                "method": method,
                "url": url,
                "status": status,
                "status_text": response.reason or "",
                "headers": dict(response.headers),
                "body": _normalize_body(text_body),
                "duration_ms": duration_ms,
                "ok": 200 <= status < 300,
                "error": None,
                # ACCEPTED on a non-2xx as well as a 2xx. The rung answers "how
                # far was this followed", not "did it succeed": a 500 is the
                # peer receiving the probe and choosing a reply just as much as
                # a 200 is, and for a pentest batch the 500 is often the point.
                # `ok` beside it carries the success question.
                "outcome": envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        "kind": "http_status_received",
                        "label": label,
                        "status": status,
                        "reason": response.reason or "",
                        "bytes_received": len(raw_body),
                        "measured_by": (
                            "response.status and len() over the bytes read off "
                            "the wire, before decoding"
                        ),
                    }],
                ),
            }
        finally:
            response.release()
    except asyncio.TimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        return _failed_request(label, method, url, duration_ms, "TIMEOUT",
                               f"timed out after {timeout_s}s")
    except aiohttp.ClientError as e:
        duration_ms = int((time.time() - start) * 1000)
        return _failed_request(label, method, url, duration_ms, "CLIENT_ERROR", str(e))
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return _failed_request(label, method, url, duration_ms, "REQUEST_ERROR", str(e))


def _failed_request(label, method, url, duration_ms, code, msg) -> Dict[str, Any]:
    """One request that produced no response.

    INDETERMINATE on all three codes this is called with, and the reason is the
    one `http.request` gives: no response was read, so whether the peer
    received and acted on the request is unknown. That is not a low rung, it is
    a different kind of answer, and it is the one that makes re-running a batch
    of POSTs a decision rather than a reflex. FAILED would mean "it did not
    happen", which nothing here established.
    """
    return {
        "label": label,
        "method": method,
        "url": url,
        "status": None,
        "status_text": "",
        "headers": {},
        "body": "",
        "duration_ms": duration_ms,
        "ok": False,
        "error": msg,
        "error_code": code,
        "outcome": envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.NONE,
            effects=[{
                "kind": "http_no_response",
                "label": label,
                "error_code": code,
                "measured_by": None,
                "detail": (
                    "No response was read. Whether the peer received and acted "
                    "on this request is not known, so a retry may repeat an "
                    "effect that already happened."
                ),
            }],
        ),
    }


def _compute_pattern_matches(
    results: List[Dict[str, Any]], patterns: List[str]
) -> List[Dict[str, Any]]:
    """Scan each result's body for each pattern, return per-pattern indices."""
    out = []
    for pat in patterns:
        indices = [i for i, r in enumerate(results) if pat.lower() in (r.get("body", "") or "").lower()]
        out.append({"pattern": pat, "matches": indices, "count": len(indices)})
    return out


@register_module(
    module_id='http.batch',
    version='1.0.0',
    category='atomic',
    subcategory='http',
    tags=['http', 'batch', 'pentest', 'atomic', 'ssrf_protected'],
    label='HTTP Batch',
    label_key='modules.http.batch.label',
    description='Run a batch of HTTP probes sequentially and capture timing + body',
    description_key='modules.http.batch.description',
    icon='Layers',
    color='#3B82F6',

    input_types=['object', 'array'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=120000,
    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['network.access'],

    params_schema={
        'requests': {
            'type': 'array',
            'required': True,
            'label': 'Requests',
            'description': 'List of request dicts: {method, url, headers?, body?, label?}',
        },
        'description': {
            'type': 'string',
            'required': False,
            'label': 'Description',
            'description': 'Informational description of the batch intent',
        },
        'measure_time': {
            'type': 'boolean',
            'required': False,
            'default': False,
            'label': 'Measure Time',
            'description': 'Execute requests sequentially for reliable timing comparison',
        },
        'timeout': {
            'type': 'number',
            'required': False,
            'default': 30,
            'label': 'Per-request timeout (seconds)',
        },
        'verify_ssl': {
            'type': 'boolean',
            'required': False,
            'default': True,
            'label': 'Verify SSL',
        },
        'ssrf_protection': {
            'type': 'boolean',
            'required': False,
            'default': True,
            'label': 'SSRF Protection',
        },
        'detect_patterns': {
            'type': 'array',
            'required': False,
            'label': 'Detect Patterns',
            'description': 'Optional list of substrings to report matches for across all bodies',
        },
    },
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the batch completed (does not imply all requests succeeded)'},
        'data': {
            'type': 'array',
            'description': (
                'Per-request results: [{label, status, body, duration_ms, ok, '
                'outcome, ...}]. Each entry carries its own outcome envelope: '
                '"accepted" when a status line came back (2xx or not), '
                '"indeterminate" when no response was read. There is no '
                'batch-level envelope -- a step is only as confirmed as its '
                'least confirmed request, and step_outcome computes that from '
                'these'
            ),
        },
        'count': {'type': 'number', 'description': 'Number of requests executed'},
        'failed_count': {'type': 'number', 'description': 'Number of requests that errored or returned non-2xx'},
        'total_duration_ms': {'type': 'number', 'description': 'Total elapsed ms across the batch'},
        'detected': {'type': 'array', 'description': 'Pattern match summary when detect_patterns provided'},
    },
    author='Flyto2 Team',
    license='MIT',
)
async def http_batch(context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a batch of HTTP requests, capturing per-request status + timing."""
    try:
        import aiohttp
    except ImportError:
        raise ImportError("aiohttp is required for http.batch")

    params = context['params']
    requests: List[Dict[str, Any]] = params.get('requests') or []
    if not isinstance(requests, list) or not requests:
        # FAILED, and this envelope is currently unreadable: `ok: False` makes
        # `wrap_legacy_result` build an ERROR result and drop the payload. It
        # is written anyway for the reason `http.request._error_result` gives --
        # the fact is true whether or not a consumer exists yet.
        return {'ok': False, 'data': [], 'count': 0, 'failed_count': 0,
                'total_duration_ms': 0, 'error': 'requests must be a non-empty list',
                'outcome': envelope(
                    Outcome.FAILED,
                    claim_by=ClaimBy.NONE,
                    effects=[{
                        'kind': 'batch_not_started',
                        'measured_by': None,
                        'detail': 'No requests were supplied; nothing was sent.',
                    }],
                )}

    measure_time = bool(params.get('measure_time', False))
    timeout_s = int(params.get('timeout', 30))
    verify_ssl = bool(params.get('verify_ssl', True))
    ssrf_on = ssrf_protection_enabled()  # operator-controlled, not client param
    patterns: List[str] = list(params.get('detect_patterns') or [])

    # SSRF gate — refuse any target that fails the project's URL validator
    if ssrf_on:
        for idx, req in enumerate(requests):
            url = req.get('url', '')
            try:
                validate_url_with_env_config(url)
            except SSRFError as e:
                logger.warning(f"http.batch SSRF blocked request {idx}: {url}")
                return {
                    'ok': False, 'data': [], 'count': 0, 'failed_count': 0,
                    'total_duration_ms': 0,
                    'error': f'SSRF blocked request {idx}: {e}',
                    'error_code': 'SSRF_BLOCKED',
                    # FAILED, not INDETERMINATE: the gate runs over every
                    # request before the session is opened, so no request in
                    # this batch was sent. Nothing reached any peer, which is
                    # knowable rather than unknown.
                    'outcome': envelope(
                        Outcome.FAILED,
                        claim_by=ClaimBy.NONE,
                        effects=[{
                            'kind': 'batch_refused_before_send',
                            'blocked_index': idx,
                            'measured_by': None,
                            'detail': (
                                'The SSRF gate refused a target before the '
                                'session was opened. No request in this batch '
                                'left this machine.'
                            ),
                        }],
                    ),
                }

    timeout = aiohttp.ClientTimeout(total=timeout_s)
    batch_start = time.time()

    async with guarded_client_session(timeout=timeout) as session:
        if measure_time:
            results = []
            for req in requests:
                r = await _execute_single_request(session, req, timeout_s, verify_ssl)
                results.append(r)
        else:
            coros = [_execute_single_request(session, req, timeout_s, verify_ssl)
                     for req in requests]
            results = await asyncio.gather(*coros)

    total_duration_ms = int((time.time() - batch_start) * 1000)
    failed_count = sum(1 for r in results if not r.get('ok'))

    out: Dict[str, Any] = {
        'ok': True,
        'data': results,
        'count': len(results),
        'failed_count': failed_count,
        'total_duration_ms': total_duration_ms,
    }
    if patterns:
        out['detected'] = _compute_pattern_matches(results, patterns)

    logger.info(
        f"http.batch: {len(results)} requests, {failed_count} failed, "
        f"{total_duration_ms}ms total"
    )
    return out
