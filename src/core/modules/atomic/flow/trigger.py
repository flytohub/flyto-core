"""
Trigger Module - Workflow entry point

Workflow Spec v1.1:
- Trigger node as workflow entry point
- Types: manual, webhook, schedule, event
- No input ports (entry point)
"""
from typing import Any, Dict, Optional
from datetime import datetime
from ...base import BaseModule
from ...registry import register_module
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.trigger',
    version='1.0.0',
    category='flow',
    tags=['flow', 'trigger', 'entry', 'webhook', 'schedule', 'control'],
    label='Trigger',
    label_key='modules.flow.trigger.label',
    description='Workflow entry point - manual, webhook, schedule, or event',
    description_key='modules.flow.trigger.description',
    icon='Zap',
    color='#F59E0B',

    # Workflow Spec v1.1
    node_type=NodeType.TRIGGER,

    # No input ports - this is an entry point
    input_ports=[],

    output_ports=[
        {
            'id': 'triggered',
            'label': 'Triggered',
            'label_key': 'modules.flow.trigger.ports.triggered',
            'event': 'triggered',
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

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'trigger_type': {
            'type': 'string',
            'label': 'Trigger Type',
            'label_key': 'modules.flow.trigger.params.trigger_type.label',
            'description': 'Type of trigger',
            'description_key': 'modules.flow.trigger.params.trigger_type.description',
            'enum': ['manual', 'webhook', 'schedule', 'event'],
            'default': 'manual',
            'required': False
        },
        'webhook_path': {
            'type': 'string',
            'label': 'Webhook Path',
            'label_key': 'modules.flow.trigger.params.webhook_path.label',
            'description': 'URL path for webhook trigger',
            'description_key': 'modules.flow.trigger.params.webhook_path.description',
            'required': False,
            'visible_when': {'trigger_type': 'webhook'}
        },
        'schedule': {
            'type': 'string',
            'label': 'Schedule',
            'label_key': 'modules.flow.trigger.params.schedule.label',
            'description': 'Cron expression for scheduled trigger',
            'description_key': 'modules.flow.trigger.params.schedule.description',
            'required': False,
            'visible_when': {'trigger_type': 'schedule'},
            'examples': ['0 * * * *', '0 9 * * 1-5', '*/5 * * * *']
        },
        'event_name': {
            'type': 'string',
            'label': 'Event Name',
            'label_key': 'modules.flow.trigger.params.event_name.label',
            'description': 'Event name to listen for',
            'description_key': 'modules.flow.trigger.params.event_name.description',
            'required': False,
            'visible_when': {'trigger_type': 'event'}
        },
        'description': {
            'type': 'string',
            'label': 'Description',
            'label_key': 'modules.flow.trigger.params.description.label',
            'description': 'Description of this trigger',
            'description_key': 'modules.flow.trigger.params.description.description',
            'required': False
        }
    },

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (triggered/error)'},
        'trigger_data': {'type': 'object', 'description': 'Data from trigger source'},
        'trigger_type': {'type': 'string', 'description': 'Type of trigger'},
        'triggered_at': {'type': 'string', 'description': 'ISO timestamp'}
    },

    examples=[
        {
            'name': 'Manual trigger',
            'description': 'Manual workflow start',
            'params': {
                'trigger_type': 'manual'
            }
        },
        {
            'name': 'Webhook trigger',
            'description': 'Trigger via HTTP webhook',
            'params': {
                'trigger_type': 'webhook',
                'webhook_path': '/api/webhooks/order-created'
            }
        },
        {
            'name': 'Scheduled trigger',
            'description': 'Run every hour',
            'params': {
                'trigger_type': 'schedule',
                'schedule': '0 * * * *'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class TriggerModule(BaseModule):
    """
    Trigger Module (Spec v1.1)

    Workflow entry point that can be triggered by:
    - manual: User-initiated execution
    - webhook: HTTP webhook call
    - schedule: Cron-based schedule
    - event: Internal or external event
    """

    module_name = "Trigger"
    module_description = "Workflow entry point"
    required_permission = "flow.control"

    def validate_params(self):
        self.trigger_type = self.params.get('trigger_type', 'manual')
        self.webhook_path = self.params.get('webhook_path')
        self.schedule = self.params.get('schedule')
        self.event_name = self.params.get('event_name')
        self.description = self.params.get('description')

        if self.trigger_type not in ('manual', 'webhook', 'schedule', 'event'):
            raise ValueError(f"Invalid trigger_type: {self.trigger_type}")

        # Validate type-specific params
        if self.trigger_type == 'webhook' and not self.webhook_path:
            raise ValueError("webhook_path required for webhook trigger")
        if self.trigger_type == 'schedule' and not self.schedule:
            raise ValueError("schedule required for schedule trigger")
        if self.trigger_type == 'event' and not self.event_name:
            raise ValueError("event_name required for event trigger")

    async def execute(self) -> Dict[str, Any]:
        """
        Process trigger and emit triggered event.

        Returns:
            Dict with __event__ (triggered/error) for engine routing
        """
        try:
            # Get trigger payload from context (injected by scheduler/webhook handler)
            trigger_payload = self.context.get('trigger_payload', {})
            triggered_at = datetime.utcnow().isoformat()

            # Build trigger data
            trigger_data = {
                'trigger_type': self.trigger_type,
                'triggered_at': triggered_at,
                'payload': trigger_payload
            }

            # Add type-specific info
            if self.trigger_type == 'webhook':
                trigger_data['webhook_path'] = self.webhook_path
            elif self.trigger_type == 'schedule':
                trigger_data['schedule'] = self.schedule
            elif self.trigger_type == 'event':
                trigger_data['event_name'] = self.event_name

            return {
                '__event__': 'triggered',
                'outputs': {
                    'triggered': trigger_data
                },
                'trigger_data': trigger_data,
                'trigger_type': self.trigger_type,
                'triggered_at': triggered_at
            }

        except Exception as e:
            return {
                '__event__': 'error',
                'outputs': {
                    'error': {'message': str(e)}
                },
                '__error__': {
                    'code': 'TRIGGER_ERROR',
                    'message': str(e)
                }
            }
