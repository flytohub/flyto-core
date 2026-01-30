"""
Runtime Type Definitions

Dataclasses and types for the plugin runtime system.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class InvokeStatus(Enum):
    """Status of an invoke operation."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    VALIDATION_ERROR = "validation_error"


@dataclass
class InvokeMetrics:
    """Metrics captured during module invocation."""
    duration_ms: int = 0
    cost_points_used: int = 0
    bytes_processed: int = 0
    items_processed: int = 0


@dataclass
class InvokeError:
    """Error details from a failed invocation."""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    retryable: bool = False


@dataclass
class InvokeRequest:
    """
    Request to invoke a module step.

    Attributes:
        module_id: Plugin identifier (e.g., "flyto-official/database" or "database")
        step_id: Step within the plugin (e.g., "query")
        input_data: Input parameters matching the step's inputSchema
        config: Static configuration for the step
        context: Execution context (secrets refs, permissions, tenant info)
    """
    module_id: str
    step_id: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    # Tracing
    execution_id: Optional[str] = None
    step_run_id: Optional[str] = None

    # Timeout (0 = no timeout)
    timeout_ms: int = 0


@dataclass
class InvokeResponse:
    """
    Response from a module invocation.

    Attributes:
        ok: Whether the invocation succeeded
        data: Result data (if successful)
        error: Error details (if failed)
        metrics: Execution metrics
    """
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[InvokeError] = None
    metrics: Optional[InvokeMetrics] = None

    # For item-based execution
    items: Optional[List[Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for legacy compatibility."""
        result = {"ok": self.ok}

        if self.ok:
            if self.data is not None:
                result["data"] = self.data
            if self.items is not None:
                result["items"] = self.items
        else:
            if self.error:
                result["error"] = {
                    "code": self.error.code,
                    "message": self.error.message,
                }
                if self.error.details:
                    result["error"]["details"] = self.error.details
                if self.error.retryable:
                    result["error"]["retryable"] = True

        if self.metrics:
            result["metrics"] = {
                "durationMs": self.metrics.duration_ms,
                "costPointsUsed": self.metrics.cost_points_used,
                "bytesProcessed": self.metrics.bytes_processed,
            }

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvokeResponse":
        """Create from dictionary (legacy module response)."""
        ok = data.get("ok", True)

        error = None
        if not ok and "error" in data:
            err_data = data["error"]
            if isinstance(err_data, str):
                error = InvokeError(code="ERROR", message=err_data)
            elif isinstance(err_data, dict):
                error = InvokeError(
                    code=err_data.get("code", "ERROR"),
                    message=err_data.get("message", str(err_data)),
                    details=err_data.get("details"),
                    retryable=err_data.get("retryable", False),
                )
        elif not ok and "error" not in data:
            # Legacy format: error as string at top level
            error = InvokeError(
                code="ERROR",
                message=data.get("message", "Unknown error")
            )

        metrics = None
        if "metrics" in data:
            m = data["metrics"]
            metrics = InvokeMetrics(
                duration_ms=m.get("durationMs", m.get("duration_ms", 0)),
                cost_points_used=m.get("costPointsUsed", m.get("cost_points_used", 0)),
                bytes_processed=m.get("bytesProcessed", m.get("bytes_processed", 0)),
            )

        return cls(
            ok=ok,
            data=data.get("data"),
            error=error,
            metrics=metrics,
            items=data.get("items"),
        )


@dataclass
class TenantContext:
    """Tenant information for multi-tenant isolation."""
    tenant_id: str
    tenant_tier: str = "free"  # free, pro, team, enterprise
    isolation_mode: str = "shared_pool"  # shared_pool, dedicated_pool
    resource_limits: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SecretRef:
    """Reference to a secret (proxy mode)."""
    ref_string: str
    secret_key: str
    execution_id: str
    expires_at: float
    resolved: bool = False
