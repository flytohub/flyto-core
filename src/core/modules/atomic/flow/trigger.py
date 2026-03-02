# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Trigger Module - Workflow entry point

Workflow Spec v1.1:
- Trigger node as workflow entry point
- Types: manual, webhook, schedule, event, mcp, polling
- No input ports (entry point)
"""
from typing import Any, Dict, Optional
from datetime import datetime
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets
from ...schema.constants import FieldGroup
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.trigger',
    version='1.0.0',
    category='flow',
    tags=['flow', 'trigger', 'entry', 'webhook', 'schedule', 'mcp', 'polling', 'control', 'ssrf_protected', 'path_restricted'],
    label='Trigger',
    label_key='modules.flow.trigger.label',
    description='Workflow entry point - manual, webhook, schedule, event, mcp, or polling',
    description_key='modules.flow.trigger.description',
    icon='Zap',
    color='#F59E0B',


    # Connection rules
    input_types=[],  # No input - this is an entry point
    output_types=['object', 'string'],  # Outputs trigger_data object and strings
    can_receive_from=[],
    can_connect_to=['*'],    # Workflow Spec v1.1
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
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.TRIGGER_TYPE(default='manual'),
        field("webhook_path", type="string",
              label="Webhook Path",
              label_key="schema.field.webhook_path",
              placeholder="/api/webhooks/my-webhook",
              description="URL path for webhook trigger",
              showIf={"trigger_type": {"$in": ["webhook"]}},
              group=FieldGroup.OPTIONS),
        field("schedule", type="string",
              label="Schedule",
              label_key="schema.field.cron_schedule",
              placeholder="0 * * * *",
              description="Cron expression for scheduled trigger",
              showIf={"trigger_type": {"$in": ["schedule"]}},
              group=FieldGroup.OPTIONS),
        field("event_name", type="string",
              label="Event Name",
              label_key="schema.field.event_name",
              placeholder="user.created",
              description="Event name to listen for",
              showIf={"trigger_type": {"$in": ["event"]}},
              group=FieldGroup.OPTIONS),
        field("tool_name", type="string",
              label="Tool Name",
              label_key="schema.field.tool_name",
              placeholder="send-weekly-report",
              description="MCP tool name exposed to AI agents",
              showIf={"trigger_type": {"$in": ["mcp"]}},
              group=FieldGroup.OPTIONS),
        field("tool_description", type="string",
              label="Tool Description",
              label_key="schema.field.tool_description",
              placeholder="Send a weekly summary report to the specified email",
              description="Description shown to AI agents for this tool",
              showIf={"trigger_type": {"$in": ["mcp"]}},
              group=FieldGroup.OPTIONS),
        field("poll_url", type="string",
              label="Poll URL",
              label_key="schema.field.poll_url",
              placeholder="https://api.example.com/items",
              description="API endpoint to poll for changes",
              showIf={"trigger_type": {"$in": ["polling"]}},
              group=FieldGroup.OPTIONS),
        field("poll_interval", type="number",
              label="Poll Interval (seconds)",
              label_key="schema.field.poll_interval",
              default=300,
              description="How often to check for changes (minimum 60 seconds)",
              showIf={"trigger_type": {"$in": ["polling"]}},
              group=FieldGroup.OPTIONS),
        field("poll_method", type="select",
              label="HTTP Method",
              label_key="schema.field.poll_method",
              default="GET",
              options=[
                  {"value": "GET", "label": "GET"},
                  {"value": "POST", "label": "POST"},
              ],
              description="HTTP method for polling request",
              showIf={"trigger_type": {"$in": ["polling"]}},
              group=FieldGroup.OPTIONS),
        field("poll_headers", type="object",
              label="Headers",
              label_key="schema.field.poll_headers",
              default={},
              description="Custom headers for polling request (e.g. API keys)",
              showIf={"trigger_type": {"$in": ["polling"]}},
              group=FieldGroup.ADVANCED),
        field("poll_body", type="object",
              label="Request Body",
              label_key="schema.field.poll_body",
              default={},
              description="Request body for POST polling",
              showIf={"trigger_type": {"$in": ["polling"]}},
              group=FieldGroup.ADVANCED),
        field("dedup_key", type="string",
              label="Dedup Key",
              label_key="schema.field.dedup_key",
              placeholder="$.data[0].id",
              description="JSON path to extract a unique value for deduplication",
              showIf={"trigger_type": {"$in": ["polling"]}},
              group=FieldGroup.OPTIONS),
        field("config", type="object",
              label="Configuration",
              label_key="modules.flow.trigger.param.config.label",
              description="Custom trigger config (for composites: LINE BOT, Telegram, Slack, etc.)",
              description_key="modules.flow.trigger.param.config.description",
              group=FieldGroup.ADVANCED),
        presets.DESCRIPTION(),
    ),

    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (triggered/error)',
                'description_key': 'modules.flow.trigger.output.__event__.description'},
        'trigger_data': {'type': 'object', 'description': 'Data from trigger source',
                'description_key': 'modules.flow.trigger.output.trigger_data.description'},
        'trigger_type': {'type': 'string', 'description': 'Type of trigger',
                'description_key': 'modules.flow.trigger.output.trigger_type.description'},
        'triggered_at': {'type': 'string', 'description': 'ISO timestamp',
                'description_key': 'modules.flow.trigger.output.triggered_at.description'}
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
        },
        {
            'name': 'MCP trigger',
            'description': 'Expose workflow as AI agent tool',
            'params': {
                'trigger_type': 'mcp',
                'tool_name': 'send-report',
                'tool_description': 'Send a weekly summary report'
            }
        },
        {
            'name': 'Polling trigger',
            'description': 'Check API for new data every 5 minutes',
            'params': {
                'trigger_type': 'polling',
                'poll_url': 'https://api.example.com/items',
                'poll_interval': 300,
                'dedup_key': '$.data[0].id'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=5000,
)
class TriggerModule(BaseModule):
    """
    Trigger Module (Spec v1.1)

    Workflow entry point that can be triggered by:
    - manual: User-initiated execution
    - webhook: HTTP webhook call
    - schedule: Cron-based schedule
    - event: Internal or external event
    - mcp: AI agent MCP tool call
    - polling: Periodic API polling
    """

    module_name = "Trigger"
    module_description = "Workflow entry point"
    def validate_params(self) -> None:
        self.trigger_type = self.params.get('trigger_type', 'manual')
        self.webhook_path = self.params.get('webhook_path')
        self.schedule = self.params.get('schedule')
        self.event_name = self.params.get('event_name')
        self.tool_name = self.params.get('tool_name')
        self.tool_description = self.params.get('tool_description')
        self.poll_url = self.params.get('poll_url')
        self.poll_interval = self.params.get('poll_interval', 300)
        self.poll_method = self.params.get('poll_method', 'GET')
        self.poll_headers = self.params.get('poll_headers', {})
        self.poll_body = self.params.get('poll_body', {})
        self.dedup_key = self.params.get('dedup_key')
        self.config = self.params.get('config', {})
        self.description = self.params.get('description')

        valid_types = ('manual', 'webhook', 'schedule', 'event', 'mcp', 'polling')
        if self.trigger_type not in valid_types:
            raise ValueError(f"Invalid trigger_type: {self.trigger_type}")

        # Validate type-specific params
        if self.trigger_type == 'webhook' and not self.webhook_path:
            raise ValueError("webhook_path required for webhook trigger")
        if self.trigger_type == 'schedule' and not self.schedule:
            raise ValueError("schedule required for schedule trigger")
        if self.trigger_type == 'event' and not self.event_name:
            raise ValueError("event_name required for event trigger")
        if self.trigger_type == 'mcp' and not self.tool_name:
            raise ValueError("tool_name required for mcp trigger")
        if self.trigger_type == 'polling' and not self.poll_url:
            raise ValueError("poll_url required for polling trigger")

    async def execute(self) -> Dict[str, Any]:
        """
        Process trigger and emit triggered event.

        Returns:
            Dict with __event__ (triggered/error) for engine routing
        """
        try:
            trigger_payload = self.context.get('trigger_payload', {})
            triggered_at = datetime.utcnow().isoformat()
            trigger_data = self._build_trigger_data(trigger_payload, triggered_at)
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

    def _build_trigger_data(
        self, trigger_payload: Dict, triggered_at: str
    ) -> Dict[str, Any]:
        trigger_data = {
            'trigger_type': self.trigger_type,
            'triggered_at': triggered_at,
            'payload': trigger_payload,
        }
        if self.config:
            trigger_data['config'] = self.config
        if self.trigger_type == 'webhook':
            trigger_data['webhook_path'] = self.webhook_path
        elif self.trigger_type == 'schedule':
            trigger_data['schedule'] = self.schedule
        elif self.trigger_type == 'event':
            trigger_data['event_name'] = self.event_name
        elif self.trigger_type == 'mcp':
            trigger_data['tool_name'] = self.tool_name
        elif self.trigger_type == 'polling':
            trigger_data['poll_url'] = self.poll_url
            trigger_data['dedup_key'] = self.dedup_key
        return trigger_data
