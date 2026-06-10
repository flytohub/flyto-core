# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Scrubbed environment for subprocess spawns (shared, dependency-free).

Any module that spawns a child process (shell.exec, process.start, git.*,
docker.*, k8s.*, network.*, plugin installs) and returns its stdout to the
caller leaks every host secret it inherits via os.environ — API keys, tokens,
DATABASE_URL, cloud credentials. ``env`` / ``cat /proc/self/environ`` /
``python -c 'import os;print(os.environ)'`` all become exfiltration primitives.

build_sandbox_env() returns a minimal environment containing only non-sensitive,
execution-relevant variables (PATH so interpreters/tools resolve, plus locale).
This is defense-in-depth: the dangerous modules are denied by default at the
capability layer (core.module_policy); this ensures that even when an operator
deliberately opts them in, the spawned process cannot trivially harvest host
secrets from the inherited environment.

Override with FLYTO_SANDBOX_INHERIT_ENV=1 to restore full inheritance (NOT
recommended when serving untrusted / red-team clients).
"""

import os
from typing import Any, Dict, Optional

# Variables safe to pass through. Deliberately excludes anything that commonly
# carries credentials. PATH is included so interpreters/tools (git, docker,
# python) resolve.
_SAFE_ENV_PASSTHROUGH = (
    "PATH", "HOME", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
    "TERM", "TMPDIR", "TEMP", "TMP", "TZ", "PWD", "SHELL",
    # git needs these to resolve config/cert paths but they are not secrets.
    "GIT_EXEC_PATH", "GIT_TEMPLATE_DIR", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "SYSTEMROOT",  # Windows: required for socket/DLL resolution
)

_TRUTHY = {"1", "true", "yes", "on"}


def inherit_full_env() -> bool:
    return os.environ.get("FLYTO_SANDBOX_INHERIT_ENV", "").strip().lower() in _TRUTHY


def build_sandbox_env(extra_env: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Return the environment for a subprocess.

    By default: only the non-sensitive passthrough allowlist, plus any caller
    supplied extra_env (which the caller is explicitly choosing to inject —
    values are stringified literally, with no shell/variable expansion at this
    layer, so {"X": "$AWS_SECRET"} is NOT substituted).
    With FLYTO_SANDBOX_INHERIT_ENV truthy: the full parent environment.
    """
    if inherit_full_env():
        env = dict(os.environ)
    else:
        env = {k: os.environ[k] for k in _SAFE_ENV_PASSTHROUGH if k in os.environ}
    for k, v in (extra_env or {}).items():
        env[str(k)] = str(v)
    return env
