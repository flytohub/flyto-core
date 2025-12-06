"""
Branch Module - Conditional branching for workflows

Evaluates a condition and returns the next step ID based on true/false result.
The workflow engine handles the actual jump logic.
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='flow.branch',
    version='1.0.0',
    category='flow',
    tags=['flow', 'branch', 'condition', 'if', 'control'],
    label='Branch',
    label_key='modules.flow.branch.label',
    description='Conditional branching based on expression evaluation',
    description_key='modules.flow.branch.description',
    icon='GitBranch',
    color='#E91E63',

    input_types=['any'],
    output_types=['branch_result'],

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
        },
        'on_true': {
            'type': 'string',
            'label': 'On True',
            'label_key': 'modules.flow.branch.params.on_true.label',
            'description': 'Step ID to jump to when condition is true',
            'description_key': 'modules.flow.branch.params.on_true.description',
            'required': True
        },
        'on_false': {
            'type': 'string',
            'label': 'On False',
            'label_key': 'modules.flow.branch.params.on_false.label',
            'description': 'Step ID to jump to when condition is false',
            'description_key': 'modules.flow.branch.params.on_false.description',
            'required': True
        }
    },
    output_schema={
        'result': {'type': 'boolean', 'description': 'Condition evaluation result'},
        'next_step': {'type': 'string', 'description': 'ID of the next step to execute'},
        'condition': {'type': 'string', 'description': 'Original condition expression'},
        'resolved_condition': {'type': 'string', 'description': 'Condition after variable resolution'}
    },
    examples=[
        {
            'name': 'Check if results exist',
            'params': {
                'condition': '${search_step.count} > 0',
                'on_true': 'process_results',
                'on_false': 'no_results_handler'
            }
        },
        {
            'name': 'Check status',
            'params': {
                'condition': '${api_call.status} == success',
                'on_true': 'continue_processing',
                'on_false': 'error_handler'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BranchModule(BaseModule):
    """
    Conditional branching module

    Evaluates a condition and determines which step to execute next.
    The workflow engine reads the next_step from the output and jumps accordingly.
    """

    module_name = "Branch"
    module_description = "Conditional branching based on expression"
    required_permission = "flow.control"

    def validate_params(self):
        if 'condition' not in self.params:
            raise ValueError("Missing required parameter: condition")
        if 'on_true' not in self.params:
            raise ValueError("Missing required parameter: on_true")
        if 'on_false' not in self.params:
            raise ValueError("Missing required parameter: on_false")

        self.condition = self.params['condition']
        self.on_true = self.params['on_true']
        self.on_false = self.params['on_false']

    async def execute(self) -> Dict[str, Any]:
        """
        Evaluate condition and return branch decision
        """
        resolved_condition = self._resolve_variables(self.condition)
        result = self._evaluate_condition(resolved_condition)
        next_step = self.on_true if result else self.on_false

        return {
            'result': result,
            'next_step': next_step,
            'condition': self.condition,
            'resolved_condition': resolved_condition
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
