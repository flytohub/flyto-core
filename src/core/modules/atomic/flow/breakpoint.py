"""
Breakpoint Module - Human-in-the-loop approval node

Workflow Spec v1.1:
- Pauses execution for human approval
- Supports timeout and custom input collection
- Routes to approved/rejected/timeout outputs

This is a capability n8n lacks - structured human intervention points.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='flow.breakpoint',
    version='1.0.0',
    category='flow',
    tags=['flow', 'breakpoint', 'approval', 'human', 'pause', 'control', 'hitl'],
    label='Breakpoint',
    label_key='modules.flow.breakpoint.label',
    description='Pause workflow execution for human approval or input',
    description_key='modules.flow.breakpoint.description',
    icon='Hand',
    color='#8B5CF6',


    can_receive_from=['data.*', 'api.*', 'http.*', 'string.*', 'array.*', 'object.*', 'math.*', 'file.*', 'database.*', 'ai.*', 'flow.*', 'element.*', 'start'],
    can_connect_to=['*'],    # Workflow Spec v1.1
    node_type=NodeType.BREAKPOINT,

    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.breakpoint.ports.input',
            'max_connections': 1,
            'required': True,
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    output_ports=[
        {
            'id': 'approved',
            'label': 'Approved',
            'label_key': 'modules.flow.breakpoint.ports.approved',
            'event': 'approved',
            'color': '#10B981',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'rejected',
            'label': 'Rejected',
            'label_key': 'modules.flow.breakpoint.ports.rejected',
            'event': 'rejected',
            'color': '#EF4444',
            'edge_type': EdgeType.CONTROL.value
        },
        {
            'id': 'timeout',
            'label': 'Timeout',
            'label_key': 'modules.flow.breakpoint.ports.timeout',
            'event': 'timeout',
            'color': '#F59E0B',
            'edge_type': EdgeType.CONTROL.value
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control', 'breakpoint.manage'],

    # Schema-driven params
    params_schema=compose(
        presets.APPROVAL_TITLE(default='Approval Required'),
        presets.DESCRIPTION(multiline=True),
        presets.TIMEOUT_SECONDS(default=0),
        presets.DATA_ARRAY(key='required_approvers', label='Required Approvers'),
        presets.APPROVAL_MODE(default='single'),
        presets.DATA_ARRAY(key='custom_fields', label='Custom Input Fields'),
        presets.BOOLEAN(key='include_context', label='Include Context', default=True),
        presets.TEXT(key='auto_approve_condition', label='Auto-Approve Condition'),
    ),

    output_schema={
        '__event__': {
            'type': 'string',
            'description': 'Event for routing (approved/rejected/timeout)'
        },
        'breakpoint_id': {
            'type': 'string',
            'description': 'Unique breakpoint identifier'
        },
        'status': {
            'type': 'string',
            'description': 'Final status (approved/rejected/timeout/cancelled)'
        },
        'approved_by': {
            'type': 'array',
            'description': 'List of users who approved'
        },
        'rejected_by': {
            'type': 'array',
            'description': 'List of users who rejected'
        },
        'custom_inputs': {
            'type': 'object',
            'description': 'Values collected from custom fields'
        },
        'comments': {
            'type': 'array',
            'description': 'Comments from approvers'
        },
        'resolved_at': {
            'type': 'string',
            'description': 'ISO timestamp of resolution'
        },
        'wait_duration_ms': {
            'type': 'integer',
            'description': 'Time spent waiting for approval'
        }
    },

    examples=[
        {
            'name': 'Simple approval',
            'description': 'Wait for any user to approve',
            'params': {
                'title': 'Approve data export',
                'description': 'Please review and approve the data export'
            }
        },
        {
            'name': 'Manager approval with timeout',
            'description': 'Require manager approval within 1 hour',
            'params': {
                'title': 'Manager Approval Required',
                'description': 'Large transaction requires manager approval',
                'required_approvers': ['manager@example.com'],
                'timeout_seconds': 3600
            }
        },
        {
            'name': 'Collect additional input',
            'description': 'Collect reason and amount from approver',
            'params': {
                'title': 'Adjustment Required',
                'custom_fields': [
                    {'name': 'reason', 'label': 'Reason', 'type': 'text', 'required': True},
                    {'name': 'amount', 'label': 'Amount', 'type': 'number', 'required': True}
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class BreakpointModule(BaseModule):
    """
    Breakpoint Module (Spec v1.1)

    Human-in-the-loop node that pauses workflow execution
    until a human approves, rejects, or timeout occurs.

    Features:
    - Configurable approvers and approval modes
    - Timeout support
    - Custom input field collection
    - Context visibility for approvers
    - Auto-approve conditions
    """

    module_name = "Breakpoint"
    module_description = "Pause workflow for human approval or input"
    required_permission = "flow.control"

    def validate_params(self):
        """Validate and extract parameters"""
        self.title = self.get_param('title', 'Approval Required')
        self.description = self.get_param('description', '')
        self.timeout_seconds = self.get_param('timeout_seconds', 0)
        self.required_approvers = self.get_param('required_approvers', [])
        self.approval_mode = self.get_param('approval_mode', 'single')
        self.custom_fields = self.get_param('custom_fields', [])
        self.include_context = self.get_param('include_context', True)
        self.auto_approve_condition = self.get_param('auto_approve_condition', '')

        # Validate approval mode
        valid_modes = ['single', 'all', 'majority', 'first']
        if self.approval_mode not in valid_modes:
            raise ValueError(
                f"Invalid approval_mode: {self.approval_mode}. "
                f"Must be one of: {valid_modes}"
            )

        # Validate custom fields structure
        for field in self.custom_fields:
            if 'name' not in field:
                raise ValueError("Custom field missing 'name' property")
            if 'type' not in field:
                field['type'] = 'string'

    async def execute(self) -> Dict[str, Any]:
        """
        Execute breakpoint - pause for approval.

        Returns:
            Dict with __event__ and approval result
        """
        from ....engine.breakpoint import (
            get_breakpoint_manager,
            ApprovalMode,
            BreakpointStatus,
        )

        start_time = datetime.utcnow()

        # Check auto-approve condition
        if self.auto_approve_condition:
            try:
                # Evaluate condition against context
                result = self._evaluate_condition(self.auto_approve_condition)
                if result:
                    return self._build_auto_approved_result(start_time)
            except Exception as e:
                # Log but don't fail - proceed with manual approval
                pass

        # Get breakpoint manager
        manager = get_breakpoint_manager()

        # Map approval mode
        mode_map = {
            'single': ApprovalMode.SINGLE,
            'all': ApprovalMode.ALL,
            'majority': ApprovalMode.MAJORITY,
            'first': ApprovalMode.FIRST,
        }
        approval_mode = mode_map.get(self.approval_mode, ApprovalMode.SINGLE)

        # Prepare context snapshot
        context_snapshot = {}
        if self.include_context:
            context_snapshot = self._sanitize_context(self.context)

        # Create breakpoint
        request = await manager.create_breakpoint(
            execution_id=self.context.get('execution_id', 'unknown'),
            step_id=self.context.get('step_id', 'unknown'),
            workflow_id=self.context.get('workflow_id'),
            title=self.title,
            description=self.description,
            required_approvers=self.required_approvers,
            approval_mode=approval_mode,
            timeout_seconds=self.timeout_seconds if self.timeout_seconds > 0 else None,
            context_snapshot=context_snapshot,
            custom_fields=self.custom_fields,
            metadata={
                'step_name': self.context.get('step_name'),
                'workflow_name': self.context.get('workflow_name'),
            },
        )

        # Wait for resolution
        result = await manager.wait_for_resolution(
            request.breakpoint_id,
            check_timeout=True,
        )

        end_time = datetime.utcnow()
        wait_duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Build output based on status
        return self._build_result(result, wait_duration_ms)

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate auto-approve condition"""
        # Simple expression evaluation against context
        # For security, only allow basic comparisons
        try:
            # Create safe evaluation context
            eval_context = {
                'context': self.context,
                'params': self.params,
                'True': True,
                'False': False,
                'None': None,
            }

            # Add safe builtins
            safe_builtins = {
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'abs': abs,
                'min': min,
                'max': max,
            }

            result = eval(condition, {"__builtins__": safe_builtins}, eval_context)
            return bool(result)
        except Exception:
            return False

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from context snapshot"""
        sensitive_keys = {
            'password', 'secret', 'token', 'key', 'credential',
            'api_key', 'apikey', 'auth', 'authorization'
        }

        def sanitize(obj: Any, depth: int = 0) -> Any:
            if depth > 10:  # Prevent infinite recursion
                return "[MAX_DEPTH]"

            if isinstance(obj, dict):
                result = {}
                for k, v in obj.items():
                    lower_key = k.lower()
                    if any(s in lower_key for s in sensitive_keys):
                        result[k] = "[REDACTED]"
                    else:
                        result[k] = sanitize(v, depth + 1)
                return result
            elif isinstance(obj, list):
                return [sanitize(item, depth + 1) for item in obj[:100]]  # Limit list size
            elif isinstance(obj, (str, int, float, bool, type(None))):
                if isinstance(obj, str) and len(obj) > 1000:
                    return obj[:1000] + "...[TRUNCATED]"
                return obj
            else:
                return str(obj)[:200]

        return sanitize(context)

    def _build_auto_approved_result(self, start_time: datetime) -> Dict[str, Any]:
        """Build result for auto-approved breakpoint"""
        end_time = datetime.utcnow()
        wait_duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return {
            '__event__': 'approved',
            'outputs': {
                'approved': {
                    'breakpoint_id': 'auto_approved',
                    'status': 'approved',
                    'auto_approved': True,
                    'approved_by': ['system'],
                    'rejected_by': [],
                    'custom_inputs': {},
                    'comments': ['Auto-approved by condition'],
                    'resolved_at': end_time.isoformat(),
                    'wait_duration_ms': wait_duration_ms,
                }
            },
            'breakpoint_id': 'auto_approved',
            'status': 'approved',
            'auto_approved': True,
            'approved_by': ['system'],
            'rejected_by': [],
            'custom_inputs': {},
            'comments': ['Auto-approved by condition'],
            'resolved_at': end_time.isoformat(),
            'wait_duration_ms': wait_duration_ms,
        }

    def _build_result(self, result, wait_duration_ms: int) -> Dict[str, Any]:
        """Build output from breakpoint result"""
        from ....engine.breakpoint import BreakpointStatus

        # Determine event based on status
        status_to_event = {
            BreakpointStatus.APPROVED: 'approved',
            BreakpointStatus.REJECTED: 'rejected',
            BreakpointStatus.TIMEOUT: 'timeout',
            BreakpointStatus.CANCELLED: 'rejected',
        }
        event = status_to_event.get(result.status, 'rejected')

        # Extract approvers and rejecters
        approved_by = [r.user_id for r in result.responses if r.approved]
        rejected_by = [r.user_id for r in result.responses if not r.approved]

        # Extract comments
        comments = [
            {'user': r.user_id, 'comment': r.comment}
            for r in result.responses
            if r.comment
        ]

        output_data = {
            'breakpoint_id': result.breakpoint_id,
            'status': result.status.value,
            'auto_approved': False,
            'approved_by': approved_by,
            'rejected_by': rejected_by,
            'custom_inputs': result.final_inputs,
            'comments': comments,
            'resolved_at': result.resolved_at.isoformat(),
            'wait_duration_ms': wait_duration_ms,
        }

        return {
            '__event__': event,
            'outputs': {
                event: output_data
            },
            **output_data,
        }
