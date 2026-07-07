# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Module capability policy — denylist / allowlist filter.

Dependency-free (stdlib only) so it can gate the module-execution hot path on
EVERY transport without dragging in FastAPI/the HTTP app:
  - the REST route (api/routes/modules.py, re-exported via api.security)
  - the STDIO MCP transport (mcp_server.py -> mcp_handler)
  - the HTTP MCP transport (api/routes/mcp.py -> mcp_handler)
  - the engine chokepoint (modules/base.py BaseModule.run) — covers recipe,
    foreach, composite sub-node, flow.invoke / template.invoke / flow.subflow.

Environment variables:
  FLYTO_MODULE_DENYLIST  — Comma-separated glob patterns to deny. Defaults to the
                           dangerous-by-default set below. Set to empty string to
                           clear (NOT recommended), or override with your own list.
  FLYTO_MODULE_ALLOWLIST — If set, ONLY these patterns are allowed (overrides the
                           denylist). Use for strict deny-by-default when serving
                           untrusted / red-team MCP clients.
  FLYTO_GRANTED_PERMISSIONS — Comma-separated dangerous permissions to grant
                           (e.g. shell.execute). Modules declaring an ungranted
                           dangerous permission are refused even if their id
                           passes the allowlist.
"""

import fnmatch
import logging
import os
from typing import Any, List

logger = logging.getLogger(__name__)

# Dangerous-by-default: deny capabilities that grant host code execution,
# SSRF-to-internal-services, or unconfined filesystem mutation unless the
# operator explicitly opts in (FLYTO_MODULE_DENYLIST / FLYTO_MODULE_ALLOWLIST).
#
# Scoped deliberately so the shipped scraping/automation recipes keep working:
#   - browser.* (incl. browser.evaluate, page-context JS) stays ALLOWED — it is the
#     core scraping primitive; its host-escape risk is addressed by running the
#     browser non-root, not by denylisting it here.
#   - docker.ps / network.* stay ALLOWED; only the host-control docker verbs are denied.
# Operators serving untrusted / red-team MCP clients should tighten this further via
# FLYTO_MODULE_ALLOWLIST (strict opt-in).
_DEFAULT_DENYLIST = [
    "shell.*",          # arbitrary host command execution
    "process.*",        # process spawn / detached reverse-shell surface
    "sandbox.*",        # execute_shell / execute_python / execute_js — NOT real sandboxes
    "database.*",       # client-supplied connection_string + raw SQL = SSRF-to-DB
    "git.*",            # git.clone ext:: transport = host RCE; spawns host git
    "k8s.*",            # cluster control
    "ssh.*",            # remote exec / credential MITM
    "docker.run",       # container host control (docker.ps stays allowed)
    "docker.exec",
    "file.delete",      # path not validated — arbitrary host file deletion
    "env.get",          # reads ANY host env var (API keys/DSNs) = secret exfil
    "env.load_dotenv",  # loads a .env file from disk into workflow variables
    # Nested-execution gadgets: these run arbitrary child workflows/modules from
    # an inline workflow_source/template payload. Denied by default so they can't
    # be used to smuggle a denied module (shell.exec etc.) past this filter. The
    # pre-flight in run_recipe ALSO parses their inline payloads as defense in
    # depth, but denying the gadget itself is the structural backstop.
    "flow.invoke",
    "flow.subflow",
    "flow.batch",
    "template.invoke",
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
# Environment-variable interpolation policy
# ---------------------------------------------------------------------------
#
# The workflow engine expands ${env.VAR} in step parameters. That is the exact
# capability the `env.get` module denylist exists to block (reading arbitrary
# host env vars = secret exfil). Interpolation happens in the engine BEFORE the
# module chokepoint, so denylisting `env.get` alone does not stop it
# (GHSA-hr7p-wg7r-hg9m). We therefore gate ${env.*} through one shared policy:
#
#   - If `env.get` is permitted by the module filter, env access is enabled and
#     ${env.VAR} resolves as before.
#   - Otherwise (the secure default), ${env.VAR} is DENIED unless VAR matches an
#     explicit allowlist the operator opts into via FLYTO_ENV_VAR_ALLOWLIST
#     (comma-separated names or fnmatch globs, e.g. "PUBLIC_*,APP_REGION").
#
# This makes engine interpolation and module execution enforce the same env
# policy, deny-by-default.

def _env_var_allowlist() -> List[str]:
    raw = os.environ.get("FLYTO_ENV_VAR_ALLOWLIST", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def is_env_var_allowed(name: str) -> bool:
    """Whether ${env.<name>} interpolation is permitted by policy.

    Ties ${env.*} to the same control as the `env.get` module: if `env.get` is
    allowed, env access is enabled; otherwise only names explicitly allowlisted
    via FLYTO_ENV_VAR_ALLOWLIST resolve, and everything else is denied.
    """
    if not name:
        return False
    if module_filter.is_allowed("env.get"):
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in _env_var_allowlist())


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


class ModulePolicyError(PermissionError):
    """Raised at the execution chokepoint when a module is blocked by policy."""


def enforce_module_policy(module_id, required_permissions=None) -> None:
    """Fail-closed gate, called at the single execution chokepoint (BaseModule.run).

    Raises ModulePolicyError if the module id is denied by the capability filter
    or declares an ungranted dangerous permission. Because EVERY module — direct,
    recipe step, foreach item, composite sub-node, and any child reached via
    flow.invoke / template.invoke / flow.subflow / agent tools — is executed
    through this gate, a denied module cannot run no matter how it was invoked.
    The MCP-boundary checks remain as a first line; this is the backstop the
    nested-execution gadgets were bypassing.
    """
    if not module_id:
        return
    if not module_filter.is_allowed(module_id):
        raise ModulePolicyError(
            f"Module '{module_id}' is blocked by the capability policy "
            "(FLYTO_MODULE_DENYLIST / FLYTO_MODULE_ALLOWLIST)."
        )
    missing = missing_permissions(required_permissions)
    if missing:
        raise ModulePolicyError(
            f"Module '{module_id}' requires ungranted permission(s) {missing} "
            "(grant via FLYTO_GRANTED_PERMISSIONS)."
        )


# ---------------------------------------------------------------------------
# Inline-payload module-id extraction (pre-flight defense in depth)
# ---------------------------------------------------------------------------
#
# flow.invoke / template.invoke / flow.subflow can take an *inline* workflow as
# an opaque YAML/JSON string (workflow_source / template / workflow params). The
# denied module id is then hidden inside a string, not under a `module:` key, so
# a naive walk over the recipe dict misses it. _collect_module_ids therefore
# (a) collects every `module:` value, AND (b) parses inline payload strings and
# recurses into them so a smuggled `shell.exec` inside `workflow_source` is seen.

# Param keys whose string value may itself be a serialized sub-workflow.
_INLINE_WORKFLOW_KEYS = frozenset({
    "workflow_source", "workflow", "template", "source", "yaml", "definition",
})


def _parse_inline_workflow(text: str) -> Any:
    """Best-effort parse of an inline workflow string (YAML superset of JSON)."""
    if not text or not isinstance(text, str):
        return None
    stripped = text.strip()
    # Cheap reject: a sub-workflow declares modules; if the literal token
    # 'module' never appears, there is nothing to extract.
    if "module" not in stripped:
        return None
    try:
        import yaml  # local import; only needed when an inline payload is seen
        return yaml.safe_load(stripped)
    except Exception:
        return None


def _collect_module_ids(obj: Any, _depth: int = 0) -> set:
    """Recursively collect every module id declared anywhere in a workflow dict.

    Walks `module:` keys AND parses inline workflow_source/template/workflow
    string payloads (the flow.invoke / template.invoke smuggling vector) so a
    denied module hidden inside an opaque YAML string is still detected.
    """
    found: set = set()
    if _depth > 25:
        return found
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "module" and isinstance(value, str) and value:
                found.add(value)
            elif key in _INLINE_WORKFLOW_KEYS and isinstance(value, str):
                parsed = _parse_inline_workflow(value)
                if parsed is not None:
                    found |= _collect_module_ids(parsed, _depth + 1)
                # also walk the raw string's structure if it parsed to a container
            else:
                found |= _collect_module_ids(value, _depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            found |= _collect_module_ids(item, _depth + 1)
    elif isinstance(obj, str):
        # A bare string that is itself a serialized sub-workflow (e.g. the
        # value passed positionally). Only parse when it looks like one.
        parsed = _parse_inline_workflow(obj)
        if isinstance(parsed, (dict, list)):
            found |= _collect_module_ids(parsed, _depth + 1)
    return found
