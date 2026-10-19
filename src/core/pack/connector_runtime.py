# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The one runtime every connector operation runs on.

No code is generated per provider or per operation. A connector pack's
operations are registered as modules (``core.pack.host``), and each call
lands here with the operation's normalized declaration. This module:

1. resolves the credential the pack names, through the execution context's
   ``secrets`` layer (by name; the pack never holds a value), and fails closed
   before any request when it is absent;
2. builds the request: path parameters encoded as one segment each, the other
   inputs in the query or the JSON body as declared;
3. waits on the pack's rate limit, one limiter shared by all its operations;
4. runs the pre-check (``core.pack.connector_gate.admit``): the features the
   operation requires, the data scope of its inputs, and its quota, against
   the provider's own entitlement answer and the caller's ``scope_grants``;
5. paginates with the declared ``http.paginate`` shape, then filters the
   answer by ``result_scope``;
6. returns the body as ``{"ok": true, "data": ...}``, or a typed failure —
   ``PROVIDER_UNAUTHORIZED``, ``PROVIDER_RATE_LIMITED``, ``PROVIDER_ERROR``
   and the rest of :data:`STATUS_FAILURES` — never an empty success.

The provider stays the authority on its own product: the pre-check can only
stop a call, and a provider refusal of an admitted call comes back as its own
typed failure. A refused call is never retried.

The only credential sent is the one the pack names, resolved from
``secrets``. Nothing else in the execution context (an inbound client's
bearer token, request headers) reaches the provider.

Outbound requests go through the platform SSRF guard
(``validate_url_with_env_config`` and the DNS-rebinding-guarded connector),
follow no redirects, and send the credential only to the pack's own origin.

``sensitive`` paths are not applied here: the module result keeps every
value, because the workflow needs them. The step log and the trace apply
them through ``BaseModule.sensitive_result_paths``
(:func:`sensitive_result_paths` computes them for one result).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import quote, urlencode, urlsplit

from .connector import BODY_METHODS, module_id_for
from .connector_gate import (
    DEFAULT_MAX_AGE_S,
    EntitlementAnswer,
    EntitlementCache,
    PrecheckError,
    admit,
    filter_result,
    missing_features,
    needs_entitlements,
    needs_fresh_read,
    read_answer,
    scope_dimensions,
)
from .jsonpath import expand, parse

logger = logging.getLogger(__name__)

__all__ = ["STATUS_FAILURES", "ConnectorCallError", "ConnectorTransport", "sensitive_result_paths"]

#: HTTP status -> the typed failure a module returns. The first matching row
#: wins; a status no row covers is ``PROVIDER_UNEXPECTED_STATUS``.
STATUS_FAILURES: Tuple[Tuple[int, int, str], ...] = (
    (401, 401, "PROVIDER_UNAUTHORIZED"),
    (403, 403, "PROVIDER_FORBIDDEN"),
    (402, 402, "PROVIDER_QUOTA_REFUSED"),
    (404, 404, "PROVIDER_NOT_FOUND"),
    (429, 429, "PROVIDER_RATE_LIMITED"),
    (300, 399, "PROVIDER_REDIRECT_REFUSED"),
    (400, 499, "PROVIDER_REJECTED"),
    (500, 599, "PROVIDER_ERROR"),
)

_TOKEN_EARLY_EXPIRY_S = 30


class ConnectorCallError(Exception):
    """A call that did not succeed, as the module result that says so."""

    def __init__(self, code: str, message: str, *, http_status: Optional[int] = None,
                 retry_after_s: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retry_after_s = retry_after_s

    def result(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"ok": False, "error": str(self), "error_code": self.code}
        if self.http_status is not None:
            out["http_status"] = self.http_status
        if self.retry_after_s is not None:
            out["retry_after_s"] = self.retry_after_s
        return out


def _status_failure(status: int) -> str:
    for low, high, code in STATUS_FAILURES:
        if low <= status <= high:
            return code
    return "PROVIDER_UNEXPECTED_STATUS"


def _retry_after(value: Optional[str]) -> Optional[int]:
    if value and value.strip().isdigit():
        return min(int(value.strip()), 86_400)
    return None


# -- sensitive paths -------------------------------------------------------------


def sensitive_result_paths(parsed: Tuple[Tuple[Any, ...], ...], result: Any) -> frozenset:
    """The concrete paths into a module result that the operation marks sensitive.

    A declared path is rooted at the operation's data (the response body, or
    ``{"items", "pages_fetched"}`` for a paginated operation), which sits
    under ``data`` in the module result.
    """
    if not isinstance(result, dict) or "data" not in result:
        return frozenset()
    return frozenset(("data", *path) for steps in parsed for path in expand(steps, result["data"]) if path)


def parse_sensitive(paths: List[str]) -> Tuple[Tuple[Any, ...], ...]:
    return tuple(parse(path) for path in paths)


# -- credentials -------------------------------------------------------------------


def _mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            decoded = json.loads(value)
        except ValueError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def _basic(value: Any) -> str:
    """``user:password``. A bare token is the user name with an empty password."""
    pair = _mapping(value)
    if pair is not None:
        text = f"{pair.get('username', '')}:{pair.get('password', '')}"
    else:
        text = value if ":" in value else f"{value}:"
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


#: How a scheme encodes the credential value; any other scheme is a prefix.
_SCHEME_ENCODERS: Mapping[str, Callable[[Any], str]] = {"basic": _basic}


@dataclass
class _Token:
    value: str
    expires_at: float


@dataclass
class ConnectorTransport:
    """The calls of one installed connector pack."""

    pack_id: str
    namespace: str
    connector: Mapping[str, Any]
    runtime: Mapping[str, Any]
    #: The pack's normalized ``entitlements`` section, or None when it has none.
    entitlements: Optional[Mapping[str, Any]] = None
    _operations: Dict[str, Mapping[str, Any]] = field(default_factory=dict, repr=False)
    _limiter: Any = field(default=None, repr=False)
    _tokens: Dict[str, _Token] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._operations = {module_id_for(self.namespace, op["id"]): op for op in self.connector["operations"]}
        limit = self.connector.get("rate_limit")
        if limit:
            from ..modules.integrations.base.rate_limiter import RateLimiter

            self._limiter = RateLimiter(calls=limit["requests"], period=limit["per_seconds"])
        origin = urlsplit(self.connector["base_url"])
        self._origin = (origin.scheme, origin.hostname, origin.port)
        max_age = (self.entitlements or {}).get("max_age_s", DEFAULT_MAX_AGE_S)
        self._entitlement_cache = EntitlementCache(max_age_s=max_age)

    def operation(self, module_id: str) -> Optional[Mapping[str, Any]]:
        return self._operations.get(module_id)

    async def close(self) -> None:
        self._tokens.clear()
        self._entitlement_cache.clear()

    def _budget(self, timeout_ms: Optional[int]) -> int:
        return min(timeout_ms or self.runtime["request_timeout_ms"], self.runtime["request_timeout_ms"])

    # -- the call ------------------------------------------------------------------

    async def call(self, module_id: str, params: Mapping[str, Any], secrets: Mapping[str, Any],
                   timeout_ms: Optional[int], scope_grants: Any = None) -> Dict[str, Any]:
        op = self._operations.get(module_id)
        if op is None:
            return ConnectorCallError("OPERATION_UNKNOWN", f"{module_id} is not an operation of {self.pack_id}").result()
        budget_ms = self._budget(timeout_ms)
        key = None
        try:
            headers, key = await self._headers(module_id, secrets, budget_ms)
            admission = await self._precheck(op, params, scope_grants, headers, key, budget_ms)
            data = await self._execute(op, params, headers, budget_ms)
            data, scope = filter_result(op, data, admission.grants)
        except PrecheckError as refusal:
            logger.info("Connector call %s refused by the pre-check: %s", module_id, refusal.code)
            return refusal.result()
        except ConnectorCallError as failure:
            logger.info("Connector call %s failed: %s", module_id, failure.code)
            if key is not None and failure.http_status is not None:
                # Whatever the provider refused, the next call asks it again.
                self._entitlement_cache.provider_error(key)
            return failure.result()
        if not needs_entitlements(op) and not scope_dimensions(op):
            return {"ok": True, "data": data}
        precheck: Dict[str, Any] = {"entitlements": admission.entitlements, "features": list(admission.features)}
        if scope is not None:
            precheck["scope"] = scope
        if admission.meter is not None:
            precheck["meter"] = await self._meter_after(admission.meter, headers, key, budget_ms)
        return {"ok": True, "data": data, "metadata": {"precheck": precheck}}

    async def _execute(self, op: Mapping[str, Any], params: Mapping[str, Any], headers: Mapping[str, str],
                       budget_ms: int) -> Any:
        url, query, body = self._request_parts(op, params)
        if op["paginate"] is not None:
            return await self._paginate(op, url, query, body, headers, budget_ms)
        data, _ = await self._send(op["method"], url, query, body, headers, budget_ms)
        return data

    # -- the pre-check -------------------------------------------------------------

    async def _precheck(self, op: Mapping[str, Any], params: Mapping[str, Any], scope_grants: Any,
                        headers: Mapping[str, str], key: str, budget_ms: int):
        answer, source = None, "not_required"
        if needs_entitlements(op):
            answer, source = await self._entitlements(headers, key, budget_ms, fresh=needs_fresh_read(op))
        return admit(op, params, scope_grants, answer, source)

    async def _entitlements(self, headers: Mapping[str, str], key: str, budget_ms: int,
                            *, fresh: bool) -> Tuple[EntitlementAnswer, str]:
        """The provider's answer for this credential: cached for a read, read again otherwise."""
        if not fresh:
            cached = self._entitlement_cache.fresh(key)
            if cached is not None:
                return cached, "cache"
        probe = self._operations[module_id_for(self.namespace, self.entitlements["probe"])]
        try:
            answer = read_answer(self.entitlements, await self._execute(probe, {}, headers, budget_ms))
        except (ConnectorCallError, PrecheckError) as failure:
            # A failed read never falls back to the last good answer.
            self._entitlement_cache.drop(key)
            raise PrecheckError("PROVIDER_ENTITLEMENT_UNREADABLE",
                              f"the provider's entitlements could not be read ({failure.code})",
                              probe_error=failure.code) from None
        self._entitlement_cache.store(key, answer)
        return answer, "provider"

    async def _meter_after(self, meter: Mapping[str, Any], headers: Mapping[str, str], key: str,
                           budget_ms: int) -> Dict[str, Any]:
        """The meter read again after the call; a mismatch with the declared amount is a finding."""
        out = dict(meter)
        try:
            answer, _ = await self._entitlements(headers, key, budget_ms, fresh=True)
        except PrecheckError:
            out.update(after=None, matches=None)
            return out
        out["after"] = answer.meters[meter["meter"]]
        out["matches"] = meter["before"] - out["after"] == meter["amount"]
        return out

    async def effective_module_ids(self, secrets: Mapping[str, Any]) -> List[str]:
        """The operations this credential is entitled to, by the probe (a cached answer may serve).

        An operation that needs no feature is always listed. A gated one is
        listed only when the answer is readable and holds its features; the
        rest are omitted, not marked.
        """
        budget_ms = self._budget(None)
        answer: Optional[EntitlementAnswer] = None
        offered = []
        for module_id, op in sorted(self._operations.items()):
            if not needs_entitlements(op):
                offered.append(module_id)
                continue
            if answer is None:
                try:
                    headers, key = await self._headers(module_id, secrets, budget_ms)
                    answer, _ = await self._entitlements(headers, key, budget_ms, fresh=False)
                except (PrecheckError, ConnectorCallError):
                    return [m for m, o in sorted(self._operations.items()) if not needs_entitlements(o)]
            if not missing_features((op.get("requires") or {}).get("features") or [], answer.features):
                offered.append(module_id)
        return offered

    def _request_parts(self, op: Mapping[str, Any], params: Mapping[str, Any]) -> Tuple[str, Dict, Optional[Dict]]:
        path = op["path"]
        query: Dict[str, Any] = {}
        body: Dict[str, Any] = {}
        for name, spec in op["inputs"].items():
            if params.get(name) is None:
                continue
            value = params[name]
            if spec["in"] == "path":
                path = path.replace("{" + name + "}", quote(_scalar(value), safe=""))
            elif spec["in"] == "query":
                query[name] = value
            else:
                body[name] = value
        # A path placeholder left unfilled would send a request for a
        # different resource; the schema marks path inputs required, and this
        # holds even if a caller bypassed it.
        if "{" in path:
            raise ConnectorCallError("INPUT_MISSING", "a path parameter has no value")
        has_body = op["method"] in BODY_METHODS
        return self.connector["base_url"] + path, query, (body if has_body else None)

    # -- auth ------------------------------------------------------------------------

    async def _headers(self, module_id: str, secrets: Mapping[str, Any],
                       budget_ms: int) -> Tuple[Dict[str, str], str]:
        """The request headers, and the key the credential's entitlement answer is cached under."""
        auth = self.connector["auth"]
        if not auth:
            return {"Accept": "application/json"}, EntitlementCache.key("", None)
        for entry in auth:
            value = secrets.get(entry["credential"]) if isinstance(secrets, Mapping) else None
            if value not in (None, ""):
                headers = await _AUTH_KINDS[entry["kind"]](self, entry, value, budget_ms)
                return {"Accept": "application/json", **headers}, EntitlementCache.key(entry["credential"], value)
        names = ", ".join(entry["credential"] for entry in auth)
        raise ConnectorCallError("CREDENTIAL_MISSING", f"{module_id} needs credential {names}; the host supplied none")

    async def _api_token(self, entry: Mapping[str, Any], value: Any, budget_ms: int) -> Dict[str, str]:
        scheme = entry.get("scheme")
        if not isinstance(value, (str, Mapping)):
            raise ConnectorCallError("CREDENTIAL_INVALID", f"credential {entry['credential']} is not a token")
        encoder = _SCHEME_ENCODERS.get((scheme or "").lower())
        if encoder is not None:
            return {entry["header"]: f"{scheme} {encoder(value)}"}
        if not isinstance(value, str):
            raise ConnectorCallError("CREDENTIAL_INVALID", f"credential {entry['credential']} is not a token")
        return {entry["header"]: f"{scheme} {value}" if scheme else value}

    async def _authorization_code(self, entry: Mapping[str, Any], value: Any, budget_ms: int) -> Dict[str, str]:
        # The host runs the authorization dance and keeps the token fresh; the
        # credential it resolves is the current access token.
        pair = _mapping(value)
        token = pair.get("access_token") if pair is not None else value
        if not isinstance(token, str) or not token:
            raise ConnectorCallError("CREDENTIAL_INVALID", f"credential {entry['credential']} has no access token")
        return {"Authorization": f"Bearer {token}"}

    async def _client_credentials(self, entry: Mapping[str, Any], value: Any, budget_ms: int) -> Dict[str, str]:
        cached = self._tokens.get(entry["credential"])
        if cached is not None and cached.expires_at > time.monotonic():
            return {"Authorization": f"Bearer {cached.value}"}
        pair = _mapping(value)
        if pair is None or not pair.get("client_id") or not pair.get("client_secret"):
            raise ConnectorCallError("CREDENTIAL_INVALID",
                                   f"credential {entry['credential']} needs client_id and client_secret")
        form = {"grant_type": "client_credentials", "client_id": pair["client_id"],
                "client_secret": pair["client_secret"]}
        if entry.get("scopes"):
            form["scope"] = " ".join(entry["scopes"])
        try:
            answer, _ = await self._send("POST", entry["token_url"], {}, None,
                                         {"Accept": "application/json"}, budget_ms, form=form, limited=False,
                                         any_origin=True)
        except ConnectorCallError as failure:
            raise ConnectorCallError("CREDENTIAL_REJECTED", f"the token endpoint refused credential "
                                   f"{entry['credential']} ({failure.code})", http_status=failure.http_status) from None
        token = answer.get("access_token") if isinstance(answer, dict) else None
        if not isinstance(token, str) or not token:
            raise ConnectorCallError("CREDENTIAL_REJECTED", "the token endpoint returned no access_token")
        lifetime = answer.get("expires_in") if isinstance(answer.get("expires_in"), int) else 300
        self._tokens[entry["credential"]] = _Token(token, time.monotonic() + max(lifetime - _TOKEN_EARLY_EXPIRY_S, 1))
        return {"Authorization": f"Bearer {token}"}

    # -- HTTP --------------------------------------------------------------------------

    def _check_origin(self, url: str) -> None:
        parts = urlsplit(url)
        if (parts.scheme, parts.hostname, parts.port) != self._origin:
            raise ConnectorCallError("PROVIDER_REDIRECT_REFUSED", "the provider pointed a page at another origin")

    async def _send(self, method: str, url: str, query: Mapping[str, Any], body: Optional[Mapping[str, Any]],
                    headers: Mapping[str, str], budget_ms: int, *, form: Optional[Mapping[str, str]] = None,
                    limited: bool = True, any_origin: bool = False) -> Tuple[Any, Mapping[str, str]]:
        import aiohttp
        from yarl import URL

        from ..utils import SSRFError, guarded_client_session, validate_url_with_env_config

        if not any_origin:
            self._check_origin(url)
        if query:
            url = f"{url}?{urlencode({k: _query_value(v) for k, v in query.items()}, doseq=True)}"
        try:
            validate_url_with_env_config(url)
        except SSRFError as error:
            raise ConnectorCallError("SSRF_BLOCKED", f"outbound address refused: {error}") from None
        if limited and self._limiter is not None:
            await self._limiter.acquire()
        max_bytes = self.runtime["max_response_bytes"]
        kwargs: Dict[str, Any] = {"headers": dict(headers), "allow_redirects": False}
        if form is not None:
            kwargs["data"] = dict(form)
        elif body is not None:
            kwargs["json"] = dict(body)
        try:
            timeout = aiohttp.ClientTimeout(total=budget_ms / 1000.0)
            async with guarded_client_session(timeout=timeout) as session, session.request(
                method, URL(url, encoded=True), **kwargs
            ) as response:
                raw = await response.content.read(max_bytes + 1)
                status, reply_headers = response.status, dict(response.headers)
        except SSRFError as error:
            raise ConnectorCallError("SSRF_BLOCKED", f"outbound address refused: {error}") from None
        except asyncio.TimeoutError:
            raise ConnectorCallError("PROVIDER_TIMEOUT", f"no answer within {budget_ms} ms") from None
        except aiohttp.ClientConnectionError as error:
            raise ConnectorCallError("PROVIDER_UNREACHABLE", f"could not reach the provider: {type(error).__name__}") \
                from None
        except aiohttp.ClientError as error:
            raise ConnectorCallError("PROVIDER_TRANSPORT_ERROR", f"request failed: {type(error).__name__}") from None
        if not 200 <= status <= 299:
            raise ConnectorCallError(_status_failure(status), f"the provider answered HTTP {status}",
                                   http_status=status, retry_after_s=_retry_after(reply_headers.get("Retry-After")))
        if len(raw) > max_bytes:
            raise ConnectorCallError("PROVIDER_RESPONSE_TOO_LARGE", "the response exceeds runtime.max_response_bytes",
                                   http_status=status)
        if not raw.strip():
            return None, reply_headers
        try:
            return json.loads(raw.decode("utf-8")), reply_headers
        except (UnicodeDecodeError, ValueError):
            raise ConnectorCallError("PROVIDER_INVALID_RESPONSE", "the response body is not JSON",
                                   http_status=status) from None

    # -- pagination --------------------------------------------------------------------

    async def _paginate(self, op: Mapping[str, Any], url: str, query: Mapping[str, Any],
                        body: Optional[Mapping[str, Any]], headers: Mapping[str, str], budget_ms: int) -> Dict:
        shape = op["paginate"]
        strategy = _STRATEGIES[shape["strategy"]]
        state = strategy.first(shape)
        items: List[Any] = []
        pages = 0
        while state is not None and pages < shape["max_pages"]:
            # A Link-header page is a whole URL; any other page is the
            # operation URL with the strategy's query on top of the inputs.
            page_url = state.get("__url__")
            page_query = {} if page_url else {**query, **state}
            page, reply_headers = await self._send(op["method"], page_url or url, page_query, body, headers,
                                                   budget_ms)
            found = _items(page, shape["data_path"])
            items.extend(found)
            pages += 1
            state = strategy.advance(shape, state, page, found, reply_headers)
        return {"items": items, "pages_fetched": pages}


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _query_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_scalar(item) for item in value]
    if isinstance(value, (dict,)):
        return json.dumps(value, separators=(",", ":"))
    return _scalar(value)


def _dot(document: Any, path: str) -> Any:
    """``http.paginate``'s dot-notation lookup (``meta.next_cursor``)."""
    if not path:
        return document
    from ..engine.variable_resolver import VariableResolver

    return VariableResolver.get_nested_value(document, path)


def _items(page: Any, data_path: str) -> List[Any]:
    found = _dot(page, data_path)
    if isinstance(found, list):
        return found
    return [] if found is None else [found]


def _next_link(header: str) -> Optional[str]:
    for part in (header or "").split(","):
        target, _, params = part.partition(";")
        if 'rel="next"' in params or "rel=next" in params:
            target = target.strip()
            if target.startswith("<") and target.endswith(">"):
                return target[1:-1]
    return None


class _Offset:
    @staticmethod
    def first(shape: Mapping[str, Any]) -> Dict[str, Any]:
        return {shape["offset_param"]: 0, shape["limit_param"]: shape["page_size"]}

    @staticmethod
    def advance(shape, state, page, found, headers) -> Optional[Dict[str, Any]]:
        if len(found) < shape["page_size"] or not found:
            return None
        return {**state, shape["offset_param"]: state[shape["offset_param"]] + shape["page_size"]}


class _Page:
    @staticmethod
    def first(shape: Mapping[str, Any]) -> Dict[str, Any]:
        state = {shape["page_param"]: shape["start_page"]}
        if shape["page_size"]:
            state[shape["limit_param"]] = shape["page_size"]
        return state

    @staticmethod
    def advance(shape, state, page, found, headers) -> Optional[Dict[str, Any]]:
        if not found:
            return None
        return {**state, shape["page_param"]: state[shape["page_param"]] + 1}


class _Cursor:
    @staticmethod
    def first(shape: Mapping[str, Any]) -> Dict[str, Any]:
        return {"limit": shape["page_size"]} if shape["page_size"] else {}

    @staticmethod
    def advance(shape, state, page, found, headers) -> Optional[Dict[str, Any]]:
        cursor = _dot(page, shape["cursor_path"])
        if not cursor or not found:
            return None
        return {**state, shape["cursor_param"]: cursor}


class _LinkHeader:
    @staticmethod
    def first(shape: Mapping[str, Any]) -> Dict[str, Any]:
        return {"per_page": shape["page_size"]} if shape["page_size"] else {}

    @staticmethod
    def advance(shape, state, page, found, headers) -> Optional[Dict[str, Any]]:
        target = _next_link(headers.get("Link", ""))
        if not target or not found:
            return None
        # The next URL carries its own query; the credential still goes only
        # to the pack's origin (``_send`` checks it).
        return {"__url__": target}


#: The ``http.paginate`` strategies, by the name a declaration uses.
_STRATEGIES = {"offset": _Offset, "page": _Page, "cursor": _Cursor, "link_header": _LinkHeader}

#: Auth kind -> how a resolved credential becomes request headers.
_AUTH_KINDS = {
    "api_token": ConnectorTransport._api_token,
    "oauth2_client_credentials": ConnectorTransport._client_credentials,
    "oauth2_authorization_code": ConnectorTransport._authorization_code,
}
