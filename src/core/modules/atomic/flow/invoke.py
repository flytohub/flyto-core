"""
Invoke Workflow Module - Execute external workflows as subflows

Workflow Spec v1.1:
- Invokes external workflow by file path or inline YAML
- Supports timeout and input/output mapping
- Isolated execution with context isolation
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import NodeType, EdgeType, DataType


logger = logging.getLogger(__name__)


@register_module(
    module_id='flow.invoke',
    version='1.0.0',
    category='flow',
    tags=['flow', 'invoke', 'workflow', 'subflow', 'execute'],
    label='Invoke Workflow',
    label_key='modules.flow.invoke.label',
    description='Execute an external workflow file',
    description_key='modules.flow.invoke.description',
    icon='Play',
    color='#8B5CF6',

    # Type definitions for connection validation
    input_types=['control', 'any'],
    output_types=['control', 'any'],

    can_receive_from=['data.*', 'api.*', 'http.*', 'string.*', 'array.*', 'object.*', 'math.*', 'file.*', 'database.*', 'ai.*', 'flow.*', 'element.*'],
    can_connect_to=['*'],
    node_type=NodeType.SUBFLOW,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.invoke.ports.input',
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
            'label_key': 'modules.flow.invoke.ports.success',
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
            key='workflow_source',
            required=True,
            label='Workflow Source',
            description='File path to workflow YAML or inline YAML content'
        ),
        presets.DATA_OBJECT(
            key='workflow_params',
            label='Workflow Parameters',
            description='Parameters to pass to the invoked workflow'
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
            'description_key': 'modules.flow.invoke.output.__event__.description'
        },
        'result': {
            'type': 'any',
            'description': 'Workflow execution result',
            'description_key': 'modules.flow.invoke.output.result.description'
        },
        'workflow_id': {
            'type': 'string',
            'description': 'Invoked workflow ID',
            'description_key': 'modules.flow.invoke.output.workflow_id.description'
        },
        'execution_time_ms': {
            'type': 'number',
            'description': 'Execution time in milliseconds',
            'description_key': 'modules.flow.invoke.output.execution_time_ms.description'
        }
    },

    examples=[
        {
            'name': 'Invoke workflow file',
            'description': 'Execute a workflow from file path',
            'params': {
                'workflow_source': 'workflows/validate_order.yaml',
                'workflow_params': {'order_id': '${input.order_id}'},
                'timeout_seconds': 60
            }
        },
        {
            'name': 'Invoke with output mapping',
            'description': 'Execute workflow and map outputs',
            'params': {
                'workflow_source': 'workflows/process_data.yaml',
                'workflow_params': {'data': '${input.data}'},
                'output_mapping': {'processed': 'result.data'}
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=300000,
)
class InvokeWorkflow(BaseModule):
    """
    Invoke Workflow Module (Spec v1.1)

    Executes an external workflow file with isolated context.
    Supports timeout, input parameters, and output mapping.
    """

    module_name = "Invoke Workflow"
    module_description = "Execute an external workflow file"

    def validate_params(self) -> None:
        if 'workflow_source' not in self.params:
            raise ValueError("Missing required parameter: workflow_source")

        self.workflow_source = self.params['workflow_source']
        self.workflow_params = self.params.get('workflow_params', {})
        self.timeout_seconds = self.params.get('timeout_seconds', 300)
        self.output_mapping = self.params.get('output_mapping', {})

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        if self.timeout_seconds > 3600:
            raise ValueError("timeout_seconds cannot exceed 3600 (1 hour)")

    async def execute(self) -> Dict[str, Any]:
        """
        Execute the invoked workflow.

        Returns:
            Dict with __event__ (success/error) for engine routing
        """
        import time
        start_time = time.time()

        try:
            # Load workflow definition
            workflow_def = await self._load_workflow()

            # Resolve input parameters
            resolved_params = self._resolve_params()

            # Execute workflow with timeout
            result = await self._execute_workflow(workflow_def, resolved_params)

            execution_time_ms = (time.time() - start_time) * 1000

            # Map outputs
            mapped_result = self._map_outputs(result)

            return {
                '__event__': 'success',
                'outputs': {
                    'success': {
                        'result': mapped_result,
                        'workflow_id': workflow_def.get('id', 'unknown'),
                        'execution_time_ms': execution_time_ms
                    }
                },
                'result': mapped_result,
                'workflow_id': workflow_def.get('id', 'unknown'),
                'execution_time_ms': execution_time_ms
            }

        except asyncio.TimeoutError:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {
                        'message': f'Workflow execution timed out after {self.timeout_seconds}s',
                        'workflow_source': self.workflow_source
                    }
                },
                '__error__': {
                    'code': 'INVOKE_TIMEOUT',
                    'message': f'Workflow execution timed out after {self.timeout_seconds}s'
                }
            }

        except FileNotFoundError as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {
                        'message': f'Workflow file not found: {self.workflow_source}',
                        'workflow_source': self.workflow_source
                    }
                },
                '__error__': {
                    'code': 'WORKFLOW_NOT_FOUND',
                    'message': str(e)
                }
            }

        except Exception as e:
            logger.exception(f"Error invoking workflow: {self.workflow_source}")
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {
                        'message': str(e),
                        'workflow_source': self.workflow_source
                    }
                },
                '__error__': {
                    'code': 'INVOKE_ERROR',
                    'message': str(e)
                }
            }

    async def _load_workflow(self) -> Dict[str, Any]:
        """Load workflow from file path or parse inline YAML."""
        source = self.workflow_source.strip()

        # Check if source is a file path
        if source.endswith('.yaml') or source.endswith('.yml'):
            path = Path(source)

            # Security: Prevent path traversal
            try:
                path = path.resolve()
            except Exception:
                raise ValueError(f"Invalid workflow path: {source}")

            if not path.exists():
                raise FileNotFoundError(f"Workflow file not found: {source}")

            if not path.is_file():
                raise ValueError(f"Workflow path is not a file: {source}")

            content = path.read_text(encoding='utf-8')
            workflow_def = yaml.safe_load(content)

        else:
            # Try to parse as inline YAML
            try:
                workflow_def = yaml.safe_load(source)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid workflow YAML: {e}")

        if not isinstance(workflow_def, dict):
            raise ValueError("Workflow definition must be a YAML object")

        if 'steps' not in workflow_def:
            raise ValueError("Workflow must contain 'steps' key")

        return workflow_def

    def _resolve_params(self) -> Dict[str, Any]:
        """Resolve workflow parameters from context."""
        resolved = {}

        for key, value in self.workflow_params.items():
            resolved[key] = self._resolve_value(value)

        # Also include input data if no explicit params
        if not resolved:
            input_data = self.context.get('input')
            if input_data:
                resolved['input'] = input_data

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

    async def _execute_workflow(
        self,
        workflow_def: Dict[str, Any],
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the workflow with the given parameters."""
        # Import WorkflowEngine here to avoid circular imports
        try:
            from ....engine.workflow import WorkflowEngine
        except ImportError:
            from core.engine.workflow import WorkflowEngine

        engine = WorkflowEngine(
            workflow=workflow_def,
            params=params
        )

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                engine.execute(),
                timeout=self.timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            engine.cancel()
            raise

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
