# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Extension Routes

Generic management for the two supported Core extension kinds:

    flyto-modules-*  (entry-point group ``flyto.modules``)
    flyto-plugin-*   (entry-point group ``flyto.plugins``)

GET  /v1/extensions           — Installed extensions, both kinds (auth)
GET  /v1/extensions/kinds     — The supported kinds, as data (auth)
POST /v1/extensions/install   — Install/upgrade one extension (auth + opt-in)
POST /v1/extensions/uninstall — Uninstall one extension (auth + opt-in)

Nothing here names a particular extension. ``flyto-modules-robotics`` is managed
by the same code path as any other module pack, on the strength of its prefix
and its entry-point group alone — there is no per-extension branch to add.

Security posture
----------------
Every route requires the bearer token (``require_auth``), and the two mutating
routes additionally require an explicit operator opt-in
(``FLYTO_EXTENSIONS_INSTALL_ENABLED``). Installing a package runs its build
hooks as host code, so "the caller held the API token" is not on its own a
sufficient reason to do it: the token is minted automatically at startup for
local clients, and it authorises module execution, not arbitrary code
installation. Read routes stay available without the opt-in because listing what
is installed changes nothing.

Errors are returned as a fixed envelope with a stable ``code`` from
``ExtensionErrorCode``. Package-manager stdout/stderr is logged locally and
never returned: it carries interpreter paths, index URLs, and occasionally
credentials embedded in an index URL.

Blocking work — pip, and the installed-distribution scans the listing does — is
handed to a worker thread. The loader is synchronous and an install is bounded
at two minutes, so calling it directly from these coroutines would park the
event loop for that long and stall every unrelated request on the server,
health checks included.
"""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.plugin.loader import (
    EXTENSION_KINDS,
    ExtensionErrorCode,
    ExtensionResult,
    get_plugin_loader,
    normalize_extension_name,
)

from ..security import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extensions"])


# ---------------------------------------------------------------------------
# Operator opt-in
# ---------------------------------------------------------------------------

#: Operator opt-in for the mutating routes. Absent/false means install and
#: uninstall are refused; the read routes are unaffected.
INSTALL_ENABLED_ENV = "FLYTO_EXTENSIONS_INSTALL_ENABLED"

_TRUTHY = {"1", "true", "yes", "on"}

#: Stable code for "the operator has not opted in". Lives here rather than in
#: ExtensionErrorCode because it is a property of this transport, not of the
#: loader — the CLI reaches the same loader without it.
MANAGEMENT_DISABLED = "extension_management_disabled"


def install_enabled() -> bool:
    """True when the operator has opted into remote extension installation."""
    return os.environ.get(INSTALL_ENABLED_ENV, "").strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# Stable error envelope
# ---------------------------------------------------------------------------

#: code -> HTTP status. Fixed mapping so a client can branch on either and get
#: the same answer. 502 is used where the failure is the package manager's or
#: the index's, not the caller's request.
_STATUS_BY_CODE: Dict[str, int] = {
    ExtensionErrorCode.UNSUPPORTED_EXTENSION: 400,
    ExtensionErrorCode.INVALID_NAME: 400,
    ExtensionErrorCode.INVALID_VERSION: 400,
    ExtensionErrorCode.NOT_INSTALLED: 404,
    ExtensionErrorCode.ENTRYPOINT_MISSING: 409,
    ExtensionErrorCode.ROLLBACK_FAILED: 409,
    ExtensionErrorCode.INSTALL_FAILED: 502,
    ExtensionErrorCode.UNINSTALL_FAILED: 502,
    ExtensionErrorCode.TIMEOUT: 504,
    MANAGEMENT_DISABLED: 403,
}

#: Any code that is somehow not in the table above. Deliberately a server error:
#: an unmapped code is a bug here, not a bad request there.
_FALLBACK_STATUS = 500


def _error_response(
    code: str,
    message: str,
    name: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """The one error shape this router emits.

    ``JSONResponse`` rather than ``HTTPException`` on purpose: FastAPI renders
    an exception as ``{"detail": ...}``, which cannot carry a stable code
    alongside a message without clients string-matching the detail.
    """
    body: Dict[str, Any] = {
        "ok": False,
        "error": {"code": code, "message": message, "name": name},
    }
    if extra:
        body["error"].update(extra)
    return JSONResponse(body, status_code=_STATUS_BY_CODE.get(code, _FALLBACK_STATUS))


def _result_response(result: ExtensionResult) -> JSONResponse:
    """Render an ExtensionResult as either the success or the error envelope."""
    if not result.ok:
        return _error_response(
            result.code or ExtensionErrorCode.INSTALL_FAILED,
            result.message,
            name=result.name,
            extra={
                "rolled_back": result.rolled_back,
                "restart_required": result.restart_required,
                # Reported on failures too: a rollback whose refresh failed
                # leaves this process still holding the package it just removed.
                "refresh_failed": result.refresh_failed,
            },
        )
    payload = result.to_dict()
    payload.pop("code", None)
    return JSONResponse(payload, status_code=200)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class InstallExtensionRequest(BaseModel):
    """Install/upgrade request.

    ``name`` must be the full prefixed distribution name. A bare name is not
    completed for the caller: ``robotics`` is ambiguous between
    ``flyto-modules-robotics`` and ``flyto-plugin-robotics``, and guessing would
    install a different package than the one the caller asked for.
    """

    name: str = Field(..., min_length=1, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    upgrade: bool = False


class UninstallExtensionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# GET /v1/extensions
# ---------------------------------------------------------------------------


@router.get("/extensions", dependencies=[Depends(require_auth)])
async def list_extensions():
    """Installed extensions of every supported kind.

    ``get_plugin_loader`` is called inside the worker too, not just the listing:
    the first call builds the loader, which creates its state directory, and it
    can now block behind an in-flight install's lock. Neither belongs on the
    event loop.
    """
    extensions = await run_in_threadpool(lambda: get_plugin_loader().list_extensions())
    return {
        "count": len(extensions),
        "extensions": extensions,
        "install_enabled": install_enabled(),
    }


# ---------------------------------------------------------------------------
# GET /v1/extensions/kinds
# ---------------------------------------------------------------------------


@router.get("/extensions/kinds", dependencies=[Depends(require_auth)])
async def list_extension_kinds():
    """The supported extension kinds, served from the same table the installer
    enforces — so a client's idea of what is installable cannot drift from
    Core's."""
    return {
        "kinds": [
            {
                "kind": kind.kind,
                "prefix": kind.prefix,
                "entry_point_group": kind.entry_point_group,
            }
            for kind in EXTENSION_KINDS
        ]
    }


# ---------------------------------------------------------------------------
# POST /v1/extensions/install
# ---------------------------------------------------------------------------


@router.post("/extensions/install", dependencies=[Depends(require_auth)])
async def install_extension(request: InstallExtensionRequest):
    """Install or upgrade one extension.

    On success the response reports ``restart_required``: an upgrade replaces
    code this interpreter has already imported, and Python does not un-import,
    so the registry refresh updates what Core *reports* while only a restart
    changes what it *runs*. A first install has nothing already imported and
    takes effect immediately — unless ``refresh_failed`` is also set, which
    means Core could not rebuild its records at all and a restart is needed
    either way.
    """
    if not install_enabled():
        # Normalised like every other id this router returns. A refusal is still
        # an answer about a package, and a client that reads ``name`` off it
        # must get the same id an install or a listing would have given for the
        # same package — otherwise the one response an operator is most likely
        # to script against is the one that echoes back an unstable spelling.
        name = normalize_extension_name(request.name)
        logger.warning(
            "Refused extension install for %r: %s is not enabled",
            name, INSTALL_ENABLED_ENV,
        )
        return _error_response(
            MANAGEMENT_DISABLED,
            f"Extension installation is disabled. Set {INSTALL_ENABLED_ENV}=1 to enable.",
            name=name,
        )

    # Everything blocking in one hop: acquiring the loader, waiting on its lock,
    # and the bounded-at-two-minutes pip run itself. On the event loop that is
    # two minutes of stalled health checks and every unrelated request behind
    # them.
    result = await run_in_threadpool(
        lambda: get_plugin_loader().install_extension(
            request.name, request.version, request.upgrade
        )
    )
    return _result_response(result)


# ---------------------------------------------------------------------------
# POST /v1/extensions/uninstall
# ---------------------------------------------------------------------------


@router.post("/extensions/uninstall", dependencies=[Depends(require_auth)])
async def uninstall_extension(request: UninstallExtensionRequest):
    """Uninstall one extension. Always reports ``restart_required``."""
    if not install_enabled():
        name = normalize_extension_name(request.name)
        logger.warning(
            "Refused extension uninstall for %r: %s is not enabled",
            name, INSTALL_ENABLED_ENV,
        )
        return _error_response(
            MANAGEMENT_DISABLED,
            f"Extension management is disabled. Set {INSTALL_ENABLED_ENV}=1 to enable.",
            name=name,
        )

    result = await run_in_threadpool(
        lambda: get_plugin_loader().uninstall_extension(request.name)
    )
    return _result_response(result)
