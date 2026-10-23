# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""OAuth 2.1 authorization code with PKCE, run by Flyto2 for one MCP server.

The MCP authorization spec: the server names its authorization server in its
protected resource metadata (RFC 9728); that server's metadata (RFC 8414)
names the endpoints; the client registers itself when the server allows it
(RFC 7591); every request names the MCP server as its resource (RFC 8707), so
the token Flyto2 receives is issued for that server's audience and no other.

The token obtained here is Flyto2's own credential for one resource. It is
never a token Flyto2 was issued by somebody else, and none of these requests
carries one: the exchange is a form post with no bearer.

Pure protocol: no storage, no browser, no clock. The host keeps the verifier
and the state between ``authorization_request`` and ``exchange_code``, and
stores the token for that resource only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlencode, urlsplit

from .connector_runtime import ConnectorCallError
from .mcp_client import Send, guarded_send

__all__ = [
    "OAUTH_FAILURES",
    "OAuthError",
    "authorization_request",
    "discover",
    "exchange_code",
    "pkce_pair",
    "refresh",
]

OAUTH_FAILURES: Mapping[str, str] = {
    "OAUTH_METADATA_UNREADABLE": "the server or its authorization server published no readable metadata",
    "OAUTH_PKCE_UNSUPPORTED": "the authorization server does not support S256 PKCE",
    "OAUTH_CLIENT_ID_REQUIRED": "the authorization server allows no registration; the owner must give a client id",
    "OAUTH_REGISTRATION_REFUSED": "the authorization server refused to register Flyto2",
    "OAUTH_TOKEN_REFUSED": "the token endpoint refused the code or refresh token",
}

_TIMEOUT_MS = 15_000


class OAuthError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or OAUTH_FAILURES.get(code, code))
        self.code = code


def pkce_pair() -> Tuple[str, str]:
    """``(verifier, S256 challenge)``."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def _json(send: Send, method: str, url: str, *, form: Optional[Mapping[str, str]] = None,
                body: Optional[Mapping[str, Any]] = None, failure: str) -> Tuple[int, Any]:
    headers = {"Accept": "application/json"}
    raw: Optional[bytes] = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        raw = urlencode(dict(form)).encode()
    elif body is not None:
        headers["Content-Type"] = "application/json"
        raw = json.dumps(body).encode()
    try:
        status, _, answer = await send(method, url, headers, raw, _TIMEOUT_MS)
        return status, json.loads(answer.decode("utf-8") or "null")
    except ConnectorCallError as error:
        raise OAuthError(failure, f"{OAUTH_FAILURES[failure]} ({error.code})") from None
    except (UnicodeDecodeError, ValueError):
        raise OAuthError(failure) from None


def _resource_metadata_url(server_url: str) -> str:
    parts = urlsplit(server_url)
    return f"{parts.scheme}://{parts.netloc}/.well-known/oauth-protected-resource{parts.path.rstrip('/')}"


async def discover(server_url: str, *, send: Send = guarded_send, client_id: str = "",
                   redirect_uri: str = "") -> Dict[str, Any]:
    """The endpoints, the client id and the resource for one MCP server."""
    status, resource = await _json(send, "GET", _resource_metadata_url(server_url),
                                   failure="OAUTH_METADATA_UNREADABLE")
    servers = resource.get("authorization_servers") if isinstance(resource, Mapping) else None
    if status != 200 or not isinstance(servers, list) or not servers or not isinstance(servers[0], str):
        raise OAuthError("OAUTH_METADATA_UNREADABLE")
    issuer = servers[0].rstrip("/")
    status, meta = await _json(send, "GET", f"{issuer}/.well-known/oauth-authorization-server",
                               failure="OAUTH_METADATA_UNREADABLE")
    if status != 200 or not isinstance(meta, Mapping) or not meta.get("authorization_endpoint") \
            or not meta.get("token_endpoint"):
        raise OAuthError("OAUTH_METADATA_UNREADABLE")
    if "S256" not in (meta.get("code_challenge_methods_supported") or []):
        raise OAuthError("OAUTH_PKCE_UNSUPPORTED")
    found = {
        "resource": str(resource.get("resource") or server_url),
        "authorization_endpoint": str(meta["authorization_endpoint"]),
        "token_endpoint": str(meta["token_endpoint"]),
        "client_id": client_id or await _registered_client(send, meta, redirect_uri),
    }
    return found


async def _registered_client(send: Send, meta: Mapping[str, Any], redirect_uri: str) -> str:
    endpoint = meta.get("registration_endpoint")
    if not endpoint:
        raise OAuthError("OAUTH_CLIENT_ID_REQUIRED")
    status, answer = await _json(send, "POST", str(endpoint), body={
        "client_name": "Flyto2", "redirect_uris": [redirect_uri] if redirect_uri else [],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }, failure="OAUTH_REGISTRATION_REFUSED")
    client = answer.get("client_id") if isinstance(answer, Mapping) else None
    if status not in (200, 201) or not isinstance(client, str) or not client:
        raise OAuthError("OAUTH_REGISTRATION_REFUSED")
    return client


def authorization_request(meta: Mapping[str, Any], *, redirect_uri: str, state: str, challenge: str,
                          scope: str = "") -> str:
    query = {
        "response_type": "code", "client_id": meta["client_id"], "redirect_uri": redirect_uri,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "resource": meta["resource"],
    }
    if scope:
        query["scope"] = scope
    return f"{meta['authorization_endpoint']}?{urlencode(query)}"


async def _token(send: Send, meta: Mapping[str, Any], form: Dict[str, str]) -> Dict[str, Any]:
    status, answer = await _json(send, "POST", str(meta["token_endpoint"]),
                                 form={**form, "client_id": meta["client_id"], "resource": meta["resource"]},
                                 failure="OAUTH_TOKEN_REFUSED")
    token = answer.get("access_token") if isinstance(answer, Mapping) else None
    if status != 200 or not isinstance(token, str) or not token:
        raise OAuthError("OAUTH_TOKEN_REFUSED")
    lifetime = answer.get("expires_in")
    return {
        "access_token": token,
        "refresh_token": answer.get("refresh_token") if isinstance(answer.get("refresh_token"), str) else "",
        "expires_in": lifetime if isinstance(lifetime, int) else None,
        "resource": meta["resource"],
    }


async def exchange_code(meta: Mapping[str, Any], *, code: str, verifier: str, redirect_uri: str,
                        send: Send = guarded_send) -> Dict[str, Any]:
    return await _token(send, meta, {"grant_type": "authorization_code", "code": code,
                                     "code_verifier": verifier, "redirect_uri": redirect_uri})


async def refresh(meta: Mapping[str, Any], *, refresh_token: str, send: Send = guarded_send) -> Dict[str, Any]:
    return await _token(send, meta, {"grant_type": "refresh_token", "refresh_token": refresh_token})
