"""
State Machine Engine - Complete Implementation

Provides:
- In-memory state machine execution
- Event-based transitions
- Guard condition evaluation
- Timeout processing
- Pluggable persistence

Reference: ITEM_PIPELINE_SPEC.md Section 18
"""

import asyncio
import logging
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Protocol

from . import (
    EventPayload,
    InstanceStatus,
    PersistenceConfig,
    StateDefinition,
    StateHistoryEntry,
    StateMachine,
    StateMachineInstance,
    StateType,
    Transition,
    TransitionTrigger,
    TriggerType,
)

logger = logging.getLogger(__name__)


class StateMachineStore(Protocol):
    """Storage protocol for state machine persistence."""

    async def save_machine(self, machine: StateMachine) -> None:
        """Save machine definition."""
        ...

    async def load_machine(self, machine_id: str, version: str = None) -> Optional[StateMachine]:
        """Load machine definition."""
        ...

    async def save_instance(self, instance: StateMachineInstance) -> None:
        """Save instance state."""
        ...

    async def load_instance(self, instance_id: str) -> Optional[StateMachineInstance]:
        """Load instance."""
        ...

    async def query_instances(
        self,
        machine_id: str = None,
        correlation_id: str = None,
        status: InstanceStatus = None,
        current_state: str = None,
        waiting_for_event: str = None,
        limit: int = 100,
    ) -> List[StateMachineInstance]:
        """Query instances with filters."""
        ...

    async def delete_instance(self, instance_id: str) -> bool:
        """Delete instance."""
        ...


class InMemoryStore:
    """In-memory store for development/testing."""

    def __init__(self):
        self._machines: Dict[str, StateMachine] = {}
        self._instances: Dict[str, StateMachineInstance] = {}

    async def save_machine(self, machine: StateMachine) -> None:
        self._machines[machine.machine_id] = machine

    async def load_machine(self, machine_id: str, version: str = None) -> Optional[StateMachine]:
        return self._machines.get(machine_id)

    async def save_instance(self, instance: StateMachineInstance) -> None:
        self._instances[instance.instance_id] = instance

    async def load_instance(self, instance_id: str) -> Optional[StateMachineInstance]:
        return self._instances.get(instance_id)

    async def query_instances(
        self,
        machine_id: str = None,
        correlation_id: str = None,
        status: InstanceStatus = None,
        current_state: str = None,
        waiting_for_event: str = None,
        limit: int = 100,
    ) -> List[StateMachineInstance]:
        results = []
        for inst in self._instances.values():
            if machine_id and inst.machine_id != machine_id:
                continue
            if correlation_id and inst.correlation_id != correlation_id:
                continue
            if status and inst.status != status:
                continue
            if current_state and inst.current_state != current_state:
                continue
            if waiting_for_event and inst.waiting_for_event != waiting_for_event:
                continue
            results.append(inst)
            if len(results) >= limit:
                break
        return results

    async def delete_instance(self, instance_id: str) -> bool:
        if instance_id in self._instances:
            del self._instances[instance_id]
            return True
        return False


class GuardEvaluator:
    """Evaluates guard conditions safely."""

    def __init__(self, custom_functions: Dict[str, Callable] = None):
        self._functions = custom_functions or {}

    def evaluate(self, expression: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate guard expression.

        Supports:
        - Simple comparisons: field == 'value', field != 'value'
        - Membership: field in ['a', 'b']
        - Boolean: field == True
        - Combined with and/or

        Args:
            expression: Guard expression
            context: Evaluation context (state_data + event_data)

        Returns:
            True if guard passes
        """
        if not expression:
            return True

        try:
            # Create safe evaluation context
            safe_context = {
                "__builtins__": {},
                "True": True,
                "False": False,
                "None": None,
            }
            safe_context.update(context)

            # Simple expression evaluation
            result = eval(expression, safe_context)
            return bool(result)

        except Exception as e:
            logger.warning(f"Guard evaluation failed: {expression} - {e}")
            return False


class StateMachineEngineImpl:
    """
    State Machine Engine Implementation.

    Manages state machine definitions and instances.
    """

    def __init__(
        self,
        store: StateMachineStore = None,
        action_executor: Callable = None,
    ):
        """
        Initialize engine.

        Args:
            store: Storage backend (default: in-memory)
            action_executor: Async function to execute workflow actions
                           Signature: async def(workflow_id: str, context: Dict) -> Dict
        """
        self._store = store or InMemoryStore()
        self._action_executor = action_executor
        self._guard_evaluator = GuardEvaluator()
        self._lock = asyncio.Lock()

    async def register_machine(self, machine: StateMachine) -> str:
        """Register a state machine definition."""
        # Validate
        errors = machine.validate()
        if errors:
            raise ValueError(f"Invalid state machine: {errors}")

        # Set timestamps
        now = datetime.utcnow()
        machine.created_at = machine.created_at or now
        machine.updated_at = now

        await self._store.save_machine(machine)
        logger.info(f"Registered state machine: {machine.machine_id}")
        return machine.machine_id

    async def get_machine(
        self,
        machine_id: str,
        version: str = None,
    ) -> Optional[StateMachine]:
        """Get state machine definition."""
        return await self._store.load_machine(machine_id, version)

    async def create_instance(
        self,
        machine_id: str,
        correlation_id: str,
        initial_data: Dict[str, Any] = None,
    ) -> StateMachineInstance:
        """Create a new state machine instance."""
        machine = await self._store.load_machine(machine_id)
        if not machine:
            raise ValueError(f"Machine not found: {machine_id}")

        now = datetime.utcnow()
        instance = StateMachineInstance(
            instance_id=str(uuid.uuid4()),
            machine_id=machine_id,
            machine_version=machine.version,
            correlation_id=correlation_id,
            current_state=machine.initial_state,
            state_data=initial_data or {},
            status=InstanceStatus.RUNNING,
            created_at=now,
            last_transition_at=now,
        )

        # Calculate global expiry
        if machine.global_timeout:
            instance.expires_at = now + machine.global_timeout

        # Execute on_enter for initial state
        initial_state_def = machine.get_state(machine.initial_state)
        if initial_state_def and initial_state_def.on_enter:
            await self._execute_action(initial_state_def.on_enter, instance)

        # Check if initial state is WAITING
        if initial_state_def and initial_state_def.state_type == StateType.WAITING:
            instance.status = InstanceStatus.WAITING
            instance.waiting_since = now
            # Find what event this state waits for
            for t in machine.get_transitions_from(machine.initial_state):
                if t.trigger.trigger_type == TriggerType.EVENT and t.trigger.event_name:
                    instance.waiting_for_event = t.trigger.event_name
                    break

        await self._store.save_instance(instance)
        logger.info(f"Created instance: {instance.instance_id} for machine: {machine_id}")
        return instance

    async def send_event(
        self,
        instance_id: str,
        event: EventPayload,
    ) -> StateMachineInstance:
        """Send event to instance."""
        async with self._lock:
            instance = await self._store.load_instance(instance_id)
            if not instance:
                raise ValueError(f"Instance not found: {instance_id}")

            if instance.status in (InstanceStatus.COMPLETED, InstanceStatus.CANCELLED, InstanceStatus.FAILED):
                raise ValueError(f"Instance {instance_id} is in terminal state: {instance.status}")

            machine = await self._store.load_machine(instance.machine_id)
            if not machine:
                raise ValueError(f"Machine not found: {instance.machine_id}")

            # Find matching transition
            transition = await self._find_matching_transition(
                machine, instance, event
            )

            if transition:
                instance = await self._execute_transition(
                    machine, instance, transition, event
                )

            await self._store.save_instance(instance)
            return instance

    async def send_event_by_correlation(
        self,
        correlation_id: str,
        event: EventPayload,
    ) -> List[StateMachineInstance]:
        """Send event to all instances with correlation ID."""
        instances = await self._store.query_instances(correlation_id=correlation_id)
        results = []
        for inst in instances:
            if inst.status not in (InstanceStatus.COMPLETED, InstanceStatus.CANCELLED, InstanceStatus.FAILED):
                try:
                    updated = await self.send_event(inst.instance_id, event)
                    results.append(updated)
                except Exception as e:
                    logger.error(f"Failed to send event to {inst.instance_id}: {e}")
        return results

    async def transition(
        self,
        instance_id: str,
        transition_name: str,
        data: Dict[str, Any] = None,
    ) -> StateMachineInstance:
        """Manually trigger a transition."""
        async with self._lock:
            instance = await self._store.load_instance(instance_id)
            if not instance:
                raise ValueError(f"Instance not found: {instance_id}")

            machine = await self._store.load_machine(instance.machine_id)
            if not machine:
                raise ValueError(f"Machine not found: {instance.machine_id}")

            # Find transition by name
            transition = None
            for t in machine.get_transitions_from(instance.current_state):
                if t.name == transition_name:
                    transition = t
                    break

            if not transition:
                raise ValueError(
                    f"Transition '{transition_name}' not found from state '{instance.current_state}'"
                )

            # Merge data
            if data:
                instance.state_data.update(data)

            # Execute transition
            event = EventPayload(event_name=f"manual:{transition_name}", data=data or {})
            instance = await self._execute_transition(machine, instance, transition, event)

            await self._store.save_instance(instance)
            return instance

    async def get_instance(self, instance_id: str) -> Optional[StateMachineInstance]:
        """Get instance by ID."""
        return await self._store.load_instance(instance_id)

    async def get_instances_by_correlation(
        self,
        correlation_id: str,
    ) -> List[StateMachineInstance]:
        """Get all instances for a correlation ID."""
        return await self._store.query_instances(correlation_id=correlation_id)

    async def get_instances(
        self,
        machine_id: str = None,
        status: InstanceStatus = None,
        current_state: str = None,
        limit: int = 100,
    ) -> List[StateMachineInstance]:
        """Get instances with filters."""
        return await self._store.query_instances(
            machine_id=machine_id,
            status=status,
            current_state=current_state,
            limit=limit,
        )

    async def get_waiting_instances(
        self,
        event_name: str = None,
        older_than: timedelta = None,
    ) -> List[StateMachineInstance]:
        """Get instances waiting for events."""
        instances = await self._store.query_instances(
            status=InstanceStatus.WAITING,
            waiting_for_event=event_name,
        )

        if older_than:
            cutoff = datetime.utcnow() - older_than
            instances = [i for i in instances if i.waiting_since and i.waiting_since < cutoff]

        return instances

    async def cancel(
        self,
        instance_id: str,
        reason: str = None,
    ) -> StateMachineInstance:
        """Cancel an instance."""
        async with self._lock:
            instance = await self._store.load_instance(instance_id)
            if not instance:
                raise ValueError(f"Instance not found: {instance_id}")

            instance.status = InstanceStatus.CANCELLED
            instance.error = reason or "Cancelled by user"

            await self._store.save_instance(instance)
            logger.info(f"Cancelled instance: {instance_id}")
            return instance

    async def process_timeouts(self) -> int:
        """Process timed-out instances."""
        count = 0
        now = datetime.utcnow()

        # Get all running/waiting instances
        instances = await self._store.query_instances(status=InstanceStatus.RUNNING)
        instances.extend(await self._store.query_instances(status=InstanceStatus.WAITING))

        for instance in instances:
            try:
                # Check global expiry
                if instance.expires_at and now > instance.expires_at:
                    instance.status = InstanceStatus.EXPIRED
                    instance.error = "Global timeout exceeded"
                    await self._store.save_instance(instance)
                    count += 1
                    continue

                # Check state timeout
                machine = await self._store.load_machine(instance.machine_id)
                if not machine:
                    continue

                state_def = machine.get_state(instance.current_state)
                if not state_def or not state_def.timeout:
                    continue

                # Check if state has timed out
                if instance.last_transition_at:
                    state_deadline = instance.last_transition_at + state_def.timeout
                    if now > state_deadline:
                        # Find timeout transition
                        if state_def.on_timeout_transition:
                            for t in machine.get_transitions_from(instance.current_state):
                                if t.name == state_def.on_timeout_transition:
                                    event = EventPayload(event_name="timeout")
                                    instance = await self._execute_transition(
                                        machine, instance, t, event
                                    )
                                    await self._store.save_instance(instance)
                                    count += 1
                                    break

            except Exception as e:
                logger.error(f"Error processing timeout for {instance.instance_id}: {e}")

        return count

    async def _find_matching_transition(
        self,
        machine: StateMachine,
        instance: StateMachineInstance,
        event: EventPayload,
    ) -> Optional[Transition]:
        """Find a matching transition for the event."""
        transitions = machine.get_transitions_from(instance.current_state)

        # Sort by priority
        transitions.sort(key=lambda t: t.priority, reverse=True)

        for t in transitions:
            # Check trigger type matches
            if t.trigger.trigger_type != TriggerType.EVENT:
                continue

            # Check event name matches
            if t.trigger.event_name != event.event_name:
                continue

            # Check guard condition
            if t.guard:
                context = {**instance.state_data, **event.data}
                if not self._guard_evaluator.evaluate(t.guard, context):
                    continue

            return t

        return None

    async def _execute_transition(
        self,
        machine: StateMachine,
        instance: StateMachineInstance,
        transition: Transition,
        event: EventPayload,
    ) -> StateMachineInstance:
        """Execute a state transition."""
        from_state = instance.current_state
        to_state = transition.to_state

        logger.info(
            f"Transition: {instance.instance_id} {from_state} -> {to_state} via {transition.name}"
        )

        # Execute on_exit for current state
        current_state_def = machine.get_state(from_state)
        if current_state_def and current_state_def.on_exit:
            await self._execute_action(current_state_def.on_exit, instance)

        # Execute transition action
        if transition.action:
            await self._execute_action(transition.action, instance)

        # Update state
        instance.current_state = to_state
        if event.data:
            instance.state_data.update(event.data)

        # Record history
        instance.record_transition(
            from_state=from_state,
            to_state=to_state,
            transition_name=transition.name,
            trigger=event.event_name,
        )

        # Execute on_enter for new state
        new_state_def = machine.get_state(to_state)
        if new_state_def:
            if new_state_def.on_enter:
                await self._execute_action(new_state_def.on_enter, instance)

            # Update status based on new state type
            if new_state_def.state_type == StateType.FINAL:
                instance.status = InstanceStatus.COMPLETED
                instance.waiting_for_event = None
                instance.waiting_since = None
            elif new_state_def.state_type == StateType.WAITING:
                instance.status = InstanceStatus.WAITING
                instance.waiting_since = datetime.utcnow()
                # Find what event this state waits for
                for t in machine.get_transitions_from(to_state):
                    if t.trigger.trigger_type == TriggerType.EVENT and t.trigger.event_name:
                        instance.waiting_for_event = t.trigger.event_name
                        break
            else:
                instance.status = InstanceStatus.RUNNING
                instance.waiting_for_event = None
                instance.waiting_since = None

        return instance

    async def _execute_action(
        self,
        action: str,
        instance: StateMachineInstance,
    ) -> None:
        """Execute a workflow action."""
        if not self._action_executor:
            logger.debug(f"No action executor configured, skipping: {action}")
            return

        try:
            context = {
                "instance_id": instance.instance_id,
                "correlation_id": instance.correlation_id,
                "current_state": instance.current_state,
                "state_data": instance.state_data,
            }
            result = await self._action_executor(action, context)
            if result:
                instance.state_data.update(result)
        except Exception as e:
            logger.error(f"Action execution failed: {action} - {e}")
            raise


# Singleton instance for convenience
_engine: Optional[StateMachineEngineImpl] = None


def get_engine(
    store: StateMachineStore = None,
    action_executor: Callable = None,
) -> StateMachineEngineImpl:
    """Get or create the state machine engine singleton."""
    global _engine
    if _engine is None:
        _engine = StateMachineEngineImpl(store=store, action_executor=action_executor)
    return _engine


def reset_engine() -> None:
    """Reset the singleton engine (for testing)."""
    global _engine
    _engine = None
