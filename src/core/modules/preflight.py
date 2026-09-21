# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Explicit module checks for values known before execution begins.

This boundary never constructs or executes a module, supplies defaults, or
rewrites parameters. Hosts must omit values that still depend on execution.
Only a module's opt-in static ``preflight_params`` hook is called. A return
does not authorize execution or replace schema, policy, and runtime validation.
"""

from typing import Any, Mapping

__all__ = ["ModulePreflightError", "preflight_module_params"]


class ModulePreflightError(ValueError):
    """Safe admission failure without parameter values or host paths."""

    def __init__(self, *, field: str, code: str):
        self.field = field
        self.code = code
        super().__init__("A module parameter is not permitted by the execution host.")


def preflight_module_params(module_id: str, params: Mapping[str, Any]) -> None:
    """Check supplied, resolved values using an explicitly declared pure hook.

    Unknown and non-opted-in modules remain subject to their existing runtime
    checks. Neither schema display formats nor descriptive tags imply a hook.
    The execution host's current configuration governs any opted-in check.
    """
    from .registry import ModuleRegistry

    if not ModuleRegistry.has(module_id):
        return
    module_class = ModuleRegistry.get(module_id)
    hook = getattr(module_class, "preflight_params", None)
    if callable(hook):
        hook(params)
