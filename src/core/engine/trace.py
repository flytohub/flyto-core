"""
Execution Trace - Complete execution tracking for workflows.

Provides detailed tracing for:
- Workflow-level execution (ExecutionTrace)
- Step-level execution (StepTrace)
- Item-level execution (ItemTrace)

Per ITEM_PIPELINE_SPEC.md Section 8.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class TraceStatus(Enum):
    """Execution status for trace entries."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    PARTIAL = "partial"  # Some items failed


_LEGACY_STATUS_MAP = {
    TraceStatus.SUCCESS.value: "completed",
    TraceStatus.ERROR.value: "failed",
    TraceStatus.RUNNING.value: "running",
    TraceStatus.PENDING.value: "pending",
    TraceStatus.SKIPPED.value: "skipped",
    TraceStatus.PARTIAL.value: "partial",
}


def _to_legacy_status(status: str) -> str:
    """Map new status values to legacy names for backward compatibility."""
    return _LEGACY_STATUS_MAP.get(status, status)


@dataclass
class TraceError:
    """Error information for trace."""
    message: str
    code: Optional[str] = None
    type: Optional[str] = None
    stack: Optional[str] = None


@dataclass
class ItemTrace:
    """
    Single item processing trace.

    Tracks the execution of a single item through a step
    in items mode execution.
    """
    index: int
    status: str = "pending"
    durationMs: int = 0
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Internal timing
    _start_time: Optional[float] = field(default=None, repr=False)

    def start(self) -> "ItemTrace":
        """Mark item processing started."""
        self._start_time = time.time()
        self.status = TraceStatus.RUNNING.value
        return self

    def complete(self, output: Dict[str, Any]) -> "ItemTrace":
        """Mark item processing completed."""
        if self._start_time:
            self.durationMs = int((time.time() - self._start_time) * 1000)
        self.status = TraceStatus.SUCCESS.value
        self.output = output
        return self

    def fail(self, error: str) -> "ItemTrace":
        """Mark item processing failed."""
        if self._start_time:
            self.durationMs = int((time.time() - self._start_time) * 1000)
        self.status = TraceStatus.ERROR.value
        self.error = error
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "index": self.index,
            "status": self.status,
            "statusLegacy": _to_legacy_status(self.status),
            "durationMs": self.durationMs,
        }
        if self.input is not None:
            result["input"] = self.input
        if self.output is not None:
            result["output"] = self.output
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class StepInput:
    """Step input data."""
    params: Dict[str, Any] = field(default_factory=dict)
    paramsRaw: Dict[str, Any] = field(default_factory=dict)  # Before variable resolution
    items: Optional[List[Dict[str, Any]]] = None
    itemCount: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "params": self.params,
            "paramsRaw": self.paramsRaw,
        }
        if self.items is not None:
            result["items"] = self.items
            result["itemCount"] = self.itemCount
        return result


@dataclass
class StepOutput:
    """Step output data."""
    items: List[List[Dict[str, Any]]] = field(default_factory=list)  # [output][item]
    itemCount: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "items": self.items,
            "itemCount": self.itemCount,
        }
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class StepTrace:
    """
    Single step execution trace.

    Tracks the execution of a workflow step including:
    - Timing information
    - Input parameters and items
    - Output items
    - Per-item traces (for items mode)
    """
    stepId: str
    stepIndex: int
    moduleId: str

    status: str = "pending"
    startedAt: Optional[datetime] = None
    endedAt: Optional[datetime] = None
    durationMs: int = 0

    input: Optional[StepInput] = None
    output: Optional[StepOutput] = None

    # Per-item traces (for items mode)
    itemTraces: Optional[List[ItemTrace]] = None

    # Error info
    error: Optional[TraceError] = None

    # Internal timing
    _start_time: Optional[float] = field(default=None, repr=False)

    def start(self) -> "StepTrace":
        """Mark step execution started."""
        self._start_time = time.time()
        self.startedAt = datetime.now()
        self.status = TraceStatus.RUNNING.value
        return self

    def complete(self, output: StepOutput = None) -> "StepTrace":
        """Mark step execution completed."""
        self.endedAt = datetime.now()
        if self._start_time:
            self.durationMs = int((time.time() - self._start_time) * 1000)
        self.status = TraceStatus.SUCCESS.value
        if output:
            self.output = output
        return self

    def fail(self, error: Exception) -> "StepTrace":
        """Mark step execution failed."""
        self.endedAt = datetime.now()
        if self._start_time:
            self.durationMs = int((time.time() - self._start_time) * 1000)
        self.status = TraceStatus.ERROR.value
        self.error = TraceError(
            message=str(error),
            type=type(error).__name__,
        )
        return self

    def skip(self, reason: str = None) -> "StepTrace":
        """Mark step skipped."""
        self.status = TraceStatus.SKIPPED.value
        if reason:
            self.error = TraceError(message=reason, code="SKIPPED")
        return self

    def set_input(
        self,
        params: Dict[str, Any],
        params_raw: Dict[str, Any] = None,
        items: List[Dict[str, Any]] = None
    ) -> "StepTrace":
        """Set step input data."""
        self.input = StepInput(
            params=params,
            paramsRaw=params_raw or params,
            items=items,
            itemCount=len(items) if items else 0,
        )
        return self

    def set_output(
        self,
        items: List[List[Dict[str, Any]]] = None,
        error: str = None
    ) -> "StepTrace":
        """Set step output data."""
        total_items = sum(len(output) for output in items) if items else 0
        self.output = StepOutput(
            items=items or [],
            itemCount=total_items,
            error=error,
        )
        return self

    def add_item_trace(self, item_trace: ItemTrace) -> "StepTrace":
        """Add an item trace."""
        if self.itemTraces is None:
            self.itemTraces = []
        self.itemTraces.append(item_trace)
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "stepId": self.stepId,
            "stepIndex": self.stepIndex,
            "moduleId": self.moduleId,
            "status": self.status,
            "statusLegacy": _to_legacy_status(self.status),
            "durationMs": self.durationMs,
        }
        if self.startedAt:
            result["startedAt"] = self.startedAt.isoformat()
        if self.endedAt:
            result["endedAt"] = self.endedAt.isoformat()
        if self.input:
            result["input"] = self.input.to_dict()
        if self.output:
            result["output"] = self.output.to_dict()
        if self.itemTraces:
            result["itemTraces"] = [t.to_dict() for t in self.itemTraces]
        if self.error:
            result["error"] = {
                "message": self.error.message,
                "code": self.error.code,
                "type": self.error.type,
            }
        return result


@dataclass
class ExecutionTrace:
    """
    Complete workflow execution trace.

    Tracks the full execution of a workflow including:
    - Workflow metadata
    - Timing information
    - Input parameters
    - All step traces
    - Final output
    """
    executionId: str
    workflowId: str
    workflowName: str

    status: str = "pending"
    startedAt: Optional[datetime] = None
    endedAt: Optional[datetime] = None
    durationMs: int = 0

    # Input parameters
    inputParams: Dict[str, Any] = field(default_factory=dict)

    # Step traces
    steps: List[StepTrace] = field(default_factory=list)

    # Final output
    output: Optional[Dict[str, Any]] = None

    # Error (if failed)
    error: Optional[TraceError] = None

    # Internal timing
    _start_time: Optional[float] = field(default=None, repr=False)

    @classmethod
    def create(
        cls,
        workflow_id: str,
        workflow_name: str,
        input_params: Dict[str, Any] = None
    ) -> "ExecutionTrace":
        """Create a new execution trace."""
        return cls(
            executionId=f"exec_{uuid.uuid4().hex[:12]}",
            workflowId=workflow_id,
            workflowName=workflow_name,
            inputParams=input_params or {},
        )

    def start(self) -> "ExecutionTrace":
        """Mark execution started."""
        self._start_time = time.time()
        self.startedAt = datetime.now()
        self.status = TraceStatus.RUNNING.value
        return self

    def complete(self, output: Dict[str, Any] = None) -> "ExecutionTrace":
        """Mark execution completed."""
        self.endedAt = datetime.now()
        if self._start_time:
            self.durationMs = int((time.time() - self._start_time) * 1000)
        self.status = TraceStatus.SUCCESS.value
        self.output = output
        return self

    def fail(self, error: Exception) -> "ExecutionTrace":
        """Mark execution failed."""
        self.endedAt = datetime.now()
        if self._start_time:
            self.durationMs = int((time.time() - self._start_time) * 1000)
        self.status = TraceStatus.ERROR.value
        self.error = TraceError(
            message=str(error),
            type=type(error).__name__,
        )
        return self

    def add_step_trace(self, step_trace: StepTrace) -> "ExecutionTrace":
        """Add a step trace."""
        self.steps.append(step_trace)
        return self

    def get_step_trace(self, step_id: str) -> Optional[StepTrace]:
        """Get step trace by ID."""
        for step in self.steps:
            if step.stepId == step_id:
                return step
        return None

    def create_step_trace(
        self,
        step_id: str,
        step_index: int,
        module_id: str
    ) -> StepTrace:
        """Create and add a new step trace."""
        step_trace = StepTrace(
            stepId=step_id,
            stepIndex=step_index,
            moduleId=module_id,
        )
        self.add_step_trace(step_trace)
        return step_trace

    @property
    def step_count(self) -> int:
        """Get total step count."""
        return len(self.steps)

    @property
    def completed_step_count(self) -> int:
        """Get completed step count."""
        return sum(1 for s in self.steps if s.status == "success")

    @property
    def failed_step_count(self) -> int:
        """Get failed step count."""
        return sum(1 for s in self.steps if s.status == "error")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "executionId": self.executionId,
            "workflowId": self.workflowId,
            "workflowName": self.workflowName,
            "status": self.status,
            "statusLegacy": _to_legacy_status(self.status),
            "durationMs": self.durationMs,
            "inputParams": self.inputParams,
            "steps": [s.to_dict() for s in self.steps],
            "stepCount": self.step_count,
            "completedSteps": self.completed_step_count,
            "failedSteps": self.failed_step_count,
        }
        if self.startedAt:
            result["startedAt"] = self.startedAt.isoformat()
        if self.endedAt:
            result["endedAt"] = self.endedAt.isoformat()
        if self.output is not None:
            result["output"] = self.output
        if self.error:
            result["error"] = {
                "message": self.error.message,
                "code": self.error.code,
                "type": self.error.type,
            }
        return result

    def to_summary(self) -> Dict[str, Any]:
        """Convert to summary format (without step details)."""
        return {
            "executionId": self.executionId,
            "workflowId": self.workflowId,
            "workflowName": self.workflowName,
            "status": self.status,
            "durationMs": self.durationMs,
            "startedAt": self.startedAt.isoformat() if self.startedAt else None,
            "endedAt": self.endedAt.isoformat() if self.endedAt else None,
            "stepCount": self.step_count,
            "completedSteps": self.completed_step_count,
            "failedSteps": self.failed_step_count,
        }


class TraceCollector:
    """
    Collects execution traces during workflow execution.

    Usage:
        collector = TraceCollector(workflow_id, workflow_name, params)
        collector.start()

        step_trace = collector.start_step("step1", 0, "http.request")
        step_trace.set_input(params)
        # ... execute step ...
        step_trace.complete(output)

        trace = collector.complete(output)
    """

    def __init__(
        self,
        workflow_id: str,
        workflow_name: str,
        input_params: Dict[str, Any] = None
    ):
        self.trace = ExecutionTrace.create(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            input_params=input_params,
        )
        self._current_step: Optional[StepTrace] = None

    @property
    def execution_id(self) -> str:
        """Get execution ID."""
        return self.trace.executionId

    def start(self) -> "TraceCollector":
        """Start execution trace."""
        self.trace.start()
        return self

    def start_step(
        self,
        step_id: str,
        step_index: int,
        module_id: str
    ) -> StepTrace:
        """Start a new step trace."""
        step_trace = self.trace.create_step_trace(step_id, step_index, module_id)
        step_trace.start()
        self._current_step = step_trace
        return step_trace

    def complete_step(
        self,
        step_trace: StepTrace = None,
        output: StepOutput = None
    ) -> StepTrace:
        """Complete current or specified step trace."""
        trace = step_trace or self._current_step
        if trace:
            trace.complete(output)
        return trace

    def fail_step(
        self,
        error: Exception,
        step_trace: StepTrace = None
    ) -> StepTrace:
        """Fail current or specified step trace."""
        trace = step_trace or self._current_step
        if trace:
            trace.fail(error)
        return trace

    def skip_step(
        self,
        step_id: str,
        step_index: int,
        module_id: str,
        reason: str = None
    ) -> StepTrace:
        """Record a skipped step."""
        step_trace = self.trace.create_step_trace(step_id, step_index, module_id)
        step_trace.skip(reason)
        return step_trace

    def complete(self, output: Dict[str, Any] = None) -> ExecutionTrace:
        """Complete execution trace."""
        self.trace.complete(output)
        return self.trace

    def fail(self, error: Exception) -> ExecutionTrace:
        """Fail execution trace."""
        self.trace.fail(error)
        return self.trace

    def get_trace(self) -> ExecutionTrace:
        """Get the execution trace."""
        return self.trace
