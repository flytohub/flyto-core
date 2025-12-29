"""
Branch Module - Conditional branching for workflows

Workflow Spec v1.1:
- Uses output ports (true/false/error) instead of text params
- Returns __event__ for engine routing
- Edges determine flow, not params
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.branch',
    version='2.0.0',  # Major version bump for spec v1.1
    category='flow',
    tags=['flow', 'branch', 'condition', 'if', 'control'],
    label='Branch',
    label_key='modules.flow.branch.label',
    description='Conditional branching based on expression evaluation',
    description_key='modules.flow.branch.description',
    icon='GitBranch',
    color='#E91E63',

    # Workflow Spec v1.1
    node_type=NodeType.BRANCH,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.branch.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    output_ports=[
        {
            'id': 'true',
            'label': 'True',
            'label_key': 'modules.flow.branch.ports.true',
            'event': 'true',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'false',
            'label': 'False',
            'label_key': 'modules.flow.branch.ports.false',
            'event': 'false',
            'color': '#F59E0B',
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

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'condition': {
            'type': 'string',
            'label': 'Condition',
            'label_key': 'modules.flow.branch.params.condition.label',
            'description': 'Expression to evaluate (supports ==, !=, >, <, >=, <=, contains)',
            'description_key': 'modules.flow.branch.params.condition.description',
            'required': True,
            'examples': [
                '${step1.count} > 0',
                '${step1.status} == success',
                '${step1.data} contains error'
            ]
        }
        # NOTE: on_true/on_false removed in v2.0
        # Flow is now determined by edges connected to output ports
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (true/false/error)'},
        'outputs': {
            'type': 'object',
            'description': 'Output values by port',
            'properties': {
                'true': {'type': 'object'},
                'false': {'type': 'object'}
            }
        },
        'result': {'type': 'boolean', 'description': 'Condition evaluation result'},
        'condition': {'type': 'string', 'description': 'Original condition expression'},
        'resolved_condition': {'type': 'string', 'description': 'Condition after variable resolution'}
    },

    examples=[
        {
            'name': 'Check if results exist',
            'description': 'Branch based on whether count is greater than 0',
            'params': {
                'condition': '${search_step.count} > 0'
            },
            'note': 'Connect true port to process_results, false port to no_results_handler'
        },
        {
            'name': 'Check status',
            'description': 'Branch based on API response status',
            'params': {
                'condition': '${api_call.status} == success'
            },
            'note': 'Connect true port to continue_processing, false port to error_handler'
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BranchModule(BaseModule):
    """
    Conditional branching module (Spec v1.1)

    Evaluates a condition and emits an event (true/false/error).
    The workflow engine routes to the next node based on the event
    and connected edges.

    Changes from v1.x:
    - Removed on_true/on_false params (use output ports instead)
    - Returns __event__ for engine routing
    - Returns outputs{} for per-port values
    """

    module_name = "Branch"
    module_description = "Conditional branching based on expression"
    required_permission = "flow.control"

    def validate_params(self):
        if 'condition' not in self.params:
            raise ValueError("Missing required parameter: condition")

        self.condition = self.params['condition']

        # Legacy support: check for deprecated on_true/on_false
        if 'on_true' in self.params or 'on_false' in self.params:
            import warnings
            warnings.warn(
                "on_true/on_false params are deprecated in v2.0. "
                "Use output ports and edges instead.",
                DeprecationWarning
            )

    async def execute(self) -> Dict[str, Any]:
        """
        Evaluate condition and return event for routing.

        Returns:
            Dict with __event__ (true/false/error) for engine routing
        """
        try:
            resolved_condition = self._resolve_variables(self.condition)
            result = self._evaluate_condition(resolved_condition)

            # Determine event
            event = 'true' if result else 'false'

            # Build response with Spec v1.1 format
            response = {
                # Event for routing
                '__event__': event,

                # Per-port outputs
                'outputs': {
                    'true': {'result': result, 'condition': self.condition} if result else None,
                    'false': {'result': result, 'condition': self.condition} if not result else None,
                },

                # Legacy fields for backwards compatibility
                'result': result,
                'condition': self.condition,
                'resolved_condition': resolved_condition,
            }

            # Legacy support: include next_step if on_true/on_false provided
            if 'on_true' in self.params and 'on_false' in self.params:
                response['next_step'] = self.params['on_true'] if result else self.params['on_false']

            return response

        except Exception as e:
            # Return error event
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e), 'condition': self.condition}
                },
                '__error__': {
                    'code': 'CONDITION_ERROR',
                    'message': str(e)
                }
            }

    def _resolve_variables(self, expression: str) -> str:
        """
        Resolve ${...} variables in the expression
        """
        import re
        pattern = r'\$\{([^}]+)\}'

        def replacer(match):
            var_path = match.group(1)
            value = self._get_variable_value(var_path)
            return str(value) if value is not None else match.group(0)

        return re.sub(pattern, replacer, expression)

    def _get_variable_value(self, var_path: str) -> Any:
        """
        Get value from context using dot notation path
        """
        parts = var_path.split('.')
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

    def _evaluate_condition(self, expression: str) -> bool:
        """
        Evaluate a condition expression

        Supports: ==, !=, >, <, >=, <=, contains, !contains
        """
        operators = [
            ('==', lambda a, b: str(a).strip() == str(b).strip()),
            ('!=', lambda a, b: str(a).strip() != str(b).strip()),
            ('>=', lambda a, b: self._to_number(a) >= self._to_number(b)),
            ('<=', lambda a, b: self._to_number(a) <= self._to_number(b)),
            ('>', lambda a, b: self._to_number(a) > self._to_number(b)),
            ('<', lambda a, b: self._to_number(a) < self._to_number(b)),
            ('!contains', lambda a, b: str(b).strip() not in str(a)),
            ('contains', lambda a, b: str(b).strip() in str(a)),
        ]

        for op_str, op_func in operators:
            if op_str in expression:
                parts = expression.split(op_str, 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    try:
                        return op_func(left, right)
                    except (ValueError, TypeError):
                        return False

        return self._to_bool(expression)

    def _to_number(self, value: Any) -> float:
        """
        Convert value to number
        """
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return 0.0
        return 0.0

    def _to_bool(self, value: Any) -> bool:
        """
        Convert value to boolean
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower().strip() in ('true', 'yes', '1')
        return bool(value)
