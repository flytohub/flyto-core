# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Scrubbed environment for sandbox subprocesses.

sandbox.execute_shell / execute_python spawn a child process. Inheriting the
full parent environment hands every host secret (API keys, tokens, DATABASE_URL,
cloud credentials) to attacker-controlled code, so the child can read and
exfiltrate them. This module builds a minimal environment containing only
non-sensitive, execution-relevant variables.

This is defense-in-depth: the modules are denied by default at the MCP
capability layer; this ensures that even when an operator deliberately opts them
in, the executed code cannot trivially harvest host secrets via os.environ.

Override with FLYTO_SANDBOX_INHERIT_ENV=1 to restore full inheritance (NOT
recommended when serving untrusted / red-team clients).
"""

import os
from typing import Any, Dict, Optional

# Variables safe to pass through. Deliberately excludes anything that commonly
# carries credentials. PATH is included so interpreters/tools resolve.
_SAFE_ENV_PASSTHROUGH = (
    "PATH", "HOME", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TEMP", "TMP", "TZ", "PWD", "SHELL",
)

_TRUTHY = {"1", "true", "yes", "on"}


def inherit_full_env() -> bool:
    return os.environ.get("FLYTO_SANDBOX_INHERIT_ENV", "").strip().lower() in _TRUTHY


def build_sandbox_env(extra_env: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Return the environment for a sandbox subprocess.

    By default: only the non-sensitive passthrough allowlist, plus any caller
    supplied extra_env (which the caller is explicitly choosing to inject).
    With FLYTO_SANDBOX_INHERIT_ENV truthy: the full parent environment.
    """
    if inherit_full_env():
        env = dict(os.environ)
    else:
        env = {k: os.environ[k] for k in _SAFE_ENV_PASSTHROUGH if k in os.environ}
    for k, v in (extra_env or {}).items():
        env[str(k)] = str(v)
    return env
