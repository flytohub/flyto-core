# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Re-export of the shared scrubbed-environment helper.

The implementation lives in ``core.safe_env`` so every subprocess-spawning
module (shell.exec, process.start, git.*, docker.*, k8s.*, network.*, plugin
installs) routes through one allowlist. This thin shim preserves the
``from .safe_env import build_sandbox_env`` import used by the sandbox modules.
"""

from core.safe_env import (  # noqa: F401
    build_sandbox_env,
    inherit_full_env,
    _SAFE_ENV_PASSTHROUGH,
)
