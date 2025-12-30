"""
Workflow Engine - Execute YAML workflows with flow control support

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.workflow instead:

    from core.engine.workflow import WorkflowEngine

All functionality has been split into:
- core/engine/workflow/routing.py - Edge routing and step connections
- core/engine/workflow/debug.py - Pause, resume, breakpoints
- core/engine/workflow/output.py - Output collection
- core/engine/workflow/engine.py - Main WorkflowEngine class

Architecture (existing modules):
- exceptions.py - Exception classes
- flow_control.py - Flow control detection
- step_executor.py - Step execution
- variable_resolver.py - Variable resolution
- hooks.py - Executor hooks
"""

# Re-export for backwards compatibility
from .workflow import (
    WorkflowEngine,
    WorkflowRouter,
    DebugController,
    OutputCollector,
)

# Also re-export exceptions for convenience
from .exceptions import (
    StepTimeoutError,
    WorkflowExecutionError,
    StepExecutionError,
)

__all__ = [
    "WorkflowEngine",
    "WorkflowRouter",
    "DebugController",
    "OutputCollector",
    "StepTimeoutError",
    "WorkflowExecutionError",
    "StepExecutionError",
]
