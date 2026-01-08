"""
Module Result - Standardized execution result structure.

This module provides the ModuleResult dataclass for consistent module return values.
All modules should return data that gets wrapped by the runtime into ModuleResult.

Design Principles:
- Single responsibility: Only handles result structure
- Atomic: Independent of module execution logic
- No hardcoding: Uses ErrorCode from constants
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from ..constants import ErrorCode


# Meta keys that are safe to expose to API responses
# Any other keys are considered internal and will be filtered out
PUBLIC_META_KEYS: Set[str] = {
    "module_id",
    "request_id",
    "duration_ms",
    "retry_attempts",
    "error_details",
    "hint",
}


@dataclass
class ModuleResult:
    """
    Standardized module execution result.

    All module returns are wrapped in this structure by the runtime.
    Modules should NOT construct this directly - they should:
    1. Return raw data (runtime wraps in success)
    2. Raise ModuleError (runtime wraps in failure)

    Attributes:
        ok: Whether execution succeeded
        data: Result data (success only)
        error: Error message (failure only)
        error_code: Error code from ErrorCode class (failure only)
        meta: Execution metadata (timing, module_id, etc.)

    Example success:
        ModuleResult(ok=True, data={"result": "hello"}, meta={"duration_ms": 42})

    Example failure:
        ModuleResult(ok=False, error="File not found", error_code="FILE_NOT_FOUND")
    """

    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    meta: Optional[Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        """Validate result consistency."""
        if self.ok:
            if self.error is not None or self.error_code is not None:
                raise ValueError("Success result cannot have error or error_code")
        else:
            if self.error is None:
                raise ValueError("Failure result must have error message")

    @classmethod
    def success(
        cls,
        data: Any = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> "ModuleResult":
        """
        Create a success result.

        Args:
            data: Result data (any type)
            meta: Execution metadata

        Returns:
            ModuleResult with ok=True
        """
        return cls(
            ok=True,
            data=data,
            meta=meta or {}
        )

    @classmethod
    def failure(
        cls,
        error: str,
        error_code: str,
        meta: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> "ModuleResult":
        """
        Create a failure result.

        Args:
            error: Human-readable error message
            error_code: Error code from ErrorCode class
            meta: Execution metadata
            details: Additional error details (field, hint, etc.)

        Returns:
            ModuleResult with ok=False
        """
        result_meta = meta or {}
        if details:
            result_meta["error_details"] = details
        return cls(
            ok=False,
            error=error,
            error_code=error_code,
            meta=result_meta
        )

    def to_dict(self, include_internal: bool = False) -> Dict[str, Any]:
        """
        Convert to dictionary format.

        Args:
            include_internal: If True, include all meta keys. If False (default),
                            only include PUBLIC_META_KEYS for security.

        Returns:
            Dictionary with ok, data/error fields, and optional meta
        """
        result: Dict[str, Any] = {"ok": self.ok}

        if self.ok:
            if self.data is not None:
                result["data"] = self.data
        else:
            result["error"] = self.error
            result["error_code"] = self.error_code

        if self.meta:
            if include_internal:
                result["meta"] = self.meta
            else:
                # Filter to only public meta keys
                public_meta = {k: v for k, v in self.meta.items() if k in PUBLIC_META_KEYS}
                if public_meta:
                    result["meta"] = public_meta

        return result

    def to_public_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format for API responses (security-safe).

        This method filters out internal meta keys like traceback, debug_info, etc.
        Use this for API responses to clients.

        Returns:
            Dictionary with ok, data/error fields, and filtered meta
        """
        return self.to_dict(include_internal=False)

    def to_internal_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format with all meta (for logging/debugging).

        This includes internal keys like traceback. Only use for internal logging.

        Returns:
            Dictionary with ok, data/error fields, and all meta
        """
        return self.to_dict(include_internal=True)

    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Convert to legacy format for backwards compatibility.

        Some consumers expect error as nested object:
        {"ok": False, "error": {"code": "...", "message": "..."}}

        Returns:
            Dictionary in legacy format
        """
        result: Dict[str, Any] = {"ok": self.ok}

        if self.ok:
            if self.data is not None:
                result["data"] = self.data
        else:
            error_obj: Dict[str, Any] = {
                "code": self.error_code,
                "message": self.error
            }
            # Include error_details if present in meta
            if self.meta and "error_details" in self.meta:
                error_obj.update(self.meta["error_details"])
            result["error"] = error_obj

        if self.meta:
            # Copy meta without error_details (already in error object)
            clean_meta = {k: v for k, v in self.meta.items() if k != "error_details"}
            if clean_meta:
                result["meta"] = clean_meta

        return result

    @property
    def is_success(self) -> bool:
        """Check if result is success."""
        return self.ok

    @property
    def is_failure(self) -> bool:
        """Check if result is failure."""
        return not self.ok

    def unwrap(self) -> Any:
        """
        Get data or raise exception if failure.

        Returns:
            Result data

        Raises:
            ValueError: If result is failure
        """
        if not self.ok:
            raise ValueError(f"Cannot unwrap failure: {self.error} ({self.error_code})")
        return self.data

    def unwrap_or(self, default: Any) -> Any:
        """
        Get data or return default if failure.

        Args:
            default: Default value to return on failure

        Returns:
            Result data or default
        """
        return self.data if self.ok else default
