"""
Fallback Module - Provide fallback value when operation fails

Provides a fallback mechanism for operations that may fail.
When the primary operation fails, returns a configured fallback
value or executes a fallback operation.

Use cases:
- Default values when API calls fail
- Cached data when live data unavailable
- Graceful degradation patterns

This is a "tool" module - it provides fallback infrastructure
without containing decision-making intelligence.
"""
from typing import Any, Dict, Optional
from datetime import datetime

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='error.fallback',
    version='1.0.0',
    category='error',
    tags=['error', 'fallback', 'default', 'resilience'],
    label='Fallback',
    label_key='modules.error.fallback.label',
    description='Provide fallback value when operation fails',
    description_key='modules.error.fallback.description',
    icon='Shield',
    color='#10B981',

    # Type definitions for connection validation
    input_types=['any'],
    output_types=['any'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    node_type=NodeType.STANDARD,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.error.fallback.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        },
        {
            'id': 'error_input',
            'label': 'Error Input',
            'label_key': 'modules.error.fallback.ports.error_input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 10,
            'required': False,
            'color': '#EF4444',
            'is_error_port': True
        }
    ],

    output_ports=[
        {
            'id': 'output',
            'label': 'Output',
            'label_key': 'modules.error.fallback.ports.output',
            'event': 'output',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'used_fallback',
            'label': 'Used Fallback',
            'label_key': 'modules.error.fallback.ports.used_fallback',
            'event': 'used_fallback',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'operation',
            type='object',
            label='Primary Operation',
            label_key='modules.error.fallback.params.operation.label',
            description='The primary operation to attempt',
            description_key='modules.error.fallback.params.operation.description',
            required=False,
        ),
        field(
            'fallback_value',
            type='any',
            label='Fallback Value',
            label_key='modules.error.fallback.params.fallback_value.label',
            description='Static value to return on failure',
            description_key='modules.error.fallback.params.fallback_value.description',
            required=False,
        ),
        field(
            'fallback_operation',
            type='object',
            label='Fallback Operation',
            label_key='modules.error.fallback.params.fallback_operation.label',
            description='Alternative operation to execute on failure',
            description_key='modules.error.fallback.params.fallback_operation.description',
            required=False,
        ),
        field(
            'fallback_on',
            type='array',
            label='Fallback On Error Codes',
            label_key='modules.error.fallback.params.fallback_on.label',
            description='Error codes that trigger fallback (empty = all errors)',
            description_key='modules.error.fallback.params.fallback_on.description',
            default=[],
        ),
        field(
            'include_error_info',
            type='boolean',
            label='Include Error Info',
            label_key='modules.error.fallback.params.include_error_info.label',
            description='Include original error information in output',
            description_key='modules.error.fallback.params.include_error_info.description',
            default=True,
        ),
        field(
            'log_fallback',
            type='boolean',
            label='Log Fallback Usage',
            label_key='modules.error.fallback.params.log_fallback.label',
            description='Log when fallback is used',
            description_key='modules.error.fallback.params.log_fallback.description',
            default=True,
        ),
    ),

    output_schema={
        'result': {
            'type': 'any',
            'description': 'Result from primary operation or fallback',
            'description_key': 'modules.error.fallback.output.result.description'
        },
        'used_fallback': {
            'type': 'boolean',
            'description': 'Whether fallback was used',
            'description_key': 'modules.error.fallback.output.used_fallback.description'
        },
        'source': {
            'type': 'string',
            'description': 'Source of result (primary/fallback_value/fallback_operation)',
            'description_key': 'modules.error.fallback.output.source.description'
        },
        'original_error': {
            'type': 'object',
            'description': 'Original error if fallback was used',
            'description_key': 'modules.error.fallback.output.original_error.description'
        }
    },

    examples=[
        {
            'name': 'Static fallback value',
            'description': 'Return empty array if API fails',
            'params': {
                'operation': {
                    'module': 'http.get',
                    'params': {'url': 'https://api.example.com/items'}
                },
                'fallback_value': []
            }
        },
        {
            'name': 'Fallback to cache',
            'description': 'Fall back to cached data on API failure',
            'params': {
                'operation': {
                    'module': 'http.get',
                    'params': {'url': 'https://api.example.com/config'}
                },
                'fallback_operation': {
                    'module': 'cache.get',
                    'params': {'key': 'config_cache'}
                }
            }
        },
        {
            'name': 'Selective fallback',
            'description': 'Only fallback on specific errors',
            'params': {
                'operation': {
                    'module': 'api.call',
                    'params': {'endpoint': '/data'}
                },
                'fallback_value': {'status': 'unavailable'},
                'fallback_on': ['NETWORK_ERROR', 'TIMEOUT_ERROR']
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=60000,
)
class FallbackModule(BaseModule):
    """
    Fallback module.

    Provides fallback mechanism for failing operations:
    - Static fallback value
    - Alternative fallback operation
    - Selective fallback based on error codes

    When used with error ports, it catches errors from upstream
    nodes and provides graceful degradation.
    """

    module_name = "Fallback"
    module_description = "Provide fallback when operation fails"

    def validate_params(self) -> None:
        self.operation = self.params.get('operation')
        self.fallback_value = self.params.get('fallback_value')
        self.fallback_operation = self.params.get('fallback_operation')
        self.fallback_on = self.params.get('fallback_on', [])
        self.include_error_info = self.params.get('include_error_info', True)
        self.log_fallback = self.params.get('log_fallback', True)

        # Must have at least one fallback method
        if self.fallback_value is None and self.fallback_operation is None:
            raise ValueError(
                "Either 'fallback_value' or 'fallback_operation' must be provided"
            )

    def _should_fallback(self, error_code: str) -> bool:
        """Determine if we should use fallback based on error code."""
        if not self.fallback_on:
            return True
        return error_code in self.fallback_on

    async def execute(self) -> Dict[str, Any]:
        """
        Execute with fallback handling.

        If receiving an error input, applies fallback logic.
        Otherwise, wraps the primary operation with fallback.
        """
        try:
            # Check if we received an error from upstream
            incoming_error = self.context.get('__incoming_error__')
            upstream_output = self.context.get('__upstream_output__', {})
            error_obj = incoming_error or upstream_output.get('__error__')

            # If we have an error, apply fallback
            if error_obj:
                error_code = error_obj.get('code', 'UNKNOWN')

                if not self._should_fallback(error_code):
                    # Don't fallback, propagate error
                    return {
                        '__event__': 'output',
                        '__error__': error_obj,
                        'outputs': {
                            'output': None
                        },
                        'result': None,
                        'used_fallback': False,
                        'source': 'error_propagated',
                        'original_error': error_obj if self.include_error_info else None
                    }

                # Use fallback
                return self._apply_fallback(error_obj)

            # No error - if we have a primary operation, set up execution plan
            if self.operation:
                return {
                    '__event__': 'output',
                    '__fallback_execution__': {
                        'operation': self.operation,
                        'fallback_value': self.fallback_value,
                        'fallback_operation': self.fallback_operation,
                        'fallback_on': self.fallback_on,
                    },
                    'outputs': {
                        'output': {
                            'operation': self.operation,
                            'fallback_configured': True
                        }
                    },
                    'result': None,
                    'used_fallback': False,
                    'source': 'pending'
                }

            # No operation, no error - just pass through input
            input_data = self.context.get('input')
            return {
                '__event__': 'output',
                'outputs': {
                    'output': {
                        'result': input_data,
                        'used_fallback': False,
                        'source': 'passthrough'
                    }
                },
                'result': input_data,
                'used_fallback': False,
                'source': 'passthrough'
            }

        except Exception as e:
            # Even fallback module can fail - return error
            return {
                '__event__': 'output',
                '__error__': {
                    'code': 'FALLBACK_ERROR',
                    'message': str(e)
                },
                'outputs': {
                    'output': {
                        'error': str(e)
                    }
                },
                'result': None,
                'used_fallback': False,
                'source': 'error'
            }

    def _apply_fallback(self, original_error: Dict[str, Any]) -> Dict[str, Any]:
        """Apply fallback and return result."""

        # Prefer static fallback value over operation
        if self.fallback_value is not None:
            result = {
                '__event__': 'used_fallback',
                'outputs': {
                    'output': {
                        'result': self.fallback_value,
                        'used_fallback': True,
                        'source': 'fallback_value'
                    },
                    'used_fallback': {
                        'original_error': original_error if self.include_error_info else None
                    }
                },
                'result': self.fallback_value,
                'used_fallback': True,
                'source': 'fallback_value'
            }

            if self.include_error_info:
                result['original_error'] = original_error

            return result

        # Use fallback operation
        if self.fallback_operation:
            return {
                '__event__': 'used_fallback',
                '__execute_fallback__': self.fallback_operation,
                'outputs': {
                    'output': {
                        'fallback_operation': self.fallback_operation,
                        'used_fallback': True,
                        'source': 'fallback_operation'
                    },
                    'used_fallback': {
                        'original_error': original_error if self.include_error_info else None
                    }
                },
                'result': None,
                'used_fallback': True,
                'source': 'fallback_operation',
                'original_error': original_error if self.include_error_info else None
            }

        # Should not reach here due to validation
        return {
            '__event__': 'output',
            'outputs': {
                'output': {'error': 'No fallback configured'}
            },
            'result': None,
            'used_fallback': False,
            'source': 'error'
        }
