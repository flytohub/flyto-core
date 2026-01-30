"""
Runtime Exceptions

Custom exceptions for the plugin runtime system.
"""

from typing import Any, Dict, Optional


class RuntimeError(Exception):
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
