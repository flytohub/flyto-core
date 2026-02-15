"""
Security — CORS, Bearer Token Auth, Module Denylist/Allowlist

Environment variables:
  FLYTO_CORS_ORIGINS    — Comma-separated allowed origins (default: localhost only).
                          Set to "*" to allow all origins.
  FLYTO_API_TOKEN       — Fixed bearer token. If unset, auto-generated on startup.
  FLYTO_MODULE_DENYLIST — Comma-separated glob patterns to deny (default: "shell.*,process.*").
                          Set to empty string to clear.
  FLYTO_MODULE_ALLOWLIST — If set, ONLY these modules are allowed (overrides denylist).
"""

import fnmatch
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


def init_auth(port: int) -> Optional[str]:
    """
    Initialize auth token. Called once at startup.

    Priority:
    1. FLYTO_API_TOKEN env var — use as-is
    2. Auto-generate + write to file

    Returns the active token, or None if auth is disabled.
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
    """FastAPI dependency — validates Bearer token on protected endpoints."""
    if _active_token is None:
        return  # Auth not initialized — pass through

    if not credentials or credentials.credentials != _active_token:
        raise HTTPException(status_code=401, detail="Invalid or missing auth token")


# ---------------------------------------------------------------------------
# Module Filter (Denylist / Allowlist)
# ---------------------------------------------------------------------------

_DEFAULT_DENYLIST = ["shell.*", "process.*"]


class ModuleFilter:
    """Filter modules by glob-pattern denylist/allowlist."""

    def __init__(self):
        self.denylist: List[str] = []
        self.allowlist: List[str] = []
        self._load_from_env()

    def _load_from_env(self):
        # Allowlist takes priority if set
        raw_allow = os.environ.get("FLYTO_MODULE_ALLOWLIST", "").strip()
        if raw_allow:
            self.allowlist = [p.strip() for p in raw_allow.split(",") if p.strip()]
            logger.info("Module allowlist: %s", self.allowlist)
            return

        # Denylist
        raw_deny = os.environ.get("FLYTO_MODULE_DENYLIST")
        if raw_deny is not None:
            # Explicit env var — could be empty to clear defaults
            raw_deny = raw_deny.strip()
            self.denylist = [p.strip() for p in raw_deny.split(",") if p.strip()] if raw_deny else []
        else:
            self.denylist = list(_DEFAULT_DENYLIST)

        if self.denylist:
            logger.info("Module denylist: %s", self.denylist)

    def is_allowed(self, module_id: str) -> bool:
        """Check if a module is allowed to execute."""
        if self.allowlist:
            return any(fnmatch.fnmatch(module_id, pat) for pat in self.allowlist)
        if self.denylist:
            return not any(fnmatch.fnmatch(module_id, pat) for pat in self.denylist)
        return True


# Singleton — initialized on import, reads env vars once
module_filter = ModuleFilter()
