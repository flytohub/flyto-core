"""
Module Result Contract v1.0

Defines the standard contract for module execution results.
All modules MUST return results conforming to this contract.

Design principles:
- Explicit success/failure via `ok` field
- Rich error information for debugging
- Optional warnings for non-fatal issues
- Metrics for observability
- Extensible metadata
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ResultStatus(Enum):
    """
    Execution result status.

    More granular than simple success/failure.
    """
    SUCCESS = "success"           # Completed successfully
    PARTIAL = "partial"           # Partially completed
    SKIPPED = "skipped"           # Intentionally skipped
    FAILED = "failed"             # Failed with error
    TIMEOUT = "timeout"           # Timed out
    CANCELLED = "cancelled"       # Cancelled by user/system


class WarningLevel(Enum):
    """Warning severity levels"""
    LOW = "low"           # Minor issue, can be ignored
    MEDIUM = "medium"     # Should be reviewed
    HIGH = "high"         # Important, may cause issues later


@dataclass
class Warning:
    """
    A non-fatal warning from module execution.

    Warnings indicate issues that didn't prevent completion
    but should be reviewed.
    """
    code: str                           # Warning code (e.g., "SLOW_RESPONSE")
    message: str                        # Human-readable message
    level: WarningLevel = WarningLevel.LOW
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "level": self.level.value,
            "details": self.details,
        }


@dataclass
class ErrorInfo:
    """
    Structured error information.

    Provides rich context for debugging and error handling.
    """
    code: str                           # Error code (e.g., "ELEMENT_NOT_FOUND")
    message: str                        # Human-readable message
    error_type: str = ""                # Exception type name
    recoverable: bool = False           # Can this error be recovered from?
    retry_suggested: bool = False       # Should the operation be retried?
    details: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None   # For debugging only

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.code,
            "message": self.message,
            "error_type": self.error_type,
            "recoverable": self.recoverable,
            "retry_suggested": self.retry_suggested,
        }
        if self.details:
            result["details"] = self.details
        return result

    @classmethod
    def from_exception(
        cls,
        error: Exception,
        code: str = "UNKNOWN_ERROR",
        recoverable: bool = False,
        retry_suggested: bool = False,
    ) -> "ErrorInfo":
        """Create ErrorInfo from an exception"""
        import traceback
        return cls(
            code=code,
            message=str(error),
            error_type=type(error).__name__,
            recoverable=recoverable,
            retry_suggested=retry_suggested,
            stack_trace=traceback.format_exc(),
        )


@dataclass
class ExecutionMetrics:
    """
    Metrics collected during module execution.

    Used for monitoring, debugging, and optimization.
    """
    duration_ms: float = 0.0           # Total execution time
    start_time: Optional[str] = None   # ISO timestamp
    end_time: Optional[str] = None     # ISO timestamp
    retry_count: int = 0               # Number of retries
    memory_bytes: Optional[int] = None # Memory used (if tracked)
    api_calls: int = 0                 # External API calls made
    bytes_transferred: int = 0         # Network bytes

    # Custom metrics
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "api_calls": self.api_calls,
            "bytes_transferred": self.bytes_transferred,
        }
        if self.start_time:
            result["start_time"] = self.start_time
        if self.end_time:
            result["end_time"] = self.end_time
        if self.memory_bytes:
            result["memory_bytes"] = self.memory_bytes
        if self.custom:
            result["custom"] = self.custom
        return result


@dataclass
class ModuleResult:
    """
    Standard result contract for module execution.

    Every module execution MUST return a ModuleResult.

    Fields:
    - ok: Boolean success indicator (required)
    - status: Detailed status enum
    - output: The actual result data (if successful)
    - error: Structured error info (if failed)
    - warnings: Non-fatal warnings
    - metrics: Execution metrics
    - meta: Additional metadata

    Usage:
        # Success
        return ModuleResult.success({"data": extracted_text})

        # Failure
        return ModuleResult.failure(
            code="ELEMENT_NOT_FOUND",
            message="Could not find element with selector: #button"
        )

        # With warnings
        result = ModuleResult.success(data)
        result.add_warning("SLOW_RESPONSE", "Response took >5s")
        return result
    """
    # Core fields (required)
    ok: bool
    status: ResultStatus

    # Result data
    output: Optional[Any] = None

    # Error information (when ok=False)
    error: Optional[ErrorInfo] = None

    # Non-fatal warnings
    warnings: List[Warning] = field(default_factory=list)

    # Execution metrics
    metrics: ExecutionMetrics = field(default_factory=ExecutionMetrics)

    # Extensible metadata
    meta: Dict[str, Any] = field(default_factory=dict)

    # Module identification
    module_id: Optional[str] = None
    step_id: Optional[str] = None

    def __post_init__(self):
        """Validate result consistency"""
        if self.ok and self.status == ResultStatus.FAILED:
            logger.warning("Inconsistent result: ok=True but status=FAILED")
        if not self.ok and self.error is None:
            logger.warning("Failed result without error info")

    def add_warning(
        self,
        code: str,
        message: str,
        level: WarningLevel = WarningLevel.LOW,
        details: Optional[Dict[str, Any]] = None,
    ) -> "ModuleResult":
        """
        Add a warning to the result.

        Returns self for method chaining.
        """
        self.warnings.append(Warning(
            code=code,
            message=message,
            level=level,
            details=details,
        ))
        return self

    def has_warnings(self) -> bool:
        """Check if result has any warnings"""
        return len(self.warnings) > 0

    def get_warnings_by_level(self, level: WarningLevel) -> List[Warning]:
        """Get warnings filtered by level"""
        return [w for w in self.warnings if w.level == level]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {
            "ok": self.ok,
            "status": self.status.value,
        }

        if self.output is not None:
            result["output"] = self.output

        if self.error:
            result["error"] = self.error.to_dict()

        if self.warnings:
            result["warnings"] = [w.to_dict() for w in self.warnings]

        if self.metrics:
            result["metrics"] = self.metrics.to_dict()

        if self.meta:
            result["meta"] = self.meta

        if self.module_id:
            result["module_id"] = self.module_id

        if self.step_id:
            result["step_id"] = self.step_id

        return result

    # ==========================================================================
    # Factory methods for common cases
    # ==========================================================================

    @classmethod
    def success(
        cls,
        output: Any = None,
        metrics: Optional[ExecutionMetrics] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "ModuleResult":
        """
        Create a successful result.

        Args:
            output: The result data
            metrics: Optional execution metrics
            meta: Optional metadata

        Returns:
            ModuleResult with ok=True
        """
        return cls(
            ok=True,
            status=ResultStatus.SUCCESS,
            output=output,
            metrics=metrics or ExecutionMetrics(),
            meta=meta or {},
        )

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        error_type: str = "",
        recoverable: bool = False,
        retry_suggested: bool = False,
        details: Optional[Dict[str, Any]] = None,
        metrics: Optional[ExecutionMetrics] = None,
    ) -> "ModuleResult":
        """
        Create a failed result.

        Args:
            code: Error code
            message: Error message
            error_type: Exception type name
            recoverable: Whether error is recoverable
            retry_suggested: Whether retry might help
            details: Additional error details
            metrics: Optional execution metrics

        Returns:
            ModuleResult with ok=False
        """
        return cls(
            ok=False,
            status=ResultStatus.FAILED,
            error=ErrorInfo(
                code=code,
                message=message,
                error_type=error_type,
                recoverable=recoverable,
                retry_suggested=retry_suggested,
                details=details,
            ),
            metrics=metrics or ExecutionMetrics(),
        )

    @classmethod
    def from_exception(
        cls,
        error: Exception,
        code: str = "EXECUTION_ERROR",
        recoverable: bool = False,
        retry_suggested: bool = False,
        metrics: Optional[ExecutionMetrics] = None,
    ) -> "ModuleResult":
        """
        Create a failed result from an exception.

        Args:
            error: The exception that occurred
            code: Error code
            recoverable: Whether error is recoverable
            retry_suggested: Whether retry might help
            metrics: Optional execution metrics

        Returns:
            ModuleResult with ok=False
        """
        return cls(
            ok=False,
            status=ResultStatus.FAILED,
            error=ErrorInfo.from_exception(
                error,
                code=code,
                recoverable=recoverable,
                retry_suggested=retry_suggested,
            ),
            metrics=metrics or ExecutionMetrics(),
        )

    @classmethod
    def timeout(
        cls,
        message: str = "Operation timed out",
        timeout_seconds: Optional[float] = None,
        metrics: Optional[ExecutionMetrics] = None,
    ) -> "ModuleResult":
        """
        Create a timeout result.

        Args:
            message: Timeout message
            timeout_seconds: The timeout value
            metrics: Optional execution metrics

        Returns:
            ModuleResult with timeout status
        """
        details = None
        if timeout_seconds is not None:
            details = {"timeout_seconds": timeout_seconds}

        return cls(
            ok=False,
            status=ResultStatus.TIMEOUT,
            error=ErrorInfo(
                code="TIMEOUT",
                message=message,
                error_type="TimeoutError",
                recoverable=True,
                retry_suggested=True,
                details=details,
            ),
            metrics=metrics or ExecutionMetrics(),
        )

    @classmethod
    def skipped(
        cls,
        reason: str = "Step skipped",
        meta: Optional[Dict[str, Any]] = None,
    ) -> "ModuleResult":
        """
        Create a skipped result.

        Used when a step is intentionally skipped.

        Args:
            reason: Why the step was skipped
            meta: Optional metadata

        Returns:
            ModuleResult with skipped status
        """
        return cls(
            ok=True,
            status=ResultStatus.SKIPPED,
            meta={"skip_reason": reason, **(meta or {})},
        )

    @classmethod
    def cancelled(
        cls,
        reason: str = "Operation cancelled",
        metrics: Optional[ExecutionMetrics] = None,
    ) -> "ModuleResult":
        """
        Create a cancelled result.

        Args:
            reason: Why the operation was cancelled
            metrics: Optional execution metrics

        Returns:
            ModuleResult with cancelled status
        """
        return cls(
            ok=False,
            status=ResultStatus.CANCELLED,
            error=ErrorInfo(
                code="CANCELLED",
                message=reason,
                recoverable=False,
                retry_suggested=False,
            ),
            metrics=metrics or ExecutionMetrics(),
        )

    @classmethod
    def partial(
        cls,
        output: Any,
        reason: str,
        metrics: Optional[ExecutionMetrics] = None,
    ) -> "ModuleResult":
        """
        Create a partial success result.

        Used when operation completed but with incomplete data.

        Args:
            output: The partial result data
            reason: Why result is partial
            metrics: Optional execution metrics

        Returns:
            ModuleResult with partial status
        """
        result = cls(
            ok=True,
            status=ResultStatus.PARTIAL,
            output=output,
            metrics=metrics or ExecutionMetrics(),
            meta={"partial_reason": reason},
        )
        result.add_warning(
            "PARTIAL_RESULT",
            reason,
            level=WarningLevel.MEDIUM,
        )
        return result


# =============================================================================
# Result validation
# =============================================================================

def validate_result(result: Any) -> bool:
    """
    Validate that a result conforms to the ModuleResult contract.

    Args:
        result: The result to validate

    Returns:
        True if valid, False otherwise

    Raises:
        TypeError: If result is not a ModuleResult
    """
    if not isinstance(result, ModuleResult):
        raise TypeError(
            f"Expected ModuleResult, got {type(result).__name__}. "
            "All modules must return ModuleResult."
        )

    # Check consistency
    if result.ok and result.status == ResultStatus.FAILED:
        logger.error("Invalid result: ok=True but status=FAILED")
        return False

    if not result.ok and result.status == ResultStatus.SUCCESS:
        logger.error("Invalid result: ok=False but status=SUCCESS")
        return False

    if not result.ok and result.error is None:
        logger.warning("Result failed but no error info provided")

    return True


def wrap_legacy_result(result: Any, module_id: str = "") -> ModuleResult:
    """
    Wrap a legacy (non-contract) result in ModuleResult.

    For backward compatibility with modules that don't yet
    return ModuleResult.

    Args:
        result: The legacy result
        module_id: Module that produced the result

    Returns:
        ModuleResult wrapping the legacy result
    """
    if isinstance(result, ModuleResult):
        return result

    if isinstance(result, dict):
        # Check if it looks like an error dict
        if "error" in result or "ok" in result and not result.get("ok"):
            return ModuleResult.failure(
                code=result.get("error_code", "LEGACY_ERROR"),
                message=str(result.get("error", result.get("message", "Unknown error"))),
            )
        # Assume success
        return ModuleResult.success(output=result)

    if isinstance(result, Exception):
        return ModuleResult.from_exception(result)

    # Wrap anything else as success
    return ModuleResult.success(output=result, meta={"module_id": module_id})
