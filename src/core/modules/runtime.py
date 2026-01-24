"""
Module Runtime - Unified module execution wrapper.

This module provides the execute_module() function that wraps all module execution.
It ensures consistent return formats, error handling, and execution metadata.

Design Principles:
- Single responsibility: Only handles execution wrapping
- Atomic: Independent of specific module implementations
- No hardcoding: Timeouts and codes from constants
- Backwards compatible: Handles old return patterns

All module execution should go through this wrapper:
    result = await execute_module(module_fn, params, context, module_id)
"""
import asyncio
import logging
import time
import traceback
from typing import Any, Callable, Coroutine, Dict, Optional, Union

from ..constants import DEFAULT_TIMEOUT_MS, ErrorCode, ProductionPolicy, ErrorMessages
from .result import ModuleResult
from .errors import ModuleError, ExecutionTimeoutError, ForbiddenError
import os

logger = logging.getLogger(__name__)


def _get_current_env() -> str:
    """Get current environment from FLYTO_ENV or default to 'local'."""
    return os.environ.get("FLYTO_ENV", "local")


def check_capabilities(
    capabilities: list,
    module_id: str,
    env: Optional[str] = None
) -> Optional[ModuleResult]:
    """
    Check if module capabilities are allowed in current environment.

    Args:
        capabilities: List of capability strings from module metadata
        module_id: Module identifier for error messages
        env: Environment override (default: from FLYTO_ENV)

    Returns:
        None if all capabilities allowed, ModuleResult.failure() if denied
    """
    if not capabilities:
        return None

    current_env = env or _get_current_env()
    allowed, denied_caps = ProductionPolicy.check_capabilities(capabilities, current_env)

    if not allowed:
        # Log the denial
        logger.warning(
            f"Capability denied for module {module_id}: {denied_caps} in {current_env}",
            extra={"module_id": module_id, "denied_capabilities": denied_caps, "env": current_env}
        )

        # Return failure result
        return ModuleResult.failure(
            error=ErrorMessages.format(
                ErrorMessages.CAPABILITY_DENIED,
                module_id=module_id,
                capability=denied_caps[0],  # First denied capability
                env=current_env
            ),
            error_code=ErrorCode.FORBIDDEN,
            meta={"module_id": module_id},
            details={
                "denied_capabilities": denied_caps,
                "environment": current_env
            }
        )

    return None


def _check_license(
    module_id: str,
    required_tier: Optional[str],
    required_feature: Optional[str],
    meta: Dict[str, Any],
) -> Optional[ModuleResult]:
    """
    Check if current license allows module execution.

    Args:
        module_id: Module identifier
        required_tier: Required license tier ("free", "pro", "enterprise")
        required_feature: Required feature flag (e.g., "DESKTOP_AUTOMATION")
        meta: Execution metadata for error response

    Returns:
        None if license check passes, ModuleResult.failure() if denied
    """
    try:
        from ..licensing import LicenseManager, LicenseError, FeatureFlag, LicenseTier

        manager = LicenseManager.get_instance()
        current_tier = manager.get_tier()

        # Check tier requirement
        if required_tier:
            tier_order = {
                LicenseTier.FREE: 0,
                LicenseTier.PRO: 1,
                LicenseTier.ENTERPRISE: 2,
            }
            required_tier_enum = LicenseTier(required_tier.lower())
            if tier_order.get(current_tier, 0) < tier_order.get(required_tier_enum, 0):
                logger.warning(
                    f"License tier denied for module {module_id}: requires {required_tier}, has {current_tier.value}",
                    extra={"module_id": module_id, "required_tier": required_tier, "current_tier": current_tier.value}
                )
                return ModuleResult.failure(
                    error=f"Module '{module_id}' requires {required_tier} license (current: {current_tier.value})",
                    error_code=ErrorCode.FORBIDDEN,
                    meta=meta,
                    details={
                        "required_tier": required_tier,
                        "current_tier": current_tier.value,
                        "upgrade_url": "/pricing",
                    }
                )

        # Check feature requirement
        if required_feature:
            try:
                feature = FeatureFlag(required_feature.upper()) if isinstance(required_feature, str) else required_feature
                if not manager.has_feature(feature):
                    logger.warning(
                        f"Feature denied for module {module_id}: requires {required_feature}",
                        extra={"module_id": module_id, "required_feature": required_feature}
                    )
                    return ModuleResult.failure(
                        error=f"Module '{module_id}' requires feature '{required_feature}' which is not available in your license",
                        error_code=ErrorCode.FORBIDDEN,
                        meta=meta,
                        details={
                            "required_feature": required_feature,
                            "current_tier": current_tier.value,
                            "upgrade_url": "/pricing",
                        }
                    )
            except ValueError:
                # Unknown feature flag - allow (fail open for forwards compatibility)
                pass

    except ImportError:
        # Licensing module not available - allow execution (fail open)
        pass
    except Exception as e:
        # License check error - log but allow execution (fail open)
        logger.debug(f"License check error for {module_id}: {e}")

    return None


async def execute_module(
    module_fn: Callable[..., Coroutine[Any, Any, Any]],
    params: Dict[str, Any],
    context: Dict[str, Any],
    module_id: str,
    timeout_ms: Optional[int] = None,
    request_id: Optional[str] = None,
    capabilities: Optional[list] = None,
    env: Optional[str] = None,
    required_tier: Optional[str] = None,
    required_feature: Optional[str] = None,
) -> ModuleResult:
    """
    Execute a module function with standardized result handling.

    This is the unified entry point for all module execution. It:
    1. Checks capabilities against production policy (if provided)
    2. Wraps successful returns in ModuleResult.success()
    3. Converts ModuleError exceptions to ModuleResult.failure()
    4. Handles old return patterns (ok/status) for backwards compatibility
    5. Enforces timeout
    6. Records execution metadata

    Args:
        module_fn: Async function to execute (module's execute method or function)
        params: Module parameters
        context: Execution context (browser, page, etc.)
        module_id: Module identifier for logging
        timeout_ms: Execution timeout in milliseconds (default: 30000)
        request_id: Request ID for tracing

        capabilities: List of capability strings from module metadata (for enforcement)
        env: Environment override for capability check (default: from FLYTO_ENV)

    Returns:
        ModuleResult with execution outcome

    Example:
        async def my_module(context):
            params = context['params']
            return {"result": params["x"] + params["y"]}

        result = await execute_module(
            my_module,
            {"x": 1, "y": 2},
            {},
            "math.add"
        )
        # result.ok == True
        # result.data == {"result": 3}
    """
    effective_timeout_ms = timeout_ms or DEFAULT_TIMEOUT_MS
    effective_request_id = request_id or context.get("request_id", "unknown")

    start_time = time.time()
    meta: Dict[str, Any] = {
        "module_id": module_id,
        "request_id": effective_request_id,
    }

    # P0-4: Check capabilities before execution
    if capabilities:
        capability_result = check_capabilities(capabilities, module_id, env)
        if capability_result is not None:
            # Capability denied - return failure immediately
            return capability_result

    # License tier check before execution
    if required_tier or required_feature:
        license_result = _check_license(module_id, required_tier, required_feature, meta)
        if license_result is not None:
            return license_result

    try:
        # Build execution context
        exec_context = {
            "params": params,
            **context
        }

        # Execute with timeout
        raw_result = await asyncio.wait_for(
            module_fn(exec_context),
            timeout=effective_timeout_ms / 1000
        )

        # Record duration
        duration_ms = int((time.time() - start_time) * 1000)
        meta["duration_ms"] = duration_ms

        # Process result
        return _normalize_result(raw_result, meta)

    except ModuleError as e:
        # Expected module error - convert to failure
        duration_ms = int((time.time() - start_time) * 1000)
        meta["duration_ms"] = duration_ms

        logger.warning(
            f"Module {module_id} failed with {e.code}: {e.message}",
            extra={"module_id": module_id, "error_code": e.code}
        )

        return ModuleResult.failure(
            error=e.message,
            error_code=e.code,
            meta=meta,
            details=e.to_dict()
        )

    except asyncio.TimeoutError:
        # Timeout
        duration_ms = int((time.time() - start_time) * 1000)
        meta["duration_ms"] = duration_ms

        logger.error(
            f"Module {module_id} timed out after {effective_timeout_ms}ms",
            extra={"module_id": module_id}
        )

        return ModuleResult.failure(
            error=f"Module {module_id} timed out after {effective_timeout_ms}ms",
            error_code=ErrorCode.TIMEOUT,
            meta=meta,
            details={"timeout_ms": effective_timeout_ms}
        )

    except asyncio.CancelledError:
        # Cancelled
        duration_ms = int((time.time() - start_time) * 1000)
        meta["duration_ms"] = duration_ms

        logger.info(
            f"Module {module_id} was cancelled",
            extra={"module_id": module_id}
        )

        return ModuleResult.failure(
            error=f"Module {module_id} execution was cancelled",
            error_code=ErrorCode.CANCELLED,
            meta=meta
        )

    except Exception as e:
        # Unexpected error
        duration_ms = int((time.time() - start_time) * 1000)
        meta["duration_ms"] = duration_ms

        # SECURITY: Log traceback but don't expose to API response
        # Traceback is logged for debugging but not included in meta
        logger.error(
            f"Module {module_id} failed with unexpected error: {e}",
            exc_info=True,
            extra={"module_id": module_id, "traceback": traceback.format_exc()}
        )

        return ModuleResult.failure(
            error=str(e),
            error_code=ErrorCode.EXECUTION_ERROR,
            meta=meta
        )


def _normalize_result(
    raw_result: Any,
    meta: Dict[str, Any]
) -> ModuleResult:
    """
    Normalize module return value to ModuleResult.

    Handles:
    1. Already ModuleResult - return as is
    2. Dict with 'ok' key - legacy OK pattern
    3. Dict with 'status' == 'error' - legacy Status pattern
    4. Any other value - wrap as success data

    Args:
        raw_result: Raw return value from module
        meta: Execution metadata

    Returns:
        Normalized ModuleResult
    """
    # Already a ModuleResult
    if isinstance(raw_result, ModuleResult):
        # Merge metadata
        if raw_result.meta:
            raw_result.meta.update(meta)
        else:
            raw_result.meta = meta
        return raw_result

    # Dict with patterns to detect
    if isinstance(raw_result, dict):
        # Pattern A: OK Pattern {"ok": True/False, ...}
        if "ok" in raw_result:
            ok_value = raw_result.get("ok")

            if ok_value:
                # Success - extract data
                # If 'data' key exists, use it directly
                # Otherwise, strip protocol keys and use remaining as data
                if "data" in raw_result:
                    data = raw_result["data"]
                else:
                    # Strip protocol keys to avoid double semantics
                    # e.g. {ok: true, foo: 1} → data = {foo: 1}
                    protocol_keys = {"ok", "error", "error_code", "status", "message", "meta"}
                    data = {k: v for k, v in raw_result.items() if k not in protocol_keys}
                    # If nothing left after stripping, use empty dict
                    if not data:
                        data = {}
                return ModuleResult.success(data=data, meta=meta)
            else:
                # Failure - extract error info
                error = raw_result.get("error")
                error_code = raw_result.get("error_code", ErrorCode.EXECUTION_ERROR)

                # Handle nested error object: {"ok": false, "error": {"code": ..., "message": ...}}
                if isinstance(error, dict):
                    error_code = error.get("code", error_code)
                    error_message = error.get("message", str(error))
                    details = {k: v for k, v in error.items() if k not in ("code", "message")}
                    return ModuleResult.failure(
                        error=error_message,
                        error_code=error_code,
                        meta=meta,
                        details=details if details else None
                    )
                else:
                    return ModuleResult.failure(
                        error=str(error) if error else "Unknown error",
                        error_code=error_code,
                        meta=meta
                    )

        # Pattern B: Status Pattern {"status": "error", "message": ...}
        # DEPRECATED: Only handle error case for backwards compatibility
        # Other status values (success, ok) fall through to raw data
        if raw_result.get("status") == "error":
            message = raw_result.get("message", "Unknown error")
            error_code = raw_result.get("error_code", ErrorCode.EXECUTION_ERROR)
            return ModuleResult.failure(
                error=message,
                error_code=error_code,
                meta=meta
            )

    # Raw data - wrap as success
    return ModuleResult.success(data=raw_result, meta=meta)


async def execute_module_with_retry(
    module_fn: Callable[..., Coroutine[Any, Any, Any]],
    params: Dict[str, Any],
    context: Dict[str, Any],
    module_id: str,
    max_retries: int = 3,
    retry_delay_ms: int = 1000,
    timeout_ms: Optional[int] = None,
    request_id: Optional[str] = None,
    retryable_codes: Optional[set] = None
) -> ModuleResult:
    """
    Execute a module with automatic retries.

    Args:
        module_fn: Async function to execute
        params: Module parameters
        context: Execution context
        module_id: Module identifier
        max_retries: Maximum retry attempts (default: 3)
        retry_delay_ms: Delay between retries in ms (default: 1000)
        timeout_ms: Per-attempt timeout in ms
        request_id: Request ID for tracing
        retryable_codes: Set of error codes that should trigger retry

    Returns:
        ModuleResult from successful execution or final failure
    """
    default_retryable = {
        ErrorCode.TIMEOUT,
        ErrorCode.NETWORK_ERROR,
        ErrorCode.RATE_LIMITED,
        ErrorCode.API_ERROR,
    }
    effective_retryable = retryable_codes or default_retryable

    last_result: Optional[ModuleResult] = None
    attempts = 0

    for attempt in range(max_retries + 1):
        attempts = attempt + 1

        result = await execute_module(
            module_fn=module_fn,
            params=params,
            context=context,
            module_id=module_id,
            timeout_ms=timeout_ms,
            request_id=request_id
        )

        # Success - return immediately
        if result.ok:
            if attempts > 1 and result.meta:
                result.meta["retry_attempts"] = attempts
            return result

        last_result = result

        # Check if should retry
        if result.error_code not in effective_retryable:
            # Non-retryable error
            return result

        # Last attempt - don't delay
        if attempt >= max_retries:
            break

        # Exponential backoff
        delay_seconds = (retry_delay_ms / 1000) * (2 ** attempt)
        logger.info(
            f"Module {module_id} failed, retrying in {delay_seconds:.1f}s "
            f"(attempt {attempts}/{max_retries + 1})",
            extra={"module_id": module_id, "attempt": attempts}
        )
        await asyncio.sleep(delay_seconds)

    # All retries exhausted
    if last_result:
        last_result.error_code = ErrorCode.RETRY_EXHAUSTED
        if last_result.meta:
            last_result.meta["retry_attempts"] = attempts
        return last_result

    # Should never reach here
    return ModuleResult.failure(
        error=f"Module {module_id} failed after {attempts} attempts",
        error_code=ErrorCode.RETRY_EXHAUSTED,
        meta={"retry_attempts": attempts}
    )


def wrap_sync_module(
    sync_fn: Callable[..., Any]
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """
    Wrap a synchronous module function to be async.

    Args:
        sync_fn: Synchronous function

    Returns:
        Async wrapper function
    """
    async def async_wrapper(context: Dict[str, Any]) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_fn, context)

    return async_wrapper
