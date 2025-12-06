"""
Switch Module - Multi-way branching for workflows

Evaluates a value and matches against multiple cases to determine next step.
"""
from typing import Any, Dict, List
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='flow.switch',
    version='1.0.0',
    category='flow',
    tags=['flow', 'switch', 'case', 'multi-branch', 'control'],
    label='Switch',
    label_key='modules.flow.switch.label',
    description='Multi-way branching based on value matching',
    description_key='modules.flow.switch.description',
    icon='GitMerge',
    color='#9C27B0',

    input_types=['any'],
    output_types=['branch_result'],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'value': {
            'type': 'string',
            'label': 'Value',
            'label_key': 'modules.flow.switch.params.value.label',
            'description': 'Value to match against cases (supports variable reference)',
            'description_key': 'modules.flow.switch.params.value.description',
            'required': True
        },
        'cases': {
            'type': 'array',
            'label': 'Cases',
            'label_key': 'modules.flow.switch.params.cases.label',
            'description': 'List of case definitions with match value and target step',
            'description_key': 'modules.flow.switch.params.cases.description',
            'required': True,
            'items': {
                'type': 'object',
                'properties': {
                    'match': {
                        'type': 'string',
                        'description': 'Value to match'
                    },
                    'step': {
                        'type': 'string',
                        'description': 'Step ID to jump to'
                    }
                }
            }
        },
        'default': {
            'type': 'string',
            'label': 'Default',
            'label_key': 'modules.flow.switch.params.default.label',
            'description': 'Step ID when no case matches',
            'description_key': 'modules.flow.switch.params.default.description',
            'required': False
        }
    },
    output_schema={
        'matched_case': {'type': 'string', 'description': 'The case that matched'},
        'next_step': {'type': 'string', 'description': 'ID of the next step to execute'},
        'value': {'type': 'any', 'description': 'The resolved value that was matched'}
    },
    examples=[
        {
            'name': 'Route by status',
            'params': {
                'value': '${api_response.status}',
                'cases': [
                    {'match': 'success', 'step': 'process_data'},
                    {'match': 'pending', 'step': 'wait_and_retry'},
                    {'match': 'error', 'step': 'handle_error'}
                ],
                'default': 'unknown_status_handler'
            }
        },
        {
            'name': 'Route by type',
            'params': {
                'value': '${input.type}',
                'cases': [
                    {'match': 'image', 'step': 'process_image'},
                    {'match': 'video', 'step': 'process_video'},
                    {'match': 'text', 'step': 'process_text'}
                ],
                'default': 'unsupported_type'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class SwitchModule(BaseModule):
    """
    Multi-way switch branching module

    Matches a value against multiple cases and determines which step to execute.
    """

    module_name = "Switch"
    module_description = "Multi-way branching based on value matching"
    required_permission = "flow.control"

    def validate_params(self):
        if 'value' not in self.params:
            raise ValueError("Missing required parameter: value")
        if 'cases' not in self.params:
            raise ValueError("Missing required parameter: cases")

        self.value_expr = self.params['value']
        self.cases = self.params['cases']
        self.default_step = self.params.get('default')

        if not isinstance(self.cases, list):
            raise ValueError("Parameter 'cases' must be a list")
        if len(self.cases) == 0:
            raise ValueError("Parameter 'cases' must have at least one case")

        for case in self.cases:
            if 'match' not in case or 'step' not in case:
                raise ValueError("Each case must have 'match' and 'step' fields")

    async def execute(self) -> Dict[str, Any]:
        """
        Match value against cases and return branch decision
        """
        resolved_value = self._resolve_value(self.value_expr)
        matched_case = None
        next_step = self.default_step

        for case in self.cases:
            case_match = str(case['match']).strip()
            if str(resolved_value).strip() == case_match:
                matched_case = case_match
                next_step = case['step']
                break

        if next_step is None:
            raise ValueError(
                f"No matching case for value '{resolved_value}' and no default step defined"
            )

        return {
            'matched_case': matched_case,
            'next_step': next_step,
            'value': resolved_value
        }

    def _resolve_value(self, expression: str) -> Any:
        """
        Resolve variable reference or return literal value
        """
        if not isinstance(expression, str):
            return expression

        expression = expression.strip()

        if expression.startswith('${') and expression.endswith('}'):
            var_path = expression[2:-1]
            return self._get_variable_value(var_path)

        return expression

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
