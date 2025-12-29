"""
Switch Module - Multi-way branching for workflows

Workflow Spec v1.1:
- Uses dynamic output ports based on cases
- Returns __event__ for engine routing
- Stable port IDs via stable_key_field
"""
from typing import Any, Dict, List
import uuid
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.switch',
    version='2.0.0',  # Major version bump for spec v1.1
    category='flow',
    tags=['flow', 'switch', 'case', 'multi-branch', 'control'],
    label='Switch',
    label_key='modules.flow.switch.label',
    description='Multi-way branching based on value matching',
    description_key='modules.flow.switch.description',
    icon='GitMerge',
    color='#9C27B0',

    # Workflow Spec v1.1
    node_type=NodeType.SWITCH,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.switch.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],

    # Static output ports (dynamic ports added based on cases)
    output_ports=[
        {
            'id': 'default',
            'label': 'Default',
            'label_key': 'modules.flow.switch.ports.default',
            'event': 'default',
            'color': '#6B7280',
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

    # Dynamic ports: generated from cases param
    dynamic_ports={
        'output': {
            'from_param': 'cases',
            'stable_key_field': 'id',       # Use case.id for stable port binding
            'id_field': 'value',            # Use case.value for slug
            'label_field': 'label',         # Use case.label for display
            'event_prefix': 'case:',        # Event = case:{value}
            'include_default': False        # Default is in static output_ports
        }
    },

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'expression': {
            'type': 'string',
            'label': 'Expression',
            'label_key': 'modules.flow.switch.params.expression.label',
            'description': 'Value to match against cases (supports variable reference)',
            'description_key': 'modules.flow.switch.params.expression.description',
            'required': True
        },
        'cases': {
            'type': 'array',
            'label': 'Cases',
            'label_key': 'modules.flow.switch.params.cases.label',
            'description': 'List of case definitions',
            'description_key': 'modules.flow.switch.params.cases.description',
            'required': True,
            'items': {
                'type': 'object',
                'properties': {
                    'id': {
                        'type': 'string',
                        'description': 'Stable unique ID (auto-generated if not provided)',
                        'auto_generate': True  # UI will auto-generate UUID
                    },
                    'value': {
                        'type': 'string',
                        'description': 'Value to match',
                        'required': True
                    },
                    'label': {
                        'type': 'string',
                        'description': 'Display label for this case'
                    }
                    # NOTE: 'step' removed in v2.0
                    # Flow is now determined by edges connected to output ports
                }
            }
        },
        # Legacy param (deprecated)
        'value': {
            'type': 'string',
            'deprecated': True,
            'alias': 'expression',
            'description': 'Deprecated: use "expression" instead'
        },
        'default': {
            'type': 'string',
            'deprecated': True,
            'description': 'Deprecated: use default port instead'
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (case:value or default)'},
        'outputs': {
            'type': 'object',
            'description': 'Output values by port'
        },
        'matched_case': {'type': 'string', 'description': 'The case that matched'},
        'value': {'type': 'any', 'description': 'The resolved value that was matched'}
    },

    examples=[
        {
            'name': 'Route by status',
            'description': 'Route to different paths based on API response status',
            'params': {
                'expression': '${api_response.status}',
                'cases': [
                    {'id': 'case-1', 'value': 'success', 'label': 'Success'},
                    {'id': 'case-2', 'value': 'pending', 'label': 'Pending'},
                    {'id': 'case-3', 'value': 'error', 'label': 'Error'}
                ]
            },
            'note': 'Connect each case port to the appropriate handler node'
        },
        {
            'name': 'Route by content type',
            'description': 'Route based on input file type',
            'params': {
                'expression': '${input.type}',
                'cases': [
                    {'id': 'img', 'value': 'image', 'label': 'Image'},
                    {'id': 'vid', 'value': 'video', 'label': 'Video'},
                    {'id': 'txt', 'value': 'text', 'label': 'Text'}
                ]
            },
            'note': 'Connect default port for unsupported types'
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class SwitchModule(BaseModule):
    """
    Multi-way switch branching module (Spec v1.1)

    Matches a value against multiple cases and emits the matching event.
    The workflow engine routes to the next node based on the event
    and connected edges.

    Changes from v1.x:
    - Removed 'step' from cases (use output ports instead)
    - Returns __event__ for engine routing
    - Cases have stable 'id' field for edge binding
    - 'value' param renamed to 'expression'
    """

    module_name = "Switch"
    module_description = "Multi-way branching based on value matching"
    required_permission = "flow.control"

    def validate_params(self):
        # Support legacy 'value' param
        self.expression = self.params.get('expression') or self.params.get('value')
        if not self.expression:
            raise ValueError("Missing required parameter: expression")

        if 'cases' not in self.params:
            raise ValueError("Missing required parameter: cases")

        self.cases = self.params['cases']

        if not isinstance(self.cases, list):
            raise ValueError("Parameter 'cases' must be a list")
        if len(self.cases) == 0:
            raise ValueError("Parameter 'cases' must have at least one case")

        # Ensure each case has required fields and generate stable IDs if missing
        for i, case in enumerate(self.cases):
            if 'value' not in case and 'match' not in case:
                raise ValueError(f"Case {i} must have 'value' field")

            # Support legacy 'match' field
            if 'match' in case and 'value' not in case:
                case['value'] = case['match']

            # Auto-generate stable ID if not provided
            if 'id' not in case:
                case['id'] = str(uuid.uuid4())[:8]

            # Auto-generate label if not provided
            if 'label' not in case:
                case['label'] = case['value']

        # Legacy support
        self.default_step = self.params.get('default')

    async def execute(self) -> Dict[str, Any]:
        """
        Match value against cases and return event for routing.

        Returns:
            Dict with __event__ (case:value or default) for engine routing
        """
        try:
            resolved_value = self._resolve_value(self.expression)
            matched_case = None
            event = 'default'

            # Find matching case
            for case in self.cases:
                case_value = str(case['value']).strip()
                if str(resolved_value).strip() == case_value:
                    matched_case = case
                    event = f"case:{case_value}"
                    break

            # Build outputs for each port
            outputs = {}
            for case in self.cases:
                port_id = f"case_{case.get('id', case['value'])}"
                if case == matched_case:
                    outputs[port_id] = {
                        'matched': True,
                        'value': resolved_value,
                        'case': case
                    }
                else:
                    outputs[port_id] = None

            outputs['default'] = None if matched_case else {
                'matched': False,
                'value': resolved_value
            }

            response = {
                '__event__': event,
                'outputs': outputs,
                'matched_case': matched_case['value'] if matched_case else None,
                'matched_id': matched_case['id'] if matched_case else None,
                'value': resolved_value
            }

            # Legacy support: include next_step if 'step' provided in matched case
            if matched_case and 'step' in matched_case:
                response['next_step'] = matched_case['step']
            elif self.default_step and not matched_case:
                response['next_step'] = self.default_step

            return response

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e), 'expression': self.expression}
                },
                '__error__': {
                    'code': 'SWITCH_ERROR',
                    'message': str(e)
                }
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
