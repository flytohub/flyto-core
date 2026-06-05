# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module capability policy — denylist / allowlist filter.

Dependency-free (stdlib only) so it can gate the module-execution hot path on
EVERY transport without dragging in FastAPI/the HTTP app:
  - the REST route (api/routes/modules.py, re-exported via api.security)
  - the STDIO MCP transport (mcp_server.py -> mcp_handler)
  - the HTTP MCP transport (api/routes/mcp.py -> mcp_handler)

Environment variables:
  FLYTO_MODULE_DENYLIST  — Comma-separated glob patterns to deny. Defaults to the
                           dangerous-by-default set below. Set to empty string to
                           clear (NOT recommended), or override with your own list.
  FLYTO_MODULE_ALLOWLIST — If set, ONLY these patterns are allowed (overrides the
                           denylist). Use for strict deny-by-default when serving
                           untrusted / red-team MCP clients.
"""

import fnmatch
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

# Dangerous-by-default: deny capabilities that grant host code execution,
# SSRF-to-internal-services, or unconfined filesystem mutation unless the
# operator explicitly opts in (FLYTO_MODULE_DENYLIST / FLYTO_MODULE_ALLOWLIST).
#
# Scoped deliberately so the 37 shipped scraping/automation recipes keep working:
#   - browser.* (incl. browser.evaluate, page-context JS) stays ALLOWED — it is the
#     core scraping primitive; its host-escape risk is addressed by running the
#     browser non-root (see the --no-sandbox hardening), not by denylisting it here.
#   - docker.ps / network.* stay ALLOWED; only the host-control docker verbs are denied.
# Operators serving untrusted / red-team MCP clients should tighten this further via
# FLYTO_MODULE_ALLOWLIST (strict opt-in).
_DEFAULT_DENYLIST = [
    "shell.*",          # arbitrary host command execution
    "process.*",        # process spawn / detached reverse-shell surface
    "sandbox.*",        # execute_shell / execute_python / execute_js — NOT real sandboxes
    "database.*",       # client-supplied connection_string + raw SQL = SSRF-to-DB
    "k8s.*",            # cluster control
    "ssh.*",            # remote exec / credential MITM
    "docker.run",       # container host control (docker.ps stays allowed)
    "docker.exec",
    "file.delete",      # path not validated — arbitrary host file deletion
]


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


# ---------------------------------------------------------------------------
# Per-module capability permissions (a second lock beyond the module allowlist)
# ---------------------------------------------------------------------------
#
# Modules declare required_permissions in their metadata. Most (browser.*, file,
# network, ai, cloud) are needed by ordinary recipes and are always allowed. A
# small set grants host code execution or money movement and must be explicitly
# granted via FLYTO_GRANTED_PERMISSIONS — otherwise the module is refused even if
# its module-id passed the allowlist. This makes required_permissions enforced
# rather than decorative.
_DANGEROUS_PERMISSIONS = frozenset({
    "shell.execute",
    "subprocess.execute",
    "payment.process",
})


def granted_permissions() -> set:
    raw = os.environ.get("FLYTO_GRANTED_PERMISSIONS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


def missing_permissions(required) -> list:
    """Return the dangerous permissions in `required` that have NOT been granted.

    An empty list means the module is permitted. Non-dangerous permissions are
    always allowed (returned never lists them).
    """
    granted = granted_permissions()
    return [
        p for p in (required or [])
        if p in _DANGEROUS_PERMISSIONS and p not in granted
    ]
