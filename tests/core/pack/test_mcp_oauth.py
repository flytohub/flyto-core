"""Flyto2 runs OAuth 2.1 (authorization code + PKCE) for one MCP server itself.

Every exchange goes through an injected ``send`` that plays the protected
resource, its authorization server and the token endpoint in process.
"""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from core.pack.mcp_oauth import (
    OAuthError,
    authorization_request,
    discover,
    exchange_code,
    pkce_pair,
    refresh,
)

SERVER = "https://mcp.example.com/mcp"
AS = "https://auth.example.com"


class FakeAuth:
    def __init__(self, *, s256=True, registration=True):
        self.seen = []
        self.s256 = s256
        self.registration = registration

    async def __call__(self, method, url, headers, body, timeout_ms):
        self.seen.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        path = urlsplit(url).path
        if url == "https://mcp.example.com/.well-known/oauth-protected-resource/mcp":
            return 200, {"Content-Type": "application/json"}, json.dumps(
                {"resource": SERVER, "authorization_servers": [AS]}).encode()
        if url == f"{AS}/.well-known/oauth-authorization-server":
            meta = {"issuer": AS, "authorization_endpoint": f"{AS}/authorize", "token_endpoint": f"{AS}/token",
                    "code_challenge_methods_supported": ["S256"] if self.s256 else ["plain"]}
            if self.registration:
                meta["registration_endpoint"] = f"{AS}/register"
            return 200, {"Content-Type": "application/json"}, json.dumps(meta).encode()
        if path == "/register":
            return 201, {"Content-Type": "application/json"}, json.dumps({"client_id": "flyto2-client"}).encode()
        if path == "/token":
            form = parse_qs(body.decode())
            if form.get("grant_type") == ["refresh_token"]:
                return 200, {}, json.dumps({"access_token": "fresh", "expires_in": 60}).encode()
            if form.get("code") != ["the-code"]:
                return 400, {}, json.dumps({"error": "invalid_grant"}).encode()
            return 200, {}, json.dumps({"access_token": "server-audience-token", "token_type": "Bearer",
                                        "expires_in": 3600, "refresh_token": "r-1"}).encode()
        return 404, {}, b"{}"


async def test_discovery_reads_the_resource_then_its_authorization_server():
    send = FakeAuth()
    meta = await discover(SERVER, send=send)
    assert meta["token_endpoint"] == f"{AS}/token" and meta["resource"] == SERVER
    assert meta["client_id"] == "flyto2-client"


async def test_a_server_without_s256_is_refused():
    with pytest.raises(OAuthError) as caught:
        await discover(SERVER, send=FakeAuth(s256=False))
    assert caught.value.code == "OAUTH_PKCE_UNSUPPORTED"


async def test_a_server_without_registration_needs_an_owner_client_id():
    with pytest.raises(OAuthError) as caught:
        await discover(SERVER, send=FakeAuth(registration=False))
    assert caught.value.code == "OAUTH_CLIENT_ID_REQUIRED"
    meta = await discover(SERVER, send=FakeAuth(registration=False), client_id="owner-registered")
    assert meta["client_id"] == "owner-registered"


def test_pkce_is_s256():
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


async def test_the_authorization_request_names_the_servers_own_resource():
    meta = await discover(SERVER, send=FakeAuth())
    url = authorization_request(meta, redirect_uri="http://127.0.0.1:8765/cb", state="s-1", challenge="c-1")
    query = parse_qs(urlsplit(url).query)
    assert query["resource"] == [SERVER]
    assert query["code_challenge_method"] == ["S256"] and query["code_challenge"] == ["c-1"]
    assert query["response_type"] == ["code"] and query["state"] == ["s-1"]


async def test_the_code_is_exchanged_for_this_resource_with_the_verifier():
    send = FakeAuth()
    meta = await discover(SERVER, send=send)
    token = await exchange_code(meta, code="the-code", verifier="v" * 43,
                                redirect_uri="http://127.0.0.1:8765/cb", send=send)
    assert token["access_token"] == "server-audience-token" and token["refresh_token"] == "r-1"
    form = parse_qs(send.seen[-1]["body"].decode())
    assert form["resource"] == [SERVER] and form["code_verifier"] == ["v" * 43]
    # The exchange carries no bearer at all: nothing Flyto2 was issued travels.
    assert "Authorization" not in send.seen[-1]["headers"]


async def test_a_refused_code_is_typed():
    send = FakeAuth()
    meta = await discover(SERVER, send=send)
    with pytest.raises(OAuthError) as caught:
        await exchange_code(meta, code="wrong", verifier="v" * 43, redirect_uri="http://x/cb", send=send)
    assert caught.value.code == "OAUTH_TOKEN_REFUSED"


async def test_refresh_keeps_the_resource():
    send = FakeAuth()
    meta = await discover(SERVER, send=send)
    token = await refresh(meta, refresh_token="r-1", send=send)
    assert token["access_token"] == "fresh"
    assert parse_qs(send.seen[-1]["body"].decode())["resource"] == [SERVER]
