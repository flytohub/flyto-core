"""
Composite Module Base Class

Abstract base class for composite modules.
"""
import logging
import os
import re
from abc import ABC
from typing import Any, Dict, List

from .registry import CompositeRegistry


logger = logging.getLogger(__name__)


class CompositeModule(ABC):
    """
    Base class for Composite Modules (Level 3)

    Composite modules combine multiple atomic modules into a single,
    reusable workflow template. They are designed for normal users
    who want powerful automation without writing code.

    Attributes:
        module_id: Unique composite module identifier
        steps: List of atomic steps to execute
        params: Input parameters
        context: Execution context
    """

    module_id: str = ""
    steps: List[Dict[str, Any]] = []

    def __init__(self, params: Dict[str, Any], context: Dict[str, Any]):
        """
        Initialize composite module

        Args:
            params: Input parameters for the composite
            context: Execution context (shared state, browser instance, etc.)
        """
        self.params = params
        self.context = context
        self.step_results: Dict[str, Any] = {}

    async def execute(self) -> Dict[str, Any]:
        """
        Execute all steps in the composite module

        Returns:
            Dict containing results from all steps
        """
        metadata = CompositeRegistry.get_metadata(self.module_id) or {}
        steps = metadata.get('steps', self.steps)

        if not steps:
            raise ValueError(f"No steps defined for composite: {self.module_id}")

        logger.info(f"Executing composite: {self.module_id} ({len(steps)} steps)")

        for i, step_config in enumerate(steps):
            step_id = step_config.get('id', f'step_{i}')

            try:
                result = await self._execute_step(step_config, step_id)
                self.step_results[step_id] = result
                logger.debug(f"Step '{step_id}' completed")

            except Exception as e:
                on_error = step_config.get('on_error', 'fail')

                if on_error == 'continue':
                    logger.warning(f"Step '{step_id}' failed, continuing: {e}")
                    self.step_results[step_id] = {'error': str(e), 'status': 'failed'}
                else:
                    logger.error(f"Composite '{self.module_id}' failed at step '{step_id}': {e}")
                    raise

        return self._build_output(metadata)

    async def _execute_step(
        self,
        step_config: Dict[str, Any],
        step_id: str
    ) -> Any:
        """Execute a single step within the composite"""
        from ...registry import ModuleRegistry

        module_id = step_config.get('module')
        if not module_id:
            raise ValueError(f"Step '{step_id}' missing 'module' field")

        # Resolve parameters with variable substitution
        raw_params = step_config.get('params', {})
        resolved_params = self._resolve_params(raw_params)

        # Get and execute the atomic module
        module_class = ModuleRegistry.get(module_id)
        module_instance = module_class(resolved_params, self.context)

        return await module_instance.run()

    def _resolve_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve parameter variables

        Supports:
            ${params.name} - Input parameter
            ${steps.step_id.field} - Previous step result
            ${env.VAR_NAME} - Environment variable
        """

        def resolve_value(value: Any) -> Any:
            if isinstance(value, str):
                # Pattern: ${type.path}
                pattern = r'\$\{(\w+)\.([^}]+)\}'

                def replacer(match):
                    var_type = match.group(1)
                    var_path = match.group(2)

                    if var_type == 'params':
                        return str(self._get_nested(self.params, var_path, ''))
                    elif var_type == 'steps':
                        return str(self._get_nested(self.step_results, var_path, ''))
                    elif var_type == 'env':
                        return os.environ.get(var_path, '')
                    elif var_type == 'context':
                        return str(self._get_nested(self.context, var_path, ''))

                    return match.group(0)

                return re.sub(pattern, replacer, value)

            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}

            elif isinstance(value, list):
                return [resolve_value(item) for item in value]

            return value

        return resolve_value(params)

    def _get_nested(self, data: Dict[str, Any], path: str, default: Any = None) -> Any:
        """Get nested value from dict using dot notation"""
        keys = path.split('.')
        result = data

        for key in keys:
            if isinstance(result, dict) and key in result:
                result = result[key]
            else:
                return default

        return result

    def _build_output(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Build composite output based on output_schema"""
        output_schema = metadata.get('output_schema', {})

        if not output_schema:
            # Return all step results
            return {
                'status': 'success',
                'steps': self.step_results
            }

        # Resolve output schema
        return self._resolve_params(output_schema)
