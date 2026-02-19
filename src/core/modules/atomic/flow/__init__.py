"""
Flow Control Modules

Provides branching, looping, jump control, parallel execution,
subflow references, triggers, breakpoints, batch processing,
container execution, and resilience patterns for workflows.

Workflow Spec v1.1 compliant.
"""

from .branch import BranchModule
from .switch import SwitchModule
from .goto import GotoModule
from .loop import LoopModule
from .container import ContainerModule
from .merge import MergeModule
from .fork import ForkModule
from .join import JoinModule
from .subflow_ref import SubflowModule
from .invoke import InvokeWorkflow
from .trigger import TriggerModule
from .start import StartModule
from .end import EndModule
from .breakpoint import BreakpointModule
from .error_handle import ErrorHandleModule
from .error_workflow_trigger import ErrorWorkflowTriggerModule
from .parallel import ParallelModule
from .batch import BatchModule
from .retry import RetryModule
from .rate_limit import RateLimitModule
from .circuit_breaker import CircuitBreakerModule
from .debounce import DebounceModule
from .throttle import ThrottleModule

__all__ = [
    # Conditional branching
    'BranchModule',
    'SwitchModule',
    # Loop control
    'GotoModule',
    'LoopModule',
    # Container/Subflow
    'ContainerModule',
    'SubflowModule',
    'InvokeWorkflow',
    # Parallel execution
    'MergeModule',
    'ForkModule',
    'JoinModule',
    'ParallelModule',
    # Batch processing
    'BatchModule',
    # Resilience patterns
    'RetryModule',
    'RateLimitModule',
    'CircuitBreakerModule',
    # Timing control
    'DebounceModule',
    'ThrottleModule',
    # Entry/Exit points
    'TriggerModule',
    'StartModule',
    'EndModule',
    # Human-in-the-loop
    'BreakpointModule',
    # Error handling
    'ErrorHandleModule',
    'ErrorWorkflowTriggerModule',
]
