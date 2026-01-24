"""
State Machine - Long-Running Workflow Support

Support for workflows that span days/weeks:
- State machine definitions
- Waiting for external events
- Timeout handling
- State persistence
- Nested state machines

Reference: ITEM_PIPELINE_SPEC.md Section 18
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class StateType(Enum):
    """State types."""
    INITIAL = "initial"      # Starting state
    NORMAL = "normal"        # Regular state
    FINAL = "final"          # Terminal state
    WAITING = "waiting"      # Waiting for external event
    PARALLEL = "parallel"    # Parallel execution


class TriggerType(Enum):
    """Transition trigger types."""
    EVENT = "event"          # External event
    TIMEOUT = "timeout"      # Timeout
    CONDITION = "condition"  # Condition met
    MANUAL = "manual"        # Manual trigger


class InstanceStatus(Enum):
    """State machine instance status."""
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class TransitionTrigger:
    """Transition trigger definition."""
    trigger_type: TriggerType
    event_name: Optional[str] = None        # For EVENT type
    timeout: Optional[timedelta] = None     # For TIMEOUT type
    condition: Optional[str] = None         # For CONDITION type (expression)


@dataclass
class Transition:
    """State transition definition."""
    name: str
    from_state: str
    to_state: str

    # Trigger
    trigger: TransitionTrigger

    # Guard condition (optional)
    guard: Optional[str] = None  # Expression that must be true

    # Action (optional)
    action: Optional[str] = None  # Workflow ID to execute

    # Priority (for multiple matching transitions)
    priority: int = 0


@dataclass
class StateDefinition:
    """State definition."""
    state_id: str
    state_type: StateType = StateType.NORMAL
    name: str = ""

    # Entry/Exit actions (workflow IDs)
    on_enter: Optional[str] = None
    on_exit: Optional[str] = None

    # Nested state machine
    child_machine_id: Optional[str] = None

    # Timeout
    timeout: Optional[timedelta] = None
    on_timeout_transition: Optional[str] = None

    # Metadata
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class PersistenceConfig:
    """Persistence configuration."""
    store_type: str = "database"  # "database" | "redis" | "file"
    snapshot_interval_seconds: int = 60
    retention_days: int = 90


@dataclass
class StateMachine:
    """State machine definition."""
    machine_id: str
    name: str
    version: str = "1.0"

    # States
    initial_state: str = ""
    states: Dict[str, StateDefinition] = field(default_factory=dict)

    # Transitions
    transitions: List[Transition] = field(default_factory=list)

    # Persistence
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)

    # Global timeout
    global_timeout: Optional[timedelta] = None

    # Metadata
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_transitions_from(self, state_id: str) -> List[Transition]:
        """Get all transitions from a state."""
        return [t for t in self.transitions if t.from_state == state_id]

    def get_state(self, state_id: str) -> Optional[StateDefinition]:
        """Get state by ID."""
        return self.states.get(state_id)

    def validate(self) -> List[str]:
        """Validate state machine definition."""
        errors = []

        # Check initial state exists
        if self.initial_state not in self.states:
            errors.append(f"Initial state '{self.initial_state}' not defined")

        # Check all transitions reference valid states
        for t in self.transitions:
            if t.from_state not in self.states:
                errors.append(f"Transition '{t.name}' references unknown state '{t.from_state}'")
            if t.to_state not in self.states:
                errors.append(f"Transition '{t.name}' references unknown state '{t.to_state}'")

        # Check at least one final state
        final_states = [s for s in self.states.values() if s.state_type == StateType.FINAL]
        if not final_states:
            errors.append("No final state defined")

        return errors


@dataclass
class StateHistoryEntry:
    """State transition history entry."""
    from_state: str
    to_state: str
    transition_name: str
    timestamp: datetime
    trigger: str
    data_snapshot: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class StateMachineInstance:
    """Running state machine instance."""
    instance_id: str
    machine_id: str
    machine_version: str

    # Correlation (business key)
    correlation_id: str

    # Current state
    current_state: str
    state_data: Dict[str, Any] = field(default_factory=dict)

    # Status
    status: InstanceStatus = InstanceStatus.RUNNING

    # History
    state_history: List[StateHistoryEntry] = field(default_factory=list)

    # Timing
    created_at: Optional[datetime] = None
    last_transition_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Waiting info (when status=WAITING)
    waiting_for_event: Optional[str] = None
    waiting_since: Optional[datetime] = None

    # Error info
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None

    # Parent (for nested machines)
    parent_instance_id: Optional[str] = None
    parent_state: Optional[str] = None

    def record_transition(
        self,
        from_state: str,
        to_state: str,
        transition_name: str,
        trigger: str,
    ) -> StateHistoryEntry:
        """Record a state transition."""
        now = datetime.utcnow()
        duration = 0
        if self.last_transition_at:
            duration = int((now - self.last_transition_at).total_seconds() * 1000)

        entry = StateHistoryEntry(
            from_state=from_state,
            to_state=to_state,
            transition_name=transition_name,
            timestamp=now,
            trigger=trigger,
            data_snapshot=dict(self.state_data),
            duration_ms=duration,
        )
        self.state_history.append(entry)
        self.last_transition_at = now
        return entry


@dataclass
class EventPayload:
    """External event payload."""
    event_name: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    source: Optional[str] = None


class StateMachineEngine:
    """
    State machine execution engine.

    Manages state machine instances and event processing.

    For actual implementation, use:
        from src.core.enterprise.state_machine.engine import get_engine
        engine = get_engine()
    """

    async def register_machine(
        self,
        machine: StateMachine,
    ) -> str:
        """
        Register a state machine definition.

        Args:
            machine: State machine definition

        Returns:
            Machine ID
        """
        raise NotImplementedError("Use engine.py implementation")

    async def get_machine(
        self,
        machine_id: str,
        version: str = None,
    ) -> Optional[StateMachine]:
        """
        Get state machine definition.

        Args:
            machine_id: Machine ID
            version: Optional specific version

        Returns:
            State machine or None
        """
        raise NotImplementedError("Implementation required")

    async def create_instance(
        self,
        machine_id: str,
        correlation_id: str,
        initial_data: Dict[str, Any] = None,
    ) -> StateMachineInstance:
        """
        Create a new state machine instance.

        Args:
            machine_id: Machine definition ID
            correlation_id: Business correlation ID
            initial_data: Optional initial state data

        Returns:
            New instance
        """
        raise NotImplementedError("Implementation required")

    async def send_event(
        self,
        instance_id: str,
        event: EventPayload,
    ) -> StateMachineInstance:
        """
        Send event to instance.

        Args:
            instance_id: Target instance
            event: Event payload

        Returns:
            Updated instance
        """
        raise NotImplementedError("Implementation required")

    async def send_event_by_correlation(
        self,
        correlation_id: str,
        event: EventPayload,
    ) -> List[StateMachineInstance]:
        """
        Send event to all instances with correlation ID.

        Args:
            correlation_id: Business correlation ID
            event: Event payload

        Returns:
            Updated instances
        """
        raise NotImplementedError("Implementation required")

    async def transition(
        self,
        instance_id: str,
        transition_name: str,
        data: Dict[str, Any] = None,
    ) -> StateMachineInstance:
        """
        Manually trigger a transition.

        Args:
            instance_id: Target instance
            transition_name: Transition to execute
            data: Optional data to merge

        Returns:
            Updated instance
        """
        raise NotImplementedError("Implementation required")

    async def get_instance(
        self,
        instance_id: str,
    ) -> Optional[StateMachineInstance]:
        """Get instance by ID."""
        raise NotImplementedError("Implementation required")

    async def get_instances_by_correlation(
        self,
        correlation_id: str,
    ) -> List[StateMachineInstance]:
        """Get all instances for a correlation ID."""
        raise NotImplementedError("Implementation required")

    async def get_instances(
        self,
        machine_id: str = None,
        status: InstanceStatus = None,
        current_state: str = None,
        limit: int = 100,
    ) -> List[StateMachineInstance]:
        """
        Get instances with filters.

        Args:
            machine_id: Filter by machine
            status: Filter by status
            current_state: Filter by current state
            limit: Maximum results

        Returns:
            List of instances
        """
        raise NotImplementedError("Implementation required")

    async def get_waiting_instances(
        self,
        event_name: str = None,
        older_than: timedelta = None,
    ) -> List[StateMachineInstance]:
        """
        Get instances waiting for events.

        Args:
            event_name: Filter by event being waited for
            older_than: Filter by wait duration

        Returns:
            List of waiting instances
        """
        raise NotImplementedError("Implementation required")

    async def cancel(
        self,
        instance_id: str,
        reason: str = None,
    ) -> StateMachineInstance:
        """
        Cancel an instance.

        Args:
            instance_id: Instance to cancel
            reason: Optional reason

        Returns:
            Cancelled instance
        """
        raise NotImplementedError("Implementation required")

    async def process_timeouts(self) -> int:
        """
        Process timed-out instances.

        Returns:
            Number of instances processed
        """
        raise NotImplementedError("Implementation required")


# Example: Approval workflow state machine
APPROVAL_WORKFLOW = StateMachine(
    machine_id="approval_process",
    name="Document Approval",
    initial_state="draft",
    states={
        "draft": StateDefinition(
            state_id="draft",
            state_type=StateType.INITIAL,
            name="Draft",
        ),
        "pending_review": StateDefinition(
            state_id="pending_review",
            state_type=StateType.WAITING,
            name="Pending Review",
            on_enter="notify_reviewer_workflow",
            timeout=timedelta(days=7),
            on_timeout_transition="escalate",
        ),
        "pending_approval": StateDefinition(
            state_id="pending_approval",
            state_type=StateType.WAITING,
            name="Pending Approval",
            on_enter="notify_approver_workflow",
            timeout=timedelta(days=3),
            on_timeout_transition="auto_reject",
        ),
        "approved": StateDefinition(
            state_id="approved",
            state_type=StateType.FINAL,
            name="Approved",
            on_enter="process_approved_workflow",
        ),
        "rejected": StateDefinition(
            state_id="rejected",
            state_type=StateType.FINAL,
            name="Rejected",
            on_enter="notify_rejection_workflow",
        ),
    },
    transitions=[
        Transition(
            name="submit",
            from_state="draft",
            to_state="pending_review",
            trigger=TransitionTrigger(
                trigger_type=TriggerType.EVENT,
                event_name="submit",
            ),
        ),
        Transition(
            name="review_pass",
            from_state="pending_review",
            to_state="pending_approval",
            trigger=TransitionTrigger(
                trigger_type=TriggerType.EVENT,
                event_name="review_complete",
            ),
            guard="review_result == 'pass'",
        ),
        Transition(
            name="review_fail",
            from_state="pending_review",
            to_state="rejected",
            trigger=TransitionTrigger(
                trigger_type=TriggerType.EVENT,
                event_name="review_complete",
            ),
            guard="review_result == 'fail'",
        ),
        Transition(
            name="approve",
            from_state="pending_approval",
            to_state="approved",
            trigger=TransitionTrigger(
                trigger_type=TriggerType.EVENT,
                event_name="approval_decision",
            ),
            guard="decision == 'approve'",
        ),
        Transition(
            name="reject",
            from_state="pending_approval",
            to_state="rejected",
            trigger=TransitionTrigger(
                trigger_type=TriggerType.EVENT,
                event_name="approval_decision",
            ),
            guard="decision == 'reject'",
        ),
        Transition(
            name="escalate",
            from_state="pending_review",
            to_state="pending_approval",
            trigger=TransitionTrigger(trigger_type=TriggerType.TIMEOUT),
        ),
        Transition(
            name="auto_reject",
            from_state="pending_approval",
            to_state="rejected",
            trigger=TransitionTrigger(trigger_type=TriggerType.TIMEOUT),
        ),
    ],
)


__all__ = [
    # Enums
    'StateType',
    'TriggerType',
    'InstanceStatus',
    # Definitions
    'TransitionTrigger',
    'Transition',
    'StateDefinition',
    'PersistenceConfig',
    'StateMachine',
    # Instance
    'StateHistoryEntry',
    'StateMachineInstance',
    'EventPayload',
    # Engine
    'StateMachineEngine',
    # Examples
    'APPROVAL_WORKFLOW',
]
