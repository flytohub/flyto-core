"""
Invoke Template Module - Execute templates from user library

This module allows templates (purchased, forked, or owned) to be used
as nodes within workflows, enabling template composition and reuse.

Key Features:
- Executes template from user's library snapshot (not live version)
- Dynamic input schema from template definition
- Timeout and error handling
- Isolated execution context
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import NodeType, EdgeType, DataType


logger = logging.getLogger(__name__)


@register_module(
    module_id='template.invoke',
    version='1.0.0',
    category='template',
    tags=['template', 'invoke', 'workflow', 'subflow', 'reuse', 'library'],
    label='Invoke Template',
    label_key='modules.template.invoke.label',
    description='Execute a template from your library as a workflow step',
    description_key='modules.template.invoke.description',
    icon='Package',
    color='#8B5CF6',

    can_receive_from=['*'],
    can_connect_to=['*'],
    node_type=NodeType.SUBFLOW,
    can_be_start=True,  # Templates can start workflows

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.template.invoke.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'success',
            'label': 'Success',
            'label_key': 'modules.template.invoke.ports.success',
            'event': 'success',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'error',
            'label': 'Error',
            'label_key': 'common.ports.error',
            'event': 'error',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=True,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        presets.TEXT(
            key='template_id',
            required=True,
            label='Template ID',
            description='ID of the template to execute'
        ),
        presets.TEXT(
            key='library_id',
            required=True,
            label='Library ID',
            description='ID of the library item (purchase/fork/owned)'
        ),
        presets.NUMBER(
            key='timeout_seconds',
            default=300,
            label='Timeout (seconds)',
            description='Maximum execution time in seconds'
        ),
        presets.OUTPUT_MAPPING(),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (success/error)',
            'description_key': 'modules.template.invoke.output.__event__.description'
        },
        'result': {
            'type': 'any',
            'description': 'Template execution result',
            'description_key': 'modules.template.invoke.output.result.description'
        },
        'template_id': {
            'type': 'string',
            'description': 'Executed template ID',
            'description_key': 'modules.template.invoke.output.template_id.description'
        },
        'execution_time_ms': {
            'type': 'number',
            'description': 'Execution time in milliseconds',
            'description_key': 'modules.template.invoke.output.execution_time_ms.description'
        }
    },

    examples=[
        {
            'name': 'Invoke purchased template',
            'description': 'Execute a template from your library',
            'params': {
                'template_id': 'abc123',
                'library_id': 'purchase_xyz',
                'timeout_seconds': 60
            }
        },
        {
            'name': 'Invoke with output mapping',
            'description': 'Execute template and map specific outputs',
            'params': {
                'template_id': 'abc123',
                'library_id': 'purchase_xyz',
                'output_mapping': {'processed_data': 'result.data'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=300000,
)
class InvokeTemplate(BaseModule):
    """
    Invoke Template Module

    Executes a template from the user's library as a workflow step.
    Templates are executed from their snapshot, not the live version,
    ensuring consistent behavior even if the original is updated.
    """

    module_name = "Invoke Template"
    module_description = "Execute a template from your library"

    def validate_params(self) -> None:
        if 'template_id' not in self.params:
            raise ValueError("Missing required parameter: template_id")
        if 'library_id' not in self.params:
            raise ValueError("Missing required parameter: library_id")

        self.template_id = self.params['template_id']
        self.library_id = self.params['library_id']
        self.timeout_seconds = self.params.get('timeout_seconds', 300)
        self.output_mapping = self.params.get('output_mapping', {})

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        if self.timeout_seconds > 3600:
            raise ValueError("timeout_seconds cannot exceed 3600 (1 hour)")

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the template.

        Returns:
            Dict with __event__ (success/error) for engine routing
        """
        start_time = time.time()

        logger.debug(f"execute() called for template_id={self.template_id}, library_id={self.library_id}")
        logger.debug(f"Context keys: {list(self.context.keys()) if self.context else 'NO CONTEXT'}")

        try:
            # Load template definition from context or API
            logger.debug("Calling _load_template_definition()")
            definition = await self._load_template_definition()

            logger.debug(f"Loaded definition: {definition is not None}")
            if definition:
                steps = definition.get('steps', [])
                logger.debug(f"Definition has {len(steps)} steps")
                for i, step in enumerate(steps):
                    logger.debug(f"Step {i}: module={step.get('module')}, id={step.get('id')}")

            if not definition or not definition.get('steps'):
                logger.error("No steps found in definition!")
                return self._error_result(
                    'TEMPLATE_EMPTY',
                    'Template has no steps to execute'
                )

            # Resolve input parameters (from context + explicit params)
            resolved_params = self._resolve_params()
            logger.debug(f"Resolved params: {resolved_params}")

            # Execute template with timeout
            logger.debug("Calling _execute_template()")
            result = await self._execute_template(definition, resolved_params)
            logger.debug(f"_execute_template returned: {type(result)}")

            execution_time_ms = (time.time() - start_time) * 1000

            # Map outputs if specified
            mapped_result = self._map_outputs(result)
            logger.debug(f"Execution completed in {execution_time_ms}ms")

            return {
                '__event__': 'success',
                'outputs': {
                    'success': {
                        'result': mapped_result,
                        'template_id': self.template_id,
                        'execution_time_ms': execution_time_ms
                    }
                },
                'result': mapped_result,
                'template_id': self.template_id,
                'execution_time_ms': execution_time_ms
            }

        except asyncio.TimeoutError:
            return self._error_result(
                'TEMPLATE_TIMEOUT',
                f'Template execution timed out after {self.timeout_seconds}s'
            )

        except Exception as e:
            logger.exception(f"Error invoking template: {self.template_id}")
            return self._error_result('TEMPLATE_ERROR', str(e))

    async def _load_template_definition(self) -> Optional[Dict[str, Any]]:
        """
        Load template definition.

        In cloud environment, this fetches from the API.
        Definition may also be pre-loaded in context by the engine.
        """
        logger.debug("_load_template_definition called")
        logger.debug(f"Looking for library_id={self.library_id}, template_id={self.template_id}")

        # Check if definition is already in context (pre-loaded by engine)
        if 'template_definition' in self.context:
            logger.debug("Found 'template_definition' in context")
            return self.context['template_definition']

        # Check template_definitions dict (pre-loaded by ExecutionManager)
        template_definitions = self.context.get('template_definitions', {})
        logger.debug(f"template_definitions keys: {list(template_definitions.keys())}")

        if self.library_id in template_definitions:
            logger.debug(f"Found definition by library_id: {self.library_id}")
            return template_definitions[self.library_id]
        if self.template_id in template_definitions:
            logger.debug(f"Found definition by template_id: {self.template_id}")
            return template_definitions[self.template_id]

        # Check if steps are directly provided (for testing/local use)
        if 'template_steps' in self.context:
            logger.debug("Found 'template_steps' in context")
            return {'steps': self.context['template_steps']}

        # In production, the engine should pre-load the definition
        # This is a fallback for local/testing scenarios
        logger.warning(
            f"Template definition NOT FOUND for library_id={self.library_id}, template_id={self.template_id}. "
            "Engine should pre-load definitions for cloud execution."
        )

        return None

    def _resolve_params(self) -> Dict[str, Any]:
        """Resolve workflow parameters from context and explicit params."""
        resolved = {}

        # Get input data from context
        input_data = self.context.get('input')
        if input_data:
            if isinstance(input_data, dict):
                resolved.update(input_data)
            else:
                resolved['input'] = input_data

        # Add any explicit params (excluding internal ones)
        internal_keys = {'template_id', 'library_id', 'timeout_seconds', 'output_mapping'}
        for key, value in self.params.items():
            if key not in internal_keys:
                resolved[key] = self._resolve_value(value)

        return resolved

    def _resolve_value(self, value: Any) -> Any:
        """Resolve variable expressions in a value."""
        import re

        if not isinstance(value, str):
            return value

        pattern = r'\$\{([^}]+)\}'
        match = re.match(pattern, value)

        if not match:
            return value

        var_path = match.group(1)
        return self._get_context_value(var_path)

    def _get_context_value(self, path: str) -> Any:
        """Get value from context using dot notation."""
        parts = path.split('.')
        current = self.context

        for part in parts:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

        return current

    async def _execute_template(
        self,
        definition: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the template workflow.

        Currently uses in-process execution for all templates.
        Subprocess isolation (for non-official templates) will be enabled
        when the plugin runtime infrastructure is ready.
        """
        # TODO: Enable subprocess execution when PoolRouter is ready
        # For now, use in-process execution for all templates
        force_in_process = self.context.get('force_in_process', True)

        if force_in_process:
            return await self._execute_in_process(definition, params)

        # Determine execution path based on template vendor
        template_vendor = self.context.get('template_vendor', 'unknown')
        is_official = template_vendor in ('flyto-official', 'flyto2', 'official')
        force_subprocess = self.context.get('force_subprocess', False)

        if is_official and not force_subprocess:
            # Official templates: in-process execution (existing logic)
            return await self._execute_in_process(definition, params)
        else:
            # Non-official templates: subprocess execution with isolation
            return await self._execute_in_subprocess(definition, params)

    async def _execute_in_process(
        self,
        definition: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute template in the same process (for official templates)."""
        logger.debug("_execute_in_process called")
        logger.debug(f"params: {params}")

        # Import WorkflowEngine here to avoid circular imports
        try:
            from ....engine.workflow import WorkflowEngine
            logger.debug("Imported WorkflowEngine from ....engine.workflow")
        except ImportError:
            try:
                from core.engine.workflow import WorkflowEngine
                logger.debug("Imported WorkflowEngine from core.engine.workflow")
            except ImportError:
                # Fallback for environments without full engine
                logger.warning("WorkflowEngine not available, returning mock result")
                return {
                    'status': 'mock',
                    'template_id': self.template_id,
                    'params': params
                }

        # Build initial context from parent context
        # This shares browser, credentials, and other runtime state
        initial_context = {}
        if self.context:
            # Copy relevant context items
            for key in ['browser', 'page', 'credentials', 'execution_id', 'user_id',
                        'secrets', 'template_definitions', 'screenshots_dir']:
                if key in self.context:
                    initial_context[key] = self.context[key]
                    logger.debug(f"Copied context key: {key}")

        steps = definition.get('steps', [])
        logger.debug(f"Creating inner WorkflowEngine with {len(steps)} steps")

        engine = WorkflowEngine(
            workflow={'steps': steps},
            params=params,
            initial_context=initial_context if initial_context else None
        )

        # Execute with timeout
        try:
            logger.debug("Starting inner engine execution...")
            result = await asyncio.wait_for(
                engine.execute(),
                timeout=self.timeout_seconds
            )
            logger.debug(f"Inner engine completed with result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            return result
        except asyncio.TimeoutError:
            logger.error("Inner engine timed out!")
            engine.cancel()
            raise
        except Exception as e:
            logger.exception(f"Inner engine failed: {e}")
            raise

    async def _execute_in_subprocess(
        self,
        definition: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute template in an isolated subprocess.

        Features:
        - Secrets are proxied (plugins get refs, not raw values)
        - Usage is metered (success_only billing)
        - Multi-tenant isolation via PoolRouter
        """
        execution_id = self.context.get('execution_id', f'exec_{int(time.time())}')
        tenant_id = self.context.get('tenant_id', 'default')
        tenant_tier = self.context.get('tenant_tier', 'free')

        # Try to import runtime components (may not be available in all environments)
        try:
            from ...runtime.pool_router import get_pool_router
            from ...runtime.types import InvokeRequest, TenantContext
            from ...secrets.proxy import get_secrets_proxy
            from ...metering.tracker import get_metering_tracker
        except ImportError:
            # Runtime not available, fall back to in-process execution
            logger.warning(
                "Plugin runtime not available, falling back to in-process execution"
            )
            return await self._execute_in_process(definition, params)

        secrets_proxy = get_secrets_proxy()
        metering_tracker = get_metering_tracker()

        # 1. Create secret references (plugins get refs, not raw secrets)
        raw_secrets = self.context.get('secrets', {})
        secret_refs = {}
        if raw_secrets:
            refs = secrets_proxy.create_refs_for_context(
                secrets=raw_secrets,
                execution_id=execution_id
            )
            # Convert SecretRef objects to ref strings for context
            secret_refs = {name: ref.ref for name, ref in refs.items()}
            logger.debug(f"Created {len(secret_refs)} secret refs for execution {execution_id}")

        try:
            # 2. Build execution context with secret refs (not raw secrets)
            subprocess_context = {
                'execution_id': execution_id,
                'tenant_id': tenant_id,
                'tenant_tier': tenant_tier,
                'secret_refs': secret_refs,  # Refs only, not raw values
                'template_id': self.template_id,
                'library_id': self.library_id,
            }

            # 3. Create tenant context for pool routing
            tenant_context = TenantContext(
                tenant_id=tenant_id,
                tenant_tier=tenant_tier,
                isolation_mode='shared_pool' if tenant_tier in ('free', 'pro') else 'dedicated_pool',
                resource_limits=self.context.get('resource_limits', {})
            )

            # 4. Create invoke request
            # For template execution, we invoke a special "workflow.execute" step
            request = InvokeRequest(
                module_id='workflow',
                step_id='execute',
                input_data={
                    'definition': definition,
                    'params': params,
                },
                config={},
                context=subprocess_context,
                execution_id=execution_id,
                timeout_ms=self.timeout_seconds * 1000,
            )

            # 5. Get pool router and invoke
            pool_router = await get_pool_router()
            response = await pool_router.invoke(request, tenant_context)

            # 6. Record metering (success_only billing)
            if response.ok:
                # Get cost info from template metadata
                cost_class = self.context.get('cost_class', 'standard')
                base_points = self.context.get('base_points', 1)

                metering_tracker.record(
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                    plugin_id=f'template.{self.template_id}',
                    step_id='invoke',
                    cost_class=cost_class,
                    base_points=base_points,
                    success=True,
                    duration_ms=response.metrics.duration_ms if response.metrics else 0,
                    metadata={
                        'template_id': self.template_id,
                        'library_id': self.library_id,
                    }
                )
                logger.debug(
                    f"Metered template execution: {self.template_id} "
                    f"({base_points} points, class={cost_class})"
                )

            # 7. Convert response to result dict
            if response.ok:
                return response.data or {}
            else:
                error_msg = response.error.message if response.error else 'Unknown error'
                raise RuntimeError(f"Subprocess execution failed: {error_msg}")

        finally:
            # 8. Always revoke secret refs after execution
            if secret_refs:
                revoked = secrets_proxy.revoke_for_execution(execution_id)
                logger.debug(f"Revoked {revoked} secret refs for execution {execution_id}")

    def _map_outputs(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Map workflow outputs using output_mapping."""
        if not self.output_mapping:
            return result

        mapped = {}
        for output_key, result_path in self.output_mapping.items():
            value = self._get_nested_value(result, result_path)
            mapped[output_key] = value

        return mapped

    def _get_nested_value(self, obj: Any, path: str) -> Any:
        """Get nested value using dot notation."""
        parts = path.split('.')
        current = obj

        for part in parts:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

        return current

    def _error_result(self, code: str, message: str) -> Dict[str, Any]:
        """Create standardized error result."""
        return {
            '__event__': 'error',
            'outputs': {
                'error': {
                    'message': message,
                    'template_id': self.template_id,
                    'library_id': self.library_id
                }
            },
            '__error__': {
                'code': code,
                'message': message
            }
        }
