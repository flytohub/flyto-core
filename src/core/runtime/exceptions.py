# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Runtime Exceptions

Custom exceptions for the plugin runtime system. ``RuntimeError`` here deliberately shadows the builtin of the same name: it is the published base class every other exception in this module derives from and that callers catch by name, so the shadowing is suppressed at the definition rather than renamed out from under them.
"""

from typing import Any, Dict, Optional


class RuntimeError(Exception):  # noqa: A001 (public base name; see module docstring)
    """Base exception for runtime errors."""

    def __init__(
        self,
        message: str,
        code: str = "RUNTIME_ERROR",
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        """Convert to error response format."""
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.retryable:
            result["retryable"] = True
        return result


class PluginNotFoundError(RuntimeError):
    """Raised when a plugin or module cannot be found."""

    def __init__(self, plugin_id: str, step_id: Optional[str] = None):
        if step_id:
            message = f"Plugin step not found: {plugin_id}/{step_id}"
        else:
            message = f"Plugin not found: {plugin_id}"
        super().__init__(
            message=message,
            code="PLUGIN_NOT_FOUND",
            details={"plugin_id": plugin_id, "step_id": step_id},
        )
        self.plugin_id = plugin_id
        self.step_id = step_id


class PluginManagerShutdownError(PluginNotFoundError):
    """Raised when a plugin is requested from a manager that has shut down.

    A subclass of ``PluginNotFoundError`` so existing handlers — including the
    invoker's fallback to in-process modules — keep working unchanged: from the
    caller's side the plugin genuinely is no longer obtainable here. It is still
    its own type because "this manager is gone" and "no such plugin" call for
    different operator responses, and the first one is otherwise invisible.

    This exists so shutdown is final. Loading after it would build a process
    that no sweeper watches, no unload reaches, and no shutdown stops.
    """

    def __init__(self, plugin_id: str, pool_id: str = ""):
        # Base initializer rather than PluginNotFoundError's: that one bakes its
        # own message into ``args``, so amending the attributes afterwards would
        # leave ``str(exc)`` saying "Plugin not found" — the misdiagnosis this
        # type exists to prevent, in the one rendering most logs actually use.
        RuntimeError.__init__(
            self,
            message=(
                f"Plugin manager {pool_id or 'pool'} is shut down; "
                f"cannot serve plugin: {plugin_id}"
            ),
            code="PLUGIN_MANAGER_SHUTDOWN",
            details={"plugin_id": plugin_id, "step_id": None, "pool_id": pool_id},
        )
        self.plugin_id = plugin_id
        self.step_id = None
        self.pool_id = pool_id


class PluginTimeoutError(RuntimeError):
    """Raised when a plugin invocation times out."""

    def __init__(self, plugin_id: str, step_id: str, timeout_ms: int):
        super().__init__(
            message=f"Plugin timeout after {timeout_ms}ms: {plugin_id}/{step_id}",
            code="PLUGIN_TIMEOUT",
            details={
                "plugin_id": plugin_id,
                "step_id": step_id,
                "timeout_ms": timeout_ms,
            },
            retryable=True,
        )
        self.plugin_id = plugin_id
        self.step_id = step_id
        self.timeout_ms = timeout_ms


class PluginCrashedError(RuntimeError):
    """Raised when a plugin process crashes."""

    def __init__(
        self,
        plugin_id: str,
        exit_code: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(
            message=f"Plugin crashed: {plugin_id} (exit code: {exit_code})",
            code="PLUGIN_CRASHED",
            details={
                "plugin_id": plugin_id,
                "exit_code": exit_code,
                "stderr": stderr[:500] if stderr else None,
            },
            retryable=True,
        )
        self.plugin_id = plugin_id
        self.exit_code = exit_code
        self.stderr = stderr


class PluginProtocolError(RuntimeError):
    """Raised when plugin returns invalid protocol response."""

    def __init__(self, plugin_id: str, message: str):
        super().__init__(
            message=f"Plugin protocol error: {message}",
            code="PLUGIN_PROTOCOL_ERROR",
            details={"plugin_id": plugin_id},
            retryable=True,
        )
        self.plugin_id = plugin_id


class ValidationError(RuntimeError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"field": field} if field else {},
            retryable=False,
        )
        self.field = field


class PermissionDeniedError(RuntimeError):
    """Raised when a required permission is not granted."""

    def __init__(self, permission: str, plugin_id: Optional[str] = None):
        super().__init__(
            message=f"Permission denied: {permission}",
            code="PERMISSION_DENIED",
            details={"permission": permission, "plugin_id": plugin_id},
            retryable=False,
        )
        self.permission = permission
        self.plugin_id = plugin_id


class SecretNotProvidedError(RuntimeError):
    """Raised when a required secret is not in context."""

    def __init__(self, secret_key: str):
        super().__init__(
            message=f"Required secret not provided: {secret_key}",
            code="SECRET_NOT_PROVIDED",
            details={"secret_key": secret_key},
            retryable=False,
        )
        self.secret_key = secret_key


class ResourceExhaustedError(RuntimeError):
    """Raised when a resource limit is exceeded."""

    def __init__(self, resource: str, limit: Any, used: Any):
        super().__init__(
            message=f"Resource exhausted: {resource} (limit: {limit}, used: {used})",
            code="RESOURCE_EXHAUSTED",
            details={"resource": resource, "limit": limit, "used": used},
            retryable=False,
        )
        self.resource = resource
        self.limit = limit
        self.used = used


class SchemaIncompatibleError(RuntimeError):
    """Raised when workflow schema is incompatible with plugin."""

    def __init__(
        self,
        workflow_version: str,
        plugin_version: str,
        plugin_id: str,
        step_id: str,
    ):
        super().__init__(
            message=f"Schema migration required: {workflow_version} -> {plugin_version}",
            code="SCHEMA_MIGRATION_REQUIRED",
            details={
                "workflow_schema_version": workflow_version,
                "plugin_schema_version": plugin_version,
                "plugin_id": plugin_id,
                "step_id": step_id,
            },
            retryable=False,
        )
        self.workflow_version = workflow_version
        self.plugin_version = plugin_version


class PluginUnhealthyError(RuntimeError):
    """Raised when plugin is marked unhealthy after too many crashes."""

    def __init__(self, plugin_id: str, cooldown_remaining_seconds: int):
        super().__init__(
            message=f"Plugin unhealthy: {plugin_id} (cooldown: {cooldown_remaining_seconds}s)",
            code="PLUGIN_UNHEALTHY",
            details={
                "plugin_id": plugin_id,
                "cooldown_remaining_seconds": cooldown_remaining_seconds,
            },
            retryable=False,  # Must wait for cooldown
        )
        self.plugin_id = plugin_id
        self.cooldown_remaining_seconds = cooldown_remaining_seconds


class SecurityError(RuntimeError):
    """Raised when a security violation is detected."""

    def __init__(
        self,
        message: str,
        violation_type: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="SECURITY_VIOLATION",
            details={"violation_type": violation_type, **(details or {})},
            retryable=False,
        )
        self.violation_type = violation_type


class PathTraversalError(SecurityError):
    """Raised when path traversal attack is detected."""

    def __init__(self, path: str, base_dir: str):
        super().__init__(
            message="Path traversal detected: path escapes allowed directory",
            violation_type="PATH_TRAVERSAL",
            details={"attempted_path": path, "base_dir": base_dir},
        )


class UnauthorizedAccessError(SecurityError):
    """Raised when unauthorized access is attempted."""

    def __init__(self, resource: str, plugin_id: Optional[str] = None):
        super().__init__(
            message=f"Unauthorized access to resource: {resource}",
            violation_type="UNAUTHORIZED_ACCESS",
            details={"resource": resource, "plugin_id": plugin_id},
        )


class InvalidSessionTokenError(SecurityError):
    """Raised when an invalid session token is provided."""

    def __init__(self, session_id: str):
        super().__init__(
            message="Invalid or missing session token",
            violation_type="INVALID_SESSION_TOKEN",
            details={"session_id": session_id},
        )
