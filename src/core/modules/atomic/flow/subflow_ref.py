"""
Subflow Module - Reference and execute external workflows

Workflow Spec v1.1:
- Subflow node references external workflow by ID or path
- Execution modes: inline (blocking), spawn (new execution), async (fire and forget)
- Input/output mapping for variable translation
"""
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.subflow',
    version='1.0.0',
    category='flow',
    tags=['flow', 'subflow', 'workflow', 'reference', 'control'],
    label='Subflow',
    label_key='modules.flow.subflow.label',
    description='Reference and execute an external workflow',
    description_key='modules.flow.subflow.description',
    icon='Workflow',
    color='#8B5CF6',

    # Workflow Spec v1.1
    node_type=NodeType.SUBFLOW,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.subflow.ports.input',
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
            'label_key': 'modules.flow.subflow.ports.success',
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
    required_permissions=['flow.control', 'workflow.execute'],

    params_schema={
        'workflow_ref': {
            'type': 'string',
            'label': 'Workflow Reference',
            'label_key': 'modules.flow.subflow.params.workflow_ref.label',
            'description': 'External workflow ID or path',
            'description_key': 'modules.flow.subflow.params.workflow_ref.description',
            'required': True
        },
        'execution_mode': {
            'type': 'string',
            'label': 'Execution Mode',
            'label_key': 'modules.flow.subflow.params.execution_mode.label',
            'description': 'How to execute the subflow',
            'description_key': 'modules.flow.subflow.params.execution_mode.description',
            'enum': ['inline', 'spawn', 'async'],
            'default': 'inline',
            'required': False
        },
        'input_mapping': {
            'type': 'object',
            'label': 'Input Mapping',
            'label_key': 'modules.flow.subflow.params.input_mapping.label',
            'description': 'Map parent variables to subflow inputs',
            'description_key': 'modules.flow.subflow.params.input_mapping.description',
            'default': {},
            'required': False
        },
        'output_mapping': {
            'type': 'object',
            'label': 'Output Mapping',
            'label_key': 'modules.flow.subflow.params.output_mapping.label',
            'description': 'Map subflow outputs to parent variables',
            'description_key': 'modules.flow.subflow.params.output_mapping.description',
            'default': {},
            'required': False
        },
        'timeout_ms': {
            'type': 'integer',
            'label': 'Timeout (ms)',
            'label_key': 'modules.flow.subflow.params.timeout_ms.label',
            'description': 'Maximum execution time in milliseconds',
            'description_key': 'modules.flow.subflow.params.timeout_ms.description',
            'default': 300000,
            'minimum': 1000,
            'maximum': 3600000,
            'required': False
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (success/error)'},
        'result': {'type': 'any', 'description': 'Subflow execution result'},
        'execution_id': {'type': 'string', 'description': 'Subflow execution ID (for spawn/async)'},
        'workflow_ref': {'type': 'string', 'description': 'Referenced workflow'}
    },

    examples=[
        {
            'name': 'Execute inline',
            'description': 'Execute subflow and wait for result',
            'params': {
                'workflow_ref': 'workflows/validate_order',
                'execution_mode': 'inline',
                'input_mapping': {'order_data': '${input.order}'},
                'output_mapping': {'validation_result': 'result'}
            }
        },
        {
            'name': 'Spawn new execution',
            'description': 'Start subflow as new execution',
            'params': {
                'workflow_ref': 'workflows/send_notifications',
                'execution_mode': 'spawn'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class SubflowModule(BaseModule):
    """
    Subflow Module (Spec v1.1)

    References and executes an external workflow.

    Execution Modes:
    - inline: Execute synchronously, wait for result
    - spawn: Start as new execution, continue with execution ID
    - async: Fire and forget, continue immediately
    """

    module_name = "Subflow"
    module_description = "Reference and execute external workflow"
    required_permission = "flow.control"

    def validate_params(self):
        if 'workflow_ref' not in self.params:
            raise ValueError("Missing required parameter: workflow_ref")

        self.workflow_ref = self.params['workflow_ref']
        self.execution_mode = self.params.get('execution_mode', 'inline')
        self.input_mapping = self.params.get('input_mapping', {})
        self.output_mapping = self.params.get('output_mapping', {})
        self.timeout_ms = self.params.get('timeout_ms', 300000)

        if self.execution_mode not in ('inline', 'spawn', 'async'):
            raise ValueError(f"Invalid execution_mode: {self.execution_mode}")

    async def execute(self) -> Dict[str, Any]:
        """
        Execute referenced subflow.

        Returns:
            Dict with __event__ (success/error) for engine routing
        """
        try:
            # Map inputs from parent context
            subflow_inputs = self._map_inputs()

            # In a real implementation, this would:
            # 1. Load the referenced workflow
            # 2. Execute it with mapped inputs
            # 3. Map outputs back to parent context

            # For now, return placeholder result
            # The actual execution is handled by the workflow engine
            result = {
                'workflow_ref': self.workflow_ref,
                'execution_mode': self.execution_mode,
                'inputs': subflow_inputs,
                'status': 'executed'
            }

            # Generate execution ID for spawn/async modes
            execution_id = None
            if self.execution_mode in ('spawn', 'async'):
                import uuid
                execution_id = str(uuid.uuid4())
                result['execution_id'] = execution_id

            # Map outputs
            mapped_outputs = self._map_outputs(result)

            return {
                '__event__': 'success',
                'outputs': {
                    'success': {
                        'result': mapped_outputs,
                        'execution_id': execution_id,
                        'workflow_ref': self.workflow_ref
                    }
                },
                'result': mapped_outputs,
                'execution_id': execution_id,
                'workflow_ref': self.workflow_ref
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {
                        'message': str(e),
                        'workflow_ref': self.workflow_ref
                    }
                },
                '__error__': {
                    'code': 'SUBFLOW_ERROR',
                    'message': str(e)
                }
            }

    def _map_inputs(self) -> Dict[str, Any]:
        """Map parent context to subflow inputs."""
        mapped = {}

        for subflow_key, parent_expr in self.input_mapping.items():
            value = self._resolve_expression(parent_expr)
            mapped[subflow_key] = value

        # Also include direct input if no mapping specified
        if not self.input_mapping:
            mapped['input'] = self.context.get('input')

        return mapped

    def _map_outputs(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Map subflow outputs to parent context."""
        if not self.output_mapping:
            return result

        mapped = {}
        for parent_key, subflow_key in self.output_mapping.items():
            if subflow_key in result:
                mapped[parent_key] = result[subflow_key]

        return mapped

    def _resolve_expression(self, expr: str) -> Any:
        """Resolve variable expression like ${input.data}."""
        import re

        if not isinstance(expr, str):
            return expr

        pattern = r'\$\{([^}]+)\}'
        match = re.match(pattern, expr)

        if not match:
            return expr

        var_path = match.group(1)
        return self._get_value_by_path(var_path)

    def _get_value_by_path(self, path: str) -> Any:
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
