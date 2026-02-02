"""
Error Workflow Trigger Module - Entry point for error workflows

Workflow Spec v1.2:
- Special trigger type for error workflows
- Receives error context from failed workflow execution
- Provides detailed error information for handling
"""
from typing import Any, Dict
from datetime import datetime
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, Field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.error_workflow_trigger',
    version='1.0.0',
    category='flow',
    tags=['flow', 'trigger', 'error', 'workflow', 'control'],
    label='Error Workflow Trigger',
    label_key='modules.flow.error_workflow_trigger.label',
    description='Entry point for error workflows - triggered when another workflow fails',
    description_key='modules.flow.error_workflow_trigger.description',
    icon='AlertTriangle',
    color='#EF4444',

    # Connection rules
    input_types=[],  # No input - this is an entry point
    output_types=['object'],
    can_receive_from=[],
    can_connect_to=['*'],
    node_type=NodeType.TRIGGER,

    # No input ports - this is an entry point
    input_ports=[],

    output_ports=[
        {
            'id': 'triggered',
            'label': 'Error Received',
            'label_key': 'modules.flow.error_workflow_trigger.ports.triggered',
            'event': 'triggered',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        Field(
            'description',
            type='string',
            label='Description',
            label_key='common.params.description.label',
            description='Description of this error workflow',
            description_key='common.params.description.description',
            default='',
            required=False
        ),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (triggered)',
            'description_key': 'modules.flow.error_workflow_trigger.output.__event__.description'
        },
        'error_context': {
            'type': 'object',
            'description': 'Complete error context from failed workflow',
            'description_key': 'modules.flow.error_workflow_trigger.output.error_context.description',
            'properties': {
                'source_workflow_id': {'type': 'string'},
                'source_workflow_name': {'type': 'string'},
                'source_execution_id': {'type': 'string'},
                'failed_step_id': {'type': 'string'},
                'failed_step_module': {'type': 'string'},
                'error_message': {'type': 'string'},
                'error_code': {'type': 'string'},
                'error_traceback': {'type': 'string'},
                'failed_at': {'type': 'string'},
                'user_id': {'type': 'string'},
                'input_params': {'type': 'object'},
                'node_outputs': {'type': 'object'}
            }
        },
        'triggered_at': {
            'type': 'string',
            'description': 'ISO timestamp when error workflow was triggered',
            'description_key': 'modules.flow.error_workflow_trigger.output.triggered_at.description'
        }
    },

    examples=[
        {
            'name': 'Error notification workflow',
            'description': 'Trigger workflow to send notifications when errors occur',
            'params': {
                'description': 'Send Slack notification on workflow failure'
            }
        },
        {
            'name': 'Error logging workflow',
            'description': 'Log errors to external system',
            'params': {
                'description': 'Log all workflow errors to monitoring system'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class ErrorWorkflowTriggerModule(BaseModule):
    """
    Error Workflow Trigger Module (Spec v1.2)

    Special trigger that serves as the entry point for error workflows.
    Receives error context from a failed workflow execution including:
    - Source workflow information
    - Failed step details
    - Error message and traceback
    - Execution context (user, params, outputs)
    """

    module_name = "Error Workflow Trigger"
    module_description = "Entry point for error workflows"

    def validate_params(self) -> None:
        self.description = self.params.get('description', '')

    async def execute(self) -> Dict[str, Any]:
        """
        Process error context and make it available to downstream nodes.

        The error context is injected by ExecutionManager when triggering
        the error workflow after a failure.
        """
        triggered_at = datetime.utcnow().isoformat()

        # Get error context from execution context (injected by ExecutionManager)
        error_context = self.context.get('error_context', {})

        # Ensure required fields have defaults
        error_context.setdefault('source_workflow_id', 'unknown')
        error_context.setdefault('source_workflow_name', 'Unknown Workflow')
        error_context.setdefault('source_execution_id', 'unknown')
        error_context.setdefault('failed_step_id', 'unknown')
        error_context.setdefault('failed_step_module', 'unknown')
        error_context.setdefault('error_message', 'Unknown error')
        error_context.setdefault('error_code', 'UNKNOWN')
        error_context.setdefault('error_traceback', '')
        error_context.setdefault('failed_at', triggered_at)
        error_context.setdefault('user_id', '')
        error_context.setdefault('input_params', {})
        error_context.setdefault('node_outputs', {})

        return {
            '__event__': 'triggered',
            'outputs': {
                'triggered': {
                    'error_context': error_context,
                    'triggered_at': triggered_at
                }
            },
            'error_context': error_context,
            'triggered_at': triggered_at,
            # Convenience fields for downstream nodes
            'workflow_id': error_context.get('source_workflow_id'),
            'workflow_name': error_context.get('source_workflow_name'),
            'execution_id': error_context.get('source_execution_id'),
            'error_message': error_context.get('error_message'),
            'failed_step': error_context.get('failed_step_id'),
        }
