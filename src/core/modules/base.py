"""
Base Module Class with Phase 2 execution support
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..constants import (
    DEFAULT_MAX_RETRIES,
    EXPONENTIAL_BACKOFF_BASE,
    ErrorMessages,
)


logger = logging.getLogger(__name__)


class BaseModule(ABC):
    """
    Base class for all modules.

    All modules must inherit from this class and implement:
    - validate_params(): Validate input parameters
    - execute(): Execute the module logic

    Attributes:
        module_id: Unique module identifier
        module_name: Human-readable module name
        module_description: Module description
        required_permission: Required permission for execution
        params: Input parameters
        context: Execution context
    """

    # Module metadata
    module_id: str = ""
    module_name: str = ""
    module_description: str = ""

    # Permission requirements
    required_permission: str = ""

    def __init__(self, params: Dict[str, Any], context: Dict[str, Any]):
        """
        Initialize module with parameters and context.

        Args:
            params: Input parameters for the module
            context: Execution context (shared state, browser instance, etc.)
        """
        self.params = params
        self.context = context
        self.validate_params()

    @abstractmethod
    def validate_params(self) -> None:
        """Validate input parameters. Raise ValueError if invalid."""
        pass

    @abstractmethod
    async def execute(self) -> Any:
        """Execute module logic and return result."""
        pass

    async def run(self) -> Any:
        """
        Execute module with Phase 2 enhancements:
        - Timeout support
        - Retry logic
        - Error handling

        Returns:
            Module execution result
        """
        # Defer import to avoid circular dependency
        from .registry import ModuleRegistry

        # Get module metadata for Phase 2 settings
        metadata = ModuleRegistry.get_metadata(self.module_id) or {}

        timeout = metadata.get('timeout')
        retryable = metadata.get('retryable', False)
        max_retries = metadata.get('max_retries', DEFAULT_MAX_RETRIES)

        # Execute with appropriate strategy
        if timeout:
            return await self._execute_with_resilience(
                timeout=timeout,
                retryable=retryable,
                max_retries=max_retries
            )
        elif retryable:
            return await self._execute_with_resilience(
                timeout=None,
                retryable=True,
                max_retries=max_retries
            )
        else:
            return await self.execute()

    async def _execute_with_resilience(
        self,
        timeout: Optional[int] = None,
        retryable: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES
    ) -> Any:
        """
        Execute with timeout and/or retry support.

        Args:
            timeout: Timeout in seconds (None for no timeout)
            retryable: Whether to retry on failure
            max_retries: Maximum number of retry attempts

        Returns:
            Module execution result

        Raises:
            TimeoutError: If execution times out
            Exception: If all retries are exhausted
        """
        attempts = max_retries if retryable else 1
        last_exception: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                if timeout:
                    return await asyncio.wait_for(
                        self.execute(),
                        timeout=timeout
                    )
                else:
                    return await self.execute()

            except asyncio.TimeoutError:
                error_msg = ErrorMessages.format(
                    ErrorMessages.TIMEOUT_ERROR,
                    module_id=self.module_id,
                    timeout=timeout
                )
                if attempt == attempts - 1:
                    logger.error(f"{error_msg} (after {attempts} attempts)")
                    raise TimeoutError(error_msg)
                logger.warning(f"{error_msg}, retrying...")
                last_exception = TimeoutError(error_msg)

            except Exception as e:
                last_exception = e
                if attempt == attempts - 1:
                    error_msg = ErrorMessages.format(
                        ErrorMessages.RETRY_EXHAUSTED,
                        module_id=self.module_id,
                        attempts=attempts
                    )
                    logger.error(f"{error_msg}: {e}")
                    raise Exception(error_msg) from e
                logger.warning(f"Module {self.module_id} failed, retrying: {e}")

            # Exponential backoff between retries
            if attempt < attempts - 1:
                backoff_time = EXPONENTIAL_BACKOFF_BASE ** attempt
                await asyncio.sleep(backoff_time)

        # Should not reach here
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected execution state")

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get module metadata.

        Returns:
            Dictionary containing module metadata
        """
        return {
            "id": self.module_id,
            "name": self.module_name,
            "description": self.module_description,
            "required_permission": self.required_permission
        }

    def get_param(self, name: str, default: Any = None) -> Any:
        """
        Get a parameter value with optional default.

        Args:
            name: Parameter name
            default: Default value if not present

        Returns:
            Parameter value or default
        """
        return self.params.get(name, default)

    def require_param(self, name: str) -> Any:
        """
        Get a required parameter value.

        Args:
            name: Parameter name

        Returns:
            Parameter value

        Raises:
            ValueError: If parameter is missing
        """
        if name not in self.params:
            raise ValueError(
                ErrorMessages.format(
                    ErrorMessages.MISSING_REQUIRED_PARAM,
                    param_name=name
                )
            )
        return self.params[name]
