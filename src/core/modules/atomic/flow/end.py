"""
End Module - Explicit workflow end node

Workflow Spec v1.1:
- End node marks explicit workflow termination
- Single input port
- No output ports (terminal)
- Optional output_mapping for workflow result
"""
from typing import Any, Dict
from datetime import datetime
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.end',
    version='1.0.0',
    category='flow',
    tags=['flow', 'end', 'finish', 'terminal', 'control'],
    label='End',
    label_key='modules.flow.end.label',
    description='Explicit workflow end node',
    description_key='modules.flow.end.description',
    icon='Square',
    color='#EF4444',

    # Workflow Spec v1.1
    node_type=NodeType.END,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.end.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    # No output ports - terminal node
    output_ports=[],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'output_mapping': {
            'type': 'object',
            'label': 'Output Mapping',
            'label_key': 'modules.flow.end.params.output_mapping.label',
            'description': 'Map internal variables to workflow output',
            'description_key': 'modules.flow.end.params.output_mapping.description',
            'default': {},
            'required': False
        },
        'success_message': {
            'type': 'string',
            'label': 'Success Message',
            'label_key': 'modules.flow.end.params.success_message.label',
            'description': 'Optional message on successful completion',
            'description_key': 'modules.flow.end.params.success_message.description',
            'required': False
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (__end__)'},
        'ended_at': {'type': 'string', 'description': 'ISO timestamp of end'},
        'workflow_result': {'type': 'object', 'description': 'Mapped workflow output'}
    },

    examples=[
        {
            'name': 'Simple end',
            'description': 'End workflow execution',
            'params': {}
        },
        {
            'name': 'End with output mapping',
            'description': 'End and export specific variables',
            'params': {
                'output_mapping': {
                    'result': '${process.output}',
                    'status': 'success'
                }
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class EndModule(BaseModule):
    """
    End Module (Spec v1.1)

    Explicit end node for workflows.
    Marks the termination of workflow execution.
    Can map internal variables to workflow output.
    """

    module_name = "End"
    module_description = "Explicit workflow end node"
    required_permission = "flow.control"

    def validate_params(self):
        self.output_mapping = self.params.get('output_mapping', {})
        self.success_message = self.params.get('success_message')

    async def execute(self) -> Dict[str, Any]:
        """
        Mark workflow end and produce final result.

        Returns:
            Dict with __event__ '__end__' for engine routing
        """
        ended_at = datetime.utcnow().isoformat()
        workflow_id = self.context.get('workflow_id')
        execution_id = self.context.get('execution_id')

        # Get input data
        input_data = self.context.get('input')

        # Build workflow result from output_mapping
        workflow_result = self._build_workflow_result(input_data)

        return {
            # Special __end__ event signals workflow termination
            '__event__': '__end__',
            'ended_at': ended_at,
            'workflow_id': workflow_id,
            'execution_id': execution_id,
            'workflow_result': workflow_result,
            'success_message': self.success_message,
            'input_data': input_data
        }

    def _build_workflow_result(self, input_data: Any) -> Dict[str, Any]:
        """Build workflow result from output_mapping."""
        if not self.output_mapping:
            # Default: use input data as result
            return {'result': input_data}

        result = {}
        for key, value_expr in self.output_mapping.items():
            if isinstance(value_expr, str) and value_expr.startswith('${'):
                # Resolve variable expression
                resolved = self._resolve_expression(value_expr)
                result[key] = resolved
            else:
                # Use literal value
                result[key] = value_expr

        return result

    def _resolve_expression(self, expr: str) -> Any:
        """Resolve variable expression like ${step.output}."""
        import re

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
