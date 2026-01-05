"""
Engine SDK Interface

Stable interface for flyto-cloud and other consumers.
This is the contract between flyto-core and external systems.

Version: 1.0.0
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from .models import (
    AutocompleteResult,
    EngineEvent,
    EventType,
    ExecutionOptions,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTrace,
    IntrospectionMode,
    NodeSnapshot,
    ParsedExpression,
    ValidationResult,
    VarCatalog,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Abstract Interface
# =============================================================================

class EngineSDKInterface(ABC):
    """Abstract interface for Engine SDK"""

    # API version for compatibility checking
    api_version: str = "1.0"

    @abstractmethod
    def validate(self, workflow: Dict[str, Any]) -> ValidationResult:
        """Validate workflow structure and connections"""
        pass

    @abstractmethod
    async def execute(
        self,
        workflow: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Optional[ExecutionOptions] = None,
    ) -> ExecutionResult:
        """Execute workflow and return result"""
        pass

    @abstractmethod
    async def execute_stream(
        self,
        workflow: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Optional[ExecutionOptions] = None,
    ) -> AsyncIterator[EngineEvent]:
        """Execute workflow with streaming events"""
        pass

    @abstractmethod
    def introspect(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        mode: IntrospectionMode = IntrospectionMode.EDIT,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> VarCatalog:
        """Get available variables for a node"""
        pass

    @abstractmethod
    def get_execution_trace(
        self,
        execution_id: str,
    ) -> Optional[ExecutionTrace]:
        """Get execution trace for debugging"""
        pass

    @abstractmethod
    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution"""
        pass

    @abstractmethod
    def pause(self, execution_id: str) -> bool:
        """Pause a running execution"""
        pass

    @abstractmethod
    def resume(self, execution_id: str) -> bool:
        """Resume a paused execution"""
        pass

    @abstractmethod
    def parse_expression(self, expression: str) -> ParsedExpression:
        """Parse a variable expression"""
        pass

    @abstractmethod
    def autocomplete(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        prefix: str,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> AutocompleteResult:
        """Get autocomplete suggestions"""
        pass

    @abstractmethod
    def validate_expression(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        expression: str,
        expected_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate an expression"""
        pass


# =============================================================================
# Default Implementation
# =============================================================================

class EngineSDK(EngineSDKInterface):
    """Default Engine SDK implementation"""

    api_version: str = "1.0"

    def __init__(self):
        # Execution state tracking
        self._executions: Dict[str, Dict[str, Any]] = {}
        self._traces: Dict[str, ExecutionTrace] = {}

    def validate(self, workflow: Dict[str, Any]) -> ValidationResult:
        """Validate workflow structure and connections"""
        try:
            from core.validation import validate_workflow
        except ImportError:
            # Fallback validation
            return self._basic_validate(workflow)

        nodes = workflow.get("nodes", [])
        edges = workflow.get("edges", [])

        # Handle steps format
        if not nodes and workflow.get("steps"):
            from ..introspection.catalog import _convert_steps_to_graph
            nodes, edges = _convert_steps_to_graph(workflow.get("steps", []))

        result = validate_workflow(nodes, edges)

        return ValidationResult(
            valid=result.valid,
            errors=[
                {"code": e.code, "path": e.path, "message": e.message, "meta": e.meta}
                for e in result.errors
            ],
            warnings=[
                {"code": w.code, "path": w.path, "message": w.message, "meta": w.meta}
                for w in result.warnings
            ],
        )

    def _basic_validate(self, workflow: Dict[str, Any]) -> ValidationResult:
        """Basic validation when core.validation not available"""
        errors = []

        nodes = workflow.get("nodes", []) or workflow.get("steps", [])
        if not nodes:
            errors.append({
                "code": "NO_NODES",
                "path": "workflow",
                "message": "Workflow has no nodes",
                "meta": {},
            })

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
        )

    async def execute(
        self,
        workflow: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Optional[ExecutionOptions] = None,
    ) -> ExecutionResult:
        """Execute workflow and return result"""
        options = options or ExecutionOptions()
        execution_id = str(uuid.uuid4())

        # Track execution
        self._executions[execution_id] = {
            "status": ExecutionStatus.RUNNING,
            "started_at": datetime.now(),
        }

        try:
            # Import and use the workflow engine
            from ..workflow.engine import WorkflowEngine

            engine = WorkflowEngine(
                workflow=workflow,
                params=inputs,
                step_mode=options.step_mode,
                breakpoints=set(options.breakpoints) if options.breakpoints else None,
            )

            result = await engine.execute()

            # Create trace if enabled
            trace = None
            if options.enable_trace:
                trace = self._build_trace(
                    execution_id,
                    workflow.get("id", "workflow"),
                    engine,
                )
                self._traces[execution_id] = trace

            self._executions[execution_id]["status"] = ExecutionStatus.COMPLETED

            return ExecutionResult(
                ok=True,
                execution_id=execution_id,
                status=ExecutionStatus.COMPLETED,
                outputs=result.get("outputs", {}),
                variables=result.get("variables", engine.context),
                trace=trace,
            )

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            self._executions[execution_id]["status"] = ExecutionStatus.FAILED

            return ExecutionResult(
                ok=False,
                execution_id=execution_id,
                status=ExecutionStatus.FAILED,
                error=str(e),
                error_code="EXECUTION_ERROR",
            )

    async def execute_stream(
        self,
        workflow: Dict[str, Any],
        inputs: Dict[str, Any],
        options: Optional[ExecutionOptions] = None,
    ) -> AsyncIterator[EngineEvent]:
        """Execute workflow with streaming events"""
        options = options or ExecutionOptions()
        execution_id = str(uuid.uuid4())

        # Emit start event
        yield EngineEvent(
            event_type=EventType.ENGINE_START,
            timestamp=time.time(),
            execution_id=execution_id,
            payload={"workflow_id": workflow.get("id", "workflow")},
        )

        try:
            from ..workflow.engine import WorkflowEngine
            from ..hooks import ExecutorHooks, HookContext

            # Create hooks that emit events
            class StreamingHooks(ExecutorHooks):
                def __init__(self, execution_id: str, events: list):
                    self._execution_id = execution_id
                    self._events = events

                def on_pre_execute(self, ctx: HookContext):
                    self._events.append(EngineEvent(
                        event_type=EventType.NODE_START,
                        timestamp=time.time(),
                        execution_id=self._execution_id,
                        node_id=ctx.step_id,
                        payload={
                            "module_id": ctx.module_id,
                            "step_index": ctx.step_index,
                        },
                    ))
                    return super().on_pre_execute(ctx)

                def on_post_execute(self, ctx: HookContext):
                    self._events.append(EngineEvent(
                        event_type=EventType.NODE_END,
                        timestamp=time.time(),
                        execution_id=self._execution_id,
                        node_id=ctx.step_id,
                        payload={
                            "result": ctx.result,
                            "elapsed_ms": ctx.elapsed_ms,
                        },
                    ))
                    return super().on_post_execute(ctx)

            events: List[EngineEvent] = []
            hooks = StreamingHooks(execution_id, events)

            engine = WorkflowEngine(
                workflow=workflow,
                params=inputs,
                hooks=hooks,
                step_mode=options.step_mode,
            )

            result = await engine.execute()

            # Yield collected events
            for event in events:
                yield event

            # Emit end event
            yield EngineEvent(
                event_type=EventType.ENGINE_END,
                timestamp=time.time(),
                execution_id=execution_id,
                payload={
                    "ok": True,
                    "outputs": result.get("outputs", {}),
                },
            )

        except Exception as e:
            yield EngineEvent(
                event_type=EventType.ERROR,
                timestamp=time.time(),
                execution_id=execution_id,
                payload={"error": str(e)},
            )

            yield EngineEvent(
                event_type=EventType.ENGINE_END,
                timestamp=time.time(),
                execution_id=execution_id,
                payload={"ok": False, "error": str(e)},
            )

    def introspect(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        mode: IntrospectionMode = IntrospectionMode.EDIT,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> VarCatalog:
        """Get available variables for a node"""
        from ..introspection.catalog import build_catalog

        return build_catalog(
            workflow=workflow,
            node_id=node_id,
            mode=mode,
            context_snapshot=context_snapshot,
        )

    def get_execution_trace(
        self,
        execution_id: str,
    ) -> Optional[ExecutionTrace]:
        """Get execution trace for debugging"""
        return self._traces.get(execution_id)

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution"""
        if execution_id not in self._executions:
            return False

        self._executions[execution_id]["status"] = ExecutionStatus.CANCELLED
        # TODO: Implement actual cancellation via engine reference
        return True

    def pause(self, execution_id: str) -> bool:
        """Pause a running execution"""
        if execution_id not in self._executions:
            return False

        self._executions[execution_id]["status"] = ExecutionStatus.PAUSED
        # TODO: Implement actual pause via engine reference
        return True

    def resume(self, execution_id: str) -> bool:
        """Resume a paused execution"""
        if execution_id not in self._executions:
            return False

        if self._executions[execution_id]["status"] != ExecutionStatus.PAUSED:
            return False

        self._executions[execution_id]["status"] = ExecutionStatus.RUNNING
        # TODO: Implement actual resume via engine reference
        return True

    def parse_expression(self, expression: str) -> ParsedExpression:
        """Parse a variable expression"""
        from .resolver import ExpressionParser

        parser = ExpressionParser()
        return parser.parse(expression)

    def autocomplete(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        prefix: str,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ) -> AutocompleteResult:
        """Get autocomplete suggestions"""
        from ..introspection.autocomplete import autocomplete as do_autocomplete

        return do_autocomplete(
            workflow=workflow,
            node_id=node_id,
            prefix=prefix,
            context_snapshot=context_snapshot,
        )

    def validate_expression(
        self,
        workflow: Dict[str, Any],
        node_id: str,
        expression: str,
        expected_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate an expression"""
        from ..introspection.autocomplete import validate_expression as do_validate

        return do_validate(
            workflow=workflow,
            node_id=node_id,
            expression=expression,
            expected_type=expected_type,
        )

    def _build_trace(
        self,
        execution_id: str,
        workflow_id: str,
        engine: Any,
    ) -> ExecutionTrace:
        """Build execution trace from engine state"""
        nodes = []

        for log_entry in engine.execution_log:
            nodes.append(NodeSnapshot(
                node_id=log_entry.get("step_id", ""),
                module_id=log_entry.get("module_id", ""),
                status=ExecutionStatus.COMPLETED,
            ))

        return ExecutionTrace(
            execution_id=execution_id,
            workflow_id=workflow_id,
            status=ExecutionStatus.COMPLETED,
            started_at=datetime.fromtimestamp(engine.start_time) if engine.start_time else None,
            ended_at=datetime.fromtimestamp(engine.end_time) if engine.end_time else None,
            duration_ms=(engine.end_time - engine.start_time) * 1000 if engine.end_time and engine.start_time else 0,
            nodes=nodes,
            final_output=engine.context,
        )


# =============================================================================
# Singleton Instance
# =============================================================================

_sdk_instance: Optional[EngineSDK] = None


def get_sdk() -> EngineSDK:
    """Get the singleton SDK instance"""
    global _sdk_instance
    if _sdk_instance is None:
        _sdk_instance = EngineSDK()
    return _sdk_instance
