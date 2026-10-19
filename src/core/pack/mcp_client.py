# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The smallest MCP client a consumer needs: Streamable HTTP, three methods.

A Flyto2 Space can use an external MCP server's tools as capabilities. This
module is the runtime half that reaches the server: ``initialize`` (and the
``notifications/initialized`` that completes it), ``tools/list`` and
``tools/call``, over one Streamable HTTP endpoint, answered either as JSON or
as an event stream. It is written here rather than taken from the ``mcp``
SDK because these three exchanges are all a consumer sends, and the SDK would
bring its own HTTP stack past the platform SSRF guard.

It reuses the connector runtime's vocabulary of typed failures
(:data:`core.pack.connector_runtime.STATUS_FAILURES`, :class:`ConnectorCallError`)
and its outbound path (the SSRF guard and the DNS-rebinding-guarded session,
no redirects followed). It adds the failures only MCP has
(:data:`MCP_FAILURES`): a tool that answered ``isError``, and a JSON-RPC error.

Three rules hold here and nowhere else needs to repeat them:

* **No token passthrough.** The only credential a request carries is the one
  the caller resolved for this server's own resource (``credential``). The
  client takes no caller headers at all, so a token issued to Flyto2 (an MCP
  client's, ChatGPT's, a user's session) cannot ride along.
* **A refusal is final.** A server that answered 401, 403 or ``isError`` is
  not retried, and the failure says so (``final``).
* **Never an empty success.** Every failure is ``{"ok": False, "error_code"}``.

Discovery facts are normalized here (:func:`normalize_tools`): name, input
schema and the four behaviour hints, with a digest of exactly those. What a
hint *means* for consequence is decided by the platform that consumes them,
never here: facts go down, judgement stays up.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .connector_runtime import ConnectorCallError, status_failure

logger = logging.getLogger(__name__)

__all__ = [
    "MCP_FAILURES",
    "FINAL_FAILURES",
    "HINT_KEYS",
    "PROTOCOL_VERSION",
    "McpClient",
    "normalize_tools",
    "tool_digest",
]

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "flyto2", "version": "1"}

#: The behaviour hints MCP tool annotations carry. Read as hints only.
HINT_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

#: Failures only MCP has, beside the connector runtime's ``PROVIDER_*`` codes.
MCP_FAILURES: Mapping[str, str] = {
    "MCP_TOOL_ERROR": "the tool ran and answered isError",
    "MCP_RPC_ERROR": "the server answered a JSON-RPC error",
    "MCP_METHOD_UNSUPPORTED": "the server does not implement the method",
    "MCP_INVALID_PARAMS": "the server refused the tool name or its arguments",
    "MCP_TOOL_MALFORMED": "a listed tool has no name or no object input schema",
    "MCP_TOO_MANY_PAGES": "tools/list kept paging past the bound",
}

#: JSON-RPC error code -> typed failure; any other code is ``MCP_RPC_ERROR``.
_RPC_FAILURES: Mapping[int, str] = {-32601: "MCP_METHOD_UNSUPPORTED", -32602: "MCP_INVALID_PARAMS"}

#: Failures that are the server's answer, not a fault on the way: never retried.
FINAL_FAILURES = frozenset({
    "PROVIDER_UNAUTHORIZED", "PROVIDER_FORBIDDEN", "PROVIDER_REJECTED", "PROVIDER_NOT_FOUND",
    "MCP_TOOL_ERROR", "MCP_INVALID_PARAMS", "MCP_METHOD_UNSUPPORTED", "CREDENTIAL_MISSING",
    "PROVIDER_REDIRECT_REFUSED", "SSRF_BLOCKED",
})

_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_LIST_PAGES = 20
_MAX_TOOLS = 256
_DEFAULT_TIMEOUT_MS = 30_000

#: ``send(method, url, headers, body, timeout_ms) -> (status, headers, raw)``.
Send = Callable[[str, str, Mapping[str, str], Optional[bytes], int], Awaitable[Tuple[int, Mapping[str, str], bytes]]]


# -- discovery facts -------------------------------------------------------------


def tool_digest(tool: Mapping[str, Any]) -> str:
    """sha256 of what a tool is: its name, description, input schema and hints."""
    payload = {
        "name": tool.get("name"),
        "description": tool.get("description") or "",
        "input_schema": tool.get("input_schema") or {},
        "hints": tool.get("hints") or {},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _hints(annotations: Any) -> Dict[str, bool]:
    if not isinstance(annotations, Mapping):
        return {}
    return {key: annotations[key] for key in HINT_KEYS if isinstance(annotations.get(key), bool)}


def _normalized(raw: Any) -> Dict[str, Any]:
    name = raw.get("name") if isinstance(raw, Mapping) else None
    schema = raw.get("inputSchema", {"type": "object"}) if isinstance(raw, Mapping) else None
    if not isinstance(name, str) or not name.strip() or not isinstance(schema, Mapping):
        return {"name": name if isinstance(name, str) else "", "refused": "MCP_TOOL_MALFORMED"}
    tool = {
        "name": name.strip()[:128],
        "title": str(raw.get("title") or (raw.get("annotations") or {}).get("title") or "")[:200],
        "description": str(raw.get("description") or "")[:1000],
        "input_schema": dict(schema),
        "hints": _hints(raw.get("annotations")),
    }
    tool["digest"] = tool_digest(tool)
    return tool


def normalize_tools(raw_tools: Any) -> List[Dict[str, Any]]:
    """Each listed tool as facts; a malformed one is named (``refused``), never dropped."""
    if not isinstance(raw_tools, list):
        return []
    return [_normalized(item) for item in raw_tools[:_MAX_TOOLS]]


# -- transport ---------------------------------------------------------------------


async def guarded_send(method: str, url: str, headers: Mapping[str, str], body: Optional[bytes],
                       timeout_ms: int) -> Tuple[int, Mapping[str, str], bytes]:
    """One request through the platform SSRF guard, no redirects followed."""
    import aiohttp

    from ..utils import SSRFError, guarded_client_session, validate_url_with_env_config

    try:
        validate_url_with_env_config(url)
    except SSRFError as error:
        raise ConnectorCallError("SSRF_BLOCKED", f"outbound address refused: {error}") from None
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000.0)
        async with guarded_client_session(timeout=timeout) as session, session.request(
            method, url, headers=dict(headers), data=body, allow_redirects=False
        ) as response:
            raw = await response.content.read(_MAX_RESPONSE_BYTES + 1)
            return response.status, dict(response.headers), raw
    except SSRFError as error:
        raise ConnectorCallError("SSRF_BLOCKED", f"outbound address refused: {error}") from None
    except asyncio.TimeoutError:
        raise ConnectorCallError("PROVIDER_TIMEOUT", f"no answer within {timeout_ms} ms") from None
    except aiohttp.ClientConnectionError as error:
        raise ConnectorCallError("PROVIDER_UNREACHABLE", f"could not reach the server: {type(error).__name__}") \
            from None
    except aiohttp.ClientError as error:
        raise ConnectorCallError("PROVIDER_TRANSPORT_ERROR", f"request failed: {type(error).__name__}") from None


def _event_messages(raw: bytes) -> List[Any]:
    """The JSON messages of an event stream body, in order."""
    messages: List[Any] = []
    for block in raw.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in block.split("\n") if line.startswith("data:"))
        if data:
            messages.append(json.loads(data))
    return messages


def _messages(headers: Mapping[str, str], raw: bytes) -> List[Any]:
    kind = next((value for name, value in headers.items() if name.lower() == "content-type"), "")
    try:
        if "text/event-stream" in kind:
            return _event_messages(raw)
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ConnectorCallError("PROVIDER_INVALID_RESPONSE", "the response is not JSON-RPC") from None
    return decoded if isinstance(decoded, list) else [decoded]


def _header(headers: Mapping[str, str], wanted: str) -> str:
    return next((str(value) for name, value in headers.items() if name.lower() == wanted.lower()), "")


# -- the client ----------------------------------------------------------------------


class McpClient:
    """One MCP server, reached with the credential held for its own resource.

    ``credential`` is the access token Flyto2 holds for this server (a static
    token by name, or one Flyto2's own OAuth flow obtained for this server's
    audience). There is deliberately no ``headers`` argument.
    """

    def __init__(self, url: str, *, credential: Optional[str], credential_required: bool = False,
                 timeout_ms: int = _DEFAULT_TIMEOUT_MS, send: Optional[Send] = None) -> None:
        self.url = url
        self._credential = credential or None
        self._credential_required = credential_required
        self._timeout_ms = max(100, min(int(timeout_ms), 120_000))
        self._send = send or guarded_send
        self._origin = urlsplit(url)[:2]
        self._session = ""
        self._version = PROTOCOL_VERSION
        self._ids = 0

    # -- public operations -------------------------------------------------------

    async def list_tools(self) -> Dict[str, Any]:
        return await self._operation(self._list_tools)

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._operation(lambda: self._call_tool(name, arguments))

    # -- internals -----------------------------------------------------------------

    async def _operation(self, body: Callable[[], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
        try:
            if self._credential_required and not self._credential:
                raise ConnectorCallError("CREDENTIAL_MISSING", "this server needs a credential; none is held")
            await self._initialize()
            data = await body()
        except ConnectorCallError as failure:
            logger.info("MCP request to %s failed: %s", self._origin[1], failure.code)
            return self._failure(failure)
        return {"ok": True, "data": data}

    def _failure(self, failure: ConnectorCallError) -> Dict[str, Any]:
        result = failure.result()
        if self._credential:
            result["error"] = result["error"].replace(self._credential, "[credential]")
        result["final"] = failure.code in FINAL_FAILURES
        return result

    async def _initialize(self) -> None:
        result = await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO,
        })
        version = result.get("protocolVersion") if isinstance(result, Mapping) else None
        self._version = version if isinstance(version, str) and version else PROTOCOL_VERSION
        await self._notify("notifications/initialized")

    async def _list_tools(self) -> Dict[str, Any]:
        tools: List[Any] = []
        cursor: Optional[str] = None
        for _ in range(_MAX_LIST_PAGES):
            page = await self._request("tools/list", {"cursor": cursor} if cursor else {})
            listed = page.get("tools") if isinstance(page, Mapping) else None
            tools.extend(listed if isinstance(listed, list) else [])
            cursor = page.get("nextCursor") if isinstance(page, Mapping) else None
            if not cursor:
                return {"tools": normalize_tools(tools)}
        raise ConnectorCallError("MCP_TOO_MANY_PAGES", f"tools/list paged past {_MAX_LIST_PAGES} pages")

    async def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        result = await self._request("tools/call", {"name": name, "arguments": dict(arguments or {})})
        if not isinstance(result, Mapping):
            raise ConnectorCallError("PROVIDER_INVALID_RESPONSE", "tools/call answered no result object")
        content = result.get("content") if isinstance(result.get("content"), list) else []
        if result.get("isError") is True:
            words = " ".join(str(item.get("text") or "") for item in content if isinstance(item, Mapping))
            raise ConnectorCallError("MCP_TOOL_ERROR", (words or "the tool reported an error")[:500])
        data: Dict[str, Any] = {"content": content}
        if isinstance(result.get("structuredContent"), Mapping):
            data["structured_content"] = dict(result["structuredContent"])
        return data

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if self._credential:
            headers["Authorization"] = f"Bearer {self._credential}"
        if self._session:
            headers["Mcp-Session-Id"] = self._session
            headers["MCP-Protocol-Version"] = self._version
        return headers

    async def _post(self, message: Mapping[str, Any]) -> Tuple[int, Mapping[str, str], bytes]:
        status, headers, raw = await self._send(
            "POST", self.url, self._headers(), json.dumps(message).encode(), self._timeout_ms)
        if not 200 <= status <= 299:
            raise ConnectorCallError(status_failure(status), f"the server answered HTTP {status}", http_status=status)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ConnectorCallError("PROVIDER_RESPONSE_TOO_LARGE", "the response exceeds the bound")
        session = _header(headers, "Mcp-Session-Id")
        if session:
            self._session = session[:256]
        return status, headers, raw

    async def _notify(self, method: str) -> None:
        await self._post({"jsonrpc": "2.0", "method": method})

    async def _request(self, method: str, params: Mapping[str, Any]) -> Any:
        self._ids += 1
        request_id = self._ids
        _, headers, raw = await self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        answer = next((item for item in _messages(headers, raw)
                       if isinstance(item, Mapping) and item.get("id") == request_id), None)
        if answer is None:
            raise ConnectorCallError("PROVIDER_INVALID_RESPONSE", f"no answer to {method}")
        error = answer.get("error")
        if isinstance(error, Mapping):
            code = error.get("code")
            failure = _RPC_FAILURES.get(code, "MCP_RPC_ERROR") if isinstance(code, int) else "MCP_RPC_ERROR"
            raise ConnectorCallError(failure, f"{method}: {str(error.get('message') or '')[:300]}")
        return answer.get("result")
