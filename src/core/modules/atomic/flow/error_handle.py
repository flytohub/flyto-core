"""
Error Handle Module - Catches and handles errors from upstream nodes

Provides a dedicated error handling node that can:
- Catch errors from connected nodes
- Extract error details (message, code, traceback)
- Allow workflow to continue after error handling
- Support retry logic or alternative flows

Workflow Spec v1.1:
- Uses output ports for continue/escalate flow
- Returns __event__ for engine routing
- Error data passed through for downstream processing
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, Field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.error_handle',
    version='1.0.0',
    category='flow',
    tags=['flow', 'error', 'catch', 'handle', 'exception', 'control'],
    label='Error Handler',
    label_key='modules.flow.error_handle.label',
    description='Catches and handles errors from upstream nodes',
    description_key='modules.flow.error_handle.description',
    icon='ShieldAlert',
    color='#EF4444',  # Red for error handling

    # Type definitions for connection validation
    input_types=['control'],
    output_types=['control'],

    # Connection rules - can receive from any node that might error
    can_receive_from=['*'],
    can_connect_to=['*'],

    # Use STANDARD node type with error-specific styling
    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'error',
            'label': 'Error Input',
            'label_key': 'modules.flow.error_handle.ports.error',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 10,  # Can catch from multiple nodes
            'required': True,
            'color': '#EF4444',
            'is_error_port': True  # Special marker for error connections
        }
    ],

    output_ports=[
        {
            'id': 'handled',
            'label': 'Handled',
            'label_key': 'modules.flow.error_handle.ports.handled',
            'event': 'handled',
            'color': '#10B981',  # Green - error was handled
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'escalate',
            'label': 'Escalate',
            'label_key': 'modules.flow.error_handle.ports.escalate',
            'event': 'escalate',
            'color': '#F59E0B',  # Orange - pass to higher handler
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        Field(
            'action',
            type='string',
            label='Action',
            label_key='modules.flow.error_handle.params.action.label',
            description='What to do with the error',
            description_key='modules.flow.error_handle.params.action.description',
            default='log_and_continue',
            options=[
                {'value': 'log_and_continue', 'label': 'Log and Continue (record error, proceed)'},
                {'value': 'transform', 'label': 'Transform (convert to different format)'},
                {'value': 'escalate', 'label': 'Escalate (pass to parent handler)'},
                {'value': 'suppress', 'label': 'Suppress (ignore error silently)'},
            ],
            required=True
        ),
        Field(
            'include_traceback',
            type='boolean',
            label='Include Traceback',
            label_key='modules.flow.error_handle.params.include_traceback.label',
            description='Include full stack trace in output',
            description_key='modules.flow.error_handle.params.include_traceback.description',
            default=True,
            required=False
        ),
        Field(
            'error_code_mapping',
            type='object',
            label='Error Code Mapping',
            label_key='modules.flow.error_handle.params.error_code_mapping.label',
            description='Map error codes to custom actions',
            description_key='modules.flow.error_handle.params.error_code_mapping.description',
            default={},
            required=False
        ),
        Field(
            'fallback_value',
            type='any',
            label='Fallback Value',
            label_key='modules.flow.error_handle.params.fallback_value.label',
            description='Value to use when error is suppressed',
            description_key='modules.flow.error_handle.params.fallback_value.description',
            default=None,
            required=False
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (handled/escalate)',
            'description_key': 'modules.flow.error_handle.output.__event__.description'
        },
        'outputs': {
            'type': 'object',
            'description': 'Output values by port',
            'description_key': 'modules.flow.error_handle.output.outputs.description'
        },
        'error_info': {
            'type': 'object',
            'description': 'Extracted error information',
            'description_key': 'modules.flow.error_handle.output.error_info.description',
            'properties': {
                'message': {'type': 'string'},
                'code': {'type': 'string'},
                'source_node': {'type': 'string'},
                'traceback': {'type': 'string'},
                'timestamp': {'type': 'string'},
                'original_error': {'type': 'object'}
            }
        },
        'action_taken': {
            'type': 'string',
            'description': 'What action was taken',
            'description_key': 'modules.flow.error_handle.output.action_taken.description'
        }
    },

    examples=[
        {
            'name': 'Log and continue',
            'description': 'Catch errors, log them, and continue workflow',
            'params': {
                'action': 'log_and_continue',
                'include_traceback': True
            },
            'note': 'Connect error ports from nodes to this handler\'s error input'
        },
        {
            'name': 'Provide fallback',
            'description': 'Suppress error and provide a default value',
            'params': {
                'action': 'suppress',
                'fallback_value': {'status': 'skipped', 'reason': 'upstream_error'}
            }
        },
        {
            'name': 'Transform and continue',
            'description': 'Transform error into a handled result',
            'params': {
                'action': 'transform',
                'error_code_mapping': {
                    'TIMEOUT': {'retry': True, 'delay': 5000},
                    'NOT_FOUND': {'skip': True}
                }
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
class ErrorHandleModule(BaseModule):
    """
    Error Handler module (Spec v1.1)

    Catches errors from upstream nodes and provides structured
    error handling with multiple action options:
    - log_and_continue: Log error details and continue workflow
    - transform: Transform error based on error code mapping
    - escalate: Pass error to higher-level handler
    - suppress: Suppress error and use fallback value
    """

    module_name = "Error Handler"
    module_description = "Catches and handles errors from upstream nodes"

    def validate_params(self) -> None:
        self.action = self.params.get('action', 'log_and_continue')
        self.include_traceback = self.params.get('include_traceback', True)
        self.error_code_mapping = self.params.get('error_code_mapping', {})
        self.fallback_value = self.params.get('fallback_value', None)

        valid_actions = ['log_and_continue', 'transform', 'escalate', 'suppress']
        if self.action not in valid_actions:
            raise ValueError(f"Invalid action: {self.action}. Must be one of {valid_actions}")

    async def execute(self) -> Dict[str, Any]:
        """
        Handle incoming error and return appropriate event.

        The error data comes from the upstream node that failed.
        This handler extracts error info and decides on action.
        """
        try:
            # Extract error information from context/input
            error_info = self._extract_error_info()

            # Determine action based on error code mapping or default action
            action_to_take = self._determine_action(error_info)

            # Execute action
            if action_to_take == 'escalate':
                return self._escalate_error(error_info)
            elif action_to_take == 'suppress':
                return self._suppress_error(error_info)
            else:
                return self._handle_error(error_info, action_to_take)

        except Exception as e:
            # Even the error handler can fail - escalate
            return {
                '__event__': 'escalate',
                'outputs': {
                    'escalate': {
                        'message': f'Error handler failed: {str(e)}',
                        'handler_error': True
                    }
                },
                '__error__': {
                    'code': 'HANDLER_ERROR',
                    'message': str(e)
                }
            }

    def _extract_error_info(self) -> Dict[str, Any]:
        """
        Extract error information from incoming data.

        Error can come from:
        - __error__ field in upstream output
        - Direct error object passed through error port
        - Context error information
        """
        from datetime import datetime

        # Check for error in context (passed through error port)
        incoming_error = self.context.get('__incoming_error__', {})
        upstream_output = self.context.get('__upstream_output__', {})

        # Extract from __error__ field if present
        error_obj = incoming_error or upstream_output.get('__error__', {})

        error_info = {
            'message': error_obj.get('message', 'Unknown error'),
            'code': error_obj.get('code', 'UNKNOWN'),
            'source_node': error_obj.get('source_node', self.context.get('__source_node__', 'unknown')),
            'timestamp': datetime.utcnow().isoformat(),
            'original_error': error_obj
        }

        # Include traceback if requested
        if self.include_traceback:
            error_info['traceback'] = error_obj.get('traceback', error_obj.get('stack', ''))

        return error_info

    def _determine_action(self, error_info: Dict[str, Any]) -> str:
        """
        Determine which action to take based on error code mapping.
        """
        error_code = error_info.get('code', 'UNKNOWN')

        # Check error code mapping
        if error_code in self.error_code_mapping:
            mapping = self.error_code_mapping[error_code]
            if isinstance(mapping, dict):
                if mapping.get('escalate'):
                    return 'escalate'
                if mapping.get('skip') or mapping.get('suppress'):
                    return 'suppress'
            return 'transform'

        return self.action

    def _handle_error(self, error_info: Dict[str, Any], action: str) -> Dict[str, Any]:
        """
        Handle error with logging and continue.
        """
        # Build handled output
        handled_output = {
            'error_info': error_info,
            'action_taken': action,
            'handled': True
        }

        # If transform action, apply mapping
        if action == 'transform':
            error_code = error_info.get('code', 'UNKNOWN')
            if error_code in self.error_code_mapping:
                handled_output['transform_config'] = self.error_code_mapping[error_code]

        return {
            '__event__': 'handled',
            'outputs': {
                'handled': handled_output
            },
            'error_info': error_info,
            'action_taken': action
        }

    def _escalate_error(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Escalate error to higher-level handler.
        """
        return {
            '__event__': 'escalate',
            'outputs': {
                'escalate': {
                    'error_info': error_info,
                    'action_taken': 'escalate',
                    'escalated': True
                }
            },
            'error_info': error_info,
            'action_taken': 'escalate'
        }

    def _suppress_error(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Suppress error and return fallback value.
        """
        return {
            '__event__': 'handled',
            'outputs': {
                'handled': {
                    'suppressed': True,
                    'fallback_value': self.fallback_value,
                    'original_error': error_info,
                    'action_taken': 'suppress'
                }
            },
            'error_info': error_info,
            'action_taken': 'suppress',
            'data': self.fallback_value  # For downstream consumption
        }
