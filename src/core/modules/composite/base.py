"""
Composite Module Base Class and Registry

Level 3 Modules - High-level workflow templates combining multiple atomic modules.
Designed for normal users, similar to n8n nodes (3-10 atomic steps).

Example:
    @register_composite(
        module_id='workflow.google.search_and_notify',
        label='Google Search and Notify',
        steps=[
            {'module': 'browser.goto', 'params': {'url': 'https://google.com'}},
            {'module': 'browser.fill', 'params': {'selector': 'input', 'value': '${params.query}'}},
            {'module': 'notification.slack.send', 'params': {'message': '${steps.search.results}'}}
        ]
    )
    class GoogleSearchNotify(CompositeModule):
        pass
"""
import asyncio
import logging
from abc import ABC
from typing import Any, Dict, List, Optional, Type

from ..base import BaseModule
from ...constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    ErrorMessages,
)

logger = logging.getLogger(__name__)


class CompositeRegistry:
    """
    Registry for Composite Modules (Level 3)

    Manages high-level workflow templates that combine multiple atomic modules.
    """

    _instance = None
    _composites: Dict[str, Type['CompositeModule']] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        module_id: str,
        module_class: Type['CompositeModule'],
        metadata: Dict[str, Any]
    ):
        """Register a composite module"""
        cls._composites[module_id] = module_class
        cls._metadata[module_id] = metadata
        logger.debug(f"Composite module registered: {module_id}")

    @classmethod
    def get(cls, module_id: str) -> Type['CompositeModule']:
        """Get composite module class by ID"""
        if module_id not in cls._composites:
            raise ValueError(f"Composite module not found: {module_id}")
        return cls._composites[module_id]

    @classmethod
    def has(cls, module_id: str) -> bool:
        """Check if composite module exists"""
        return module_id in cls._composites

    @classmethod
    def list_all(cls) -> Dict[str, Type['CompositeModule']]:
        """List all registered composite modules"""
        return cls._composites.copy()

    @classmethod
    def get_metadata(cls, module_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a composite module"""
        return cls._metadata.get(module_id)

    @classmethod
    def get_all_metadata(
        cls,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Get all composite metadata with optional filtering"""
        result = {}

        for module_id, metadata in cls._metadata.items():
            if category and metadata.get('category') != category:
                continue

            if tags:
                module_tags = metadata.get('tags', [])
                if not any(tag in module_tags for tag in tags):
                    continue

            result[module_id] = metadata

        return result

    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """Get composite registry statistics"""
        all_composites = cls._metadata

        categories = {}
        for module_id, metadata in all_composites.items():
            cat = metadata.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_composites": len(all_composites),
            "categories": categories,
            "total_categories": len(categories)
        }


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
        from ..registry import ModuleRegistry

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
        import os
        import re

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


def register_composite(
    module_id: str,
    version: str = "1.0.0",
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tags: Optional[List[str]] = None,

    # Display
    label: Optional[str] = None,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
    description_key: Optional[str] = None,

    # Visual
    icon: Optional[str] = None,
    color: Optional[str] = None,

    # Connection types
    input_types: Optional[List[str]] = None,
    output_types: Optional[List[str]] = None,

    # Steps definition
    steps: Optional[List[Dict[str, Any]]] = None,

    # Schema
    params_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,

    # Execution settings
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retryable: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,

    # Documentation
    examples: Optional[List[Dict[str, Any]]] = None,
    author: Optional[str] = None,
    license: str = "MIT"
):
    """
    Decorator to register a Composite Module (Level 3)

    Example:
        @register_composite(
            module_id='workflow.google.search_notify',
            label='Google Search and Notify',
            description='Search Google and send results to Slack',
            steps=[
                {'id': 'launch', 'module': 'browser.launch'},
                {'id': 'search', 'module': 'browser.goto', 'params': {'url': '...'}},
                {'id': 'notify', 'module': 'notification.slack.send', 'params': {...}}
            ],
            params_schema={
                'query': {'type': 'string', 'required': True, 'label': 'Search Query'},
                'webhook_url': {'type': 'string', 'required': True, 'label': 'Slack Webhook'}
            }
        )
        class GoogleSearchNotify(CompositeModule):
            pass

    Args:
        module_id: Unique identifier (e.g., "workflow.google.search_notify")
        version: Semantic version
        category: Primary category (e.g., "workflow", "automation")
        subcategory: Subcategory (e.g., "google", "github")
        tags: List of tags for filtering
        label: Display name
        label_key: i18n key for label
        description: Module description
        description_key: i18n key for description
        icon: Lucide icon name
        color: Hex color code
        input_types: List of accepted input types
        output_types: List of produced output types
        steps: List of atomic steps to execute
        params_schema: Parameter definitions
        output_schema: Output structure definition
        timeout: Execution timeout in seconds
        retryable: Whether module can be retried
        max_retries: Maximum retry attempts
        examples: Usage examples
        author: Module author
        license: License identifier
    """
    def decorator(cls):
        # Ensure class inherits from CompositeModule
        if not issubclass(cls, CompositeModule):
            raise TypeError(f"{cls.__name__} must inherit from CompositeModule")

        cls.module_id = module_id
        cls.steps = steps or []

        # Build metadata
        metadata = {
            "module_id": module_id,
            "version": version,
            "level": 3,  # Level 3 = Composite Module
            "category": category or module_id.split('.')[0],
            "subcategory": subcategory,
            "tags": tags or [],
            "label": label or module_id,
            "label_key": label_key,
            "description": description or "",
            "description_key": description_key,
            "icon": icon,
            "color": color,
            "input_types": input_types or [],
            "output_types": output_types or [],
            "steps": steps or [],
            "params_schema": params_schema or {},
            "output_schema": output_schema or {},
            "timeout": timeout,
            "retryable": retryable,
            "max_retries": max_retries,
            "examples": examples or [],
            "author": author,
            "license": license
        }

        CompositeRegistry.register(module_id, cls, metadata)
        return cls

    return decorator


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
