# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Security — CORS, Bearer Token Auth, Module Denylist/Allowlist

Environment variables:
  FLYTO_CORS_ORIGINS    — Comma-separated allowed origins (default: localhost only).
                          Set to "*" to allow all origins.
  FLYTO_API_TOKEN       — Fixed bearer token. If unset, auto-generated on startup.
  FLYTO_MODULE_DENYLIST — Comma-separated glob patterns to deny. Defaults to the
                          dangerous-by-default set below (host RCE / SSRF-to-DB /
                          unconfined filesystem sinks). Set to empty string to clear
                          (NOT recommended when exposing the server to any client),
                          or override with your own list.
  FLYTO_MODULE_ALLOWLIST — If set, ONLY these modules are allowed (overrides denylist).
                          Use this for strict deny-by-default when serving untrusted
                          or red-team MCP clients.

The same ModuleFilter singleton gates BOTH the REST route and BOTH MCP transports
(STDIO + HTTP) — see mcp_handler.execute_module / run_recipe. There is no transport
that bypasses it.
"""

import logging
import os
import secrets
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8334",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8334",
]


def get_cors_origins() -> List[str]:
    """Return allowed CORS origins from env or defaults."""
    raw = os.environ.get("FLYTO_CORS_ORIGINS", "").strip()
    if raw == "*":
        return ["*"]
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_ORIGINS)


# ---------------------------------------------------------------------------
# Bearer Token Auth
# ---------------------------------------------------------------------------

_TOKEN_DIR = Path.home() / ".flyto"
_bearer_scheme = HTTPBearer(auto_error=False)

# Module-level token — set by init_auth() at startup
_active_token: Optional[str] = None


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _token_file_path(port: int) -> Path:
    return _TOKEN_DIR / f".api-token-{port}"


def write_token_file(token: str, port: int) -> Path:
    """Write token to ~/.flyto/.api-token-{port}. Returns path."""
    _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    path = _token_file_path(port)
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return path


def read_token_file(port: int) -> Optional[str]:
    """Read token from file. Returns None if missing."""
    path = _token_file_path(port)
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return None


def init_auth(port: int) -> str:
    """
    Initialize auth token. Called once at startup.

    Priority:
    1. FLYTO_API_TOKEN env var — use as-is
    2. Auto-generate + write to file

    Always mints and returns a non-empty bearer token: there is intentionally
    **no auth-disabled mode**. Both paths set ``_active_token`` and return it, so
    the return value is never None (the ``Optional`` was historical).

    Design decision (FLYA-41): auth is on by default and fails closed. The
    uninitialized ``_active_token is None`` state is reserved exclusively for
    "auth not initialized / server misconfigured" and is rejected with 503 by
    ``require_auth`` (see GHSA-h9f9-h6gm-wc85, FLYA-32) — it must never be
    overloaded to mean "auth deliberately off". If an explicit auth-disabled
    mode is ever genuinely needed, it MUST be gated behind a dedicated, loud env
    flag (e.g. ``FLYTO_AUTH_DISABLED=1``) handled here so the intent is explicit
    in logs and code — never inferred from a None token. No such flag exists
    today, and any unrecognized one is ignored: this function still mints a token.
    """
    global _active_token

    env_token = os.environ.get("FLYTO_API_TOKEN", "").strip()
    if env_token:
        _active_token = env_token
        logger.info("Auth enabled (token from FLYTO_API_TOKEN env var)")
        return _active_token

    # Auto-generate
    _active_token = generate_token()
    token_path = write_token_file(_active_token, port)
    logger.info("Auth enabled (token written to %s)", token_path)
    return _active_token


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
):
    """FastAPI dependency — validates Bearer token on protected endpoints.

    Fails closed (Secure Defaults / Fail Securely): if auth was never
    initialized (``_active_token is None``) the request is refused rather than
    passed through. ``init_auth`` always mints a token during normal startup
    (``create_app`` calls it unconditionally), so a ``None`` token means the
    server is misconfigured/uninitialized — in which case denying every
    protected surface, including MCP module execution, is the safe default.
    """
    if _active_token is None:
        # Latent fail-open removed: never serve a protected endpoint without
        # active authentication. 503 distinguishes "auth not initialized"
        # (server-side misconfiguration) from "bad/missing credentials" (401).
        raise HTTPException(
            status_code=503,
            detail="Authentication is not initialized; refusing request",
        )

    if not credentials or credentials.credentials != _active_token:
        raise HTTPException(status_code=401, detail="Invalid or missing auth token")


# ---------------------------------------------------------------------------
# Bind Posture
# ---------------------------------------------------------------------------

# Hosts that only accept connections from the local machine. An empty/unset
# host, "0.0.0.0", "::", and "*" all resolve to "all interfaces" (INADDR_ANY /
# in6addr_any) and are therefore NOT loopback — binding to them exposes the
# server to the network. They must fall through to enforce_bind_policy's auth
# check rather than being treated as a safe local bind (fail-open removed).
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# Hosts that explicitly request all interfaces (INADDR_ANY / in6addr_any).
# Treated as non-loopback unconditionally so a wildcard bind can never be
# misclassified as a safe local bind — even if a future edit re-adds one of
# these to _LOOPBACK_HOSTS (defense in depth around the fail-open we removed).
_WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::", "*"})


def is_auth_active() -> bool:
    """True once init_auth() has established a bearer token."""
    return _active_token is not None


def _is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if normalized in _WILDCARD_HOSTS:
        return False  # all-interfaces bind is never loopback — refuse the shortcut
    return normalized in _LOOPBACK_HOSTS


def enforce_bind_policy(host: str) -> None:
    """Fail-closed bind guard, called at startup before binding the socket.

    Binding to a non-loopback interface exposes the Execution API (including
    the MCP module-execution surface) to the network. That is only safe when
    authentication is active. If auth is not active, refuse the bind outright
    rather than warning — see GHSA-h9f9-h6gm-wc85.
    """
    if _is_loopback_host(host):
        return
    if not is_auth_active():
        raise RuntimeError(
            f"Refusing to bind to non-loopback host {host!r} without active "
            "authentication. Set FLYTO_API_TOKEN (or use the auto-generated "
            "token) before exposing the server, or bind to 127.0.0.1."
        )


# ---------------------------------------------------------------------------
# Module Filter (Denylist / Allowlist)
# ---------------------------------------------------------------------------
#
# The ModuleFilter lives in core.module_policy (dependency-free) so the SAME
# singleton can gate the module-execution hot path on every transport — the REST
# route here AND both MCP transports (mcp_handler.execute_module / run_recipe) —
# without importing FastAPI. Re-exported here for backward compatibility with
# existing `from ..security import module_filter` call sites.
from core.module_policy import ModuleFilter, module_filter, _DEFAULT_DENYLIST  # noqa: E402,F401
