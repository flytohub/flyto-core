"""
Composite Module Executor

Handles execution of composite modules with proper context management.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from ....constants import DEFAULT_TIMEOUT_SECONDS
from .registry import CompositeRegistry


logger = logging.getLogger(__name__)


class CompositeExecutor:
    """
    Executor for Composite Modules

    Handles the execution of composite modules with proper
    context management, error handling, and result aggregation.
    """

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        """
        Initialize executor

        Args:
            context: Shared execution context
        """
        self.context = context or {}

    async def execute(
        self,
        module_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a composite module

        Args:
            module_id: Composite module identifier
            params: Input parameters

        Returns:
            Execution result
        """
        if not CompositeRegistry.has(module_id):
            raise ValueError(f"Composite module not found: {module_id}")

        module_class = CompositeRegistry.get(module_id)
        metadata = CompositeRegistry.get_metadata(module_id) or {}

        timeout = metadata.get('timeout', DEFAULT_TIMEOUT_SECONDS)

        try:
            module_instance = module_class(params, self.context)

            if timeout:
                result = await asyncio.wait_for(
                    module_instance.execute(),
                    timeout=timeout
                )
            else:
                result = await module_instance.execute()

            return {
                'status': 'success',
                'module_id': module_id,
                'result': result
            }

        except asyncio.TimeoutError:
            logger.error(f"Composite '{module_id}' timed out after {timeout}s")
            return {
                'status': 'timeout',
                'module_id': module_id,
                'error': f"Execution timed out after {timeout} seconds"
            }

        except Exception as e:
            logger.error(f"Composite '{module_id}' failed: {e}")
            return {
                'status': 'error',
                'module_id': module_id,
                'error': str(e)
            }

    async def execute_batch(
        self,
        executions: List[Dict[str, Any]],
        parallel: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple composite modules

        Args:
            executions: List of {'module_id': str, 'params': dict}
            parallel: Whether to execute in parallel

        Returns:
            List of execution results
        """
        if parallel:
            tasks = [
                self.execute(ex['module_id'], ex.get('params', {}))
                for ex in executions
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)

        results = []
        for execution in executions:
            result = await self.execute(
                execution['module_id'],
                execution.get('params', {})
            )
            results.append(result)

        return results
