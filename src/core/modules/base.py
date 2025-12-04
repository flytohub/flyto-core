"""
Base Module Class with Phase 2 execution support
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
import asyncio
import time
from functools import wraps


class BaseModule(ABC):
    """Base class for all modules"""

    # Module metadata
    module_id: str = ""
    module_name: str = ""
    module_description: str = ""

    # Permission requirements
    required_permission: str = ""

    def __init__(self, params: Dict[str, Any], context: Dict[str, Any]):
        self.params = params
        self.context = context
        self.validate_params()

    @abstractmethod
    def validate_params(self):
        """Validate parameters"""
        pass

    @abstractmethod
    async def execute(self) -> Any:
        """Execute module"""
        pass

    async def run(self) -> Any:
        """
        Execute module with Phase 2 enhancements:
        - Timeout support
        - Retry logic
        - Error handling
        """
        from .registry import ModuleRegistry

        # Get module metadata for Phase 2 settings
        metadata = ModuleRegistry.get_metadata(self.module_id) or {}

        timeout = metadata.get('timeout')
        retryable = metadata.get('retryable', False)
        max_retries = metadata.get('max_retries', 3)

        # Execute with timeout if specified
        if timeout:
            return await self._execute_with_timeout(timeout, retryable, max_retries)
        elif retryable:
            return await self._execute_with_retry(max_retries)
        else:
            return await self.execute()

    async def _execute_with_timeout(self, timeout: int, retryable: bool, max_retries: int) -> Any:
        """Execute with timeout"""
        if retryable:
            # Both timeout and retry
            for attempt in range(max_retries):
                try:
                    return await asyncio.wait_for(self.execute(), timeout=timeout)
                except asyncio.TimeoutError:
                    if attempt == max_retries - 1:
                        raise TimeoutError(
                            f"Module {self.module_id} timed out after {timeout}s "
                            f"(tried {max_retries} times)"
                        )
                    # Retry
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    # Retry
                    await asyncio.sleep(2 ** attempt)
        else:
            # Only timeout
            try:
                return await asyncio.wait_for(self.execute(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Module {self.module_id} timed out after {timeout}s"
                )

    async def _execute_with_retry(self, max_retries: int) -> Any:
        """Execute with retry (no timeout)"""
        last_exception = None

        for attempt in range(max_retries):
            try:
                return await self.execute()
            except Exception as e:
                last_exception = e
                if attempt == max_retries - 1:
                    raise Exception(
                        f"Module {self.module_id} failed after {max_retries} attempts: {e}"
                    ) from e
                # Exponential backoff: 1s, 2s, 4s, 8s...
                await asyncio.sleep(2 ** attempt)

        # Should not reach here, but just in case
        raise last_exception

    def get_metadata(self) -> Dict[str, Any]:
        """Get module metadata"""
        return {
            "id": self.module_id,
            "name": self.module_name,
            "description": self.module_description,
            "required_permission": self.required_permission
        }
