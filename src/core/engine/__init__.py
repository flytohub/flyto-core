"""
Workflow Engine Package

This package provides workflow execution capabilities with:
- Variable resolution
- Step execution
- Hooks and evidence collection
- Data lineage tracking
- Replay and breakpoint support
"""

# Core exceptions - always available
from .exceptions import (
    StepTimeoutError,
    WorkflowExecutionError,
    StepExecutionError,
    FlowControlError,
    VariableResolutionError,
)

# Flow control utilities - always available
from .flow_control import (
    FLOW_CONTROL_MODULES,
    is_flow_control_module,
    is_flow_jumping_module,
    is_iteration_module,
    normalize_module_id,
)

# Variable resolver - always available
from .variable_resolver import VariableResolver

# Execution Trace (ITEM_PIPELINE_SPEC.md Section 8)
from .trace import (
    ExecutionTrace,
    StepTrace,
    ItemTrace,
    TraceCollector,
    TraceStatus,
    TraceError,
    StepInput,
    StepOutput,
)

# Optional imports - may not exist in all configurations
WorkflowEngine = None
StepExecutor = None
create_step_executor = None

try:
    from .workflow.engine import WorkflowEngine
except ImportError:
    pass

try:
    from .step_executor import StepExecutor, create_step_executor
except ImportError:
    pass

# Hooks - optional
ExecutorHooks = None
HookContext = None
HookResult = None
HookAction = None
NullHooks = None
LoggingHooks = None
MetricsHooks = None
CompositeHooks = None
create_hooks = None

try:
    from .hooks import (
        ExecutorHooks,
        HookContext,
        HookResult,
        HookAction,
        NullHooks,
        LoggingHooks,
        MetricsHooks,
        CompositeHooks,
        create_hooks,
    )
except ImportError:
    pass

# Evidence - optional
StepEvidence = None
EvidenceStore = None
StepEvidenceHook = None
EvidenceExecutorHooks = None
create_evidence_store = None
create_evidence_hook = None
create_evidence_executor_hooks = None

try:
    from .evidence import (
        StepEvidence,
        EvidenceStore,
        StepEvidenceHook,
        EvidenceExecutorHooks,
        create_evidence_store,
        create_evidence_hook,
        create_evidence_executor_hooks,
    )
except ImportError:
    pass

# Lineage - optional
DataSource = None
TrackedValue = None
LineageContext = None
trace_data_flow = None
find_dependent_variables = None
build_data_graph = None
create_lineage_context = None
wrap_with_lineage = None

try:
    from .lineage import (
        DataSource,
        TrackedValue,
        LineageContext,
        trace_data_flow,
        find_dependent_variables,
        build_data_graph,
        create_lineage_context,
        wrap_with_lineage,
    )
except ImportError:
    pass

# Replay - optional
ReplayMode = None
ReplayConfig = None
ReplayResult = None
ReplayManager = None
create_replay_manager = None

try:
    from .replay import (
        ReplayMode,
        ReplayConfig,
        ReplayResult,
        ReplayManager,
        create_replay_manager,
    )
except ImportError:
    pass

# Breakpoint - optional
BreakpointStatus = None
ApprovalMode = None
BreakpointRequest = None
ApprovalResponse = None
BreakpointResult = None
BreakpointManager = None
BreakpointStore = None
BreakpointNotifier = None
InMemoryBreakpointStore = None
NullNotifier = None
get_breakpoint_manager = None
create_breakpoint_manager = None
set_global_breakpoint_manager = None

try:
    from .breakpoint import (
        BreakpointStatus,
        ApprovalMode,
        BreakpointRequest,
        ApprovalResponse,
        BreakpointResult,
        BreakpointManager,
        BreakpointStore,
        BreakpointNotifier,
        InMemoryBreakpointStore,
        NullNotifier,
        get_breakpoint_manager,
        create_breakpoint_manager,
        set_global_breakpoint_manager,
    )
except ImportError:
    pass

__all__ = [
    # Exceptions
    'StepTimeoutError',
    'WorkflowExecutionError',
    'StepExecutionError',
    'FlowControlError',
    'VariableResolutionError',
    # Flow Control
    'FLOW_CONTROL_MODULES',
    'is_flow_control_module',
    'is_flow_jumping_module',
    'is_iteration_module',
    'normalize_module_id',
    # Workflow Engine
    'WorkflowEngine',
    'VariableResolver',
    # Execution Trace
    'ExecutionTrace',
    'StepTrace',
    'ItemTrace',
    'TraceCollector',
    'TraceStatus',
    'TraceError',
    'StepInput',
    'StepOutput',
    # Step Executor
    'StepExecutor',
    'create_step_executor',
    # Hooks
    'ExecutorHooks',
    'HookContext',
    'HookResult',
    'HookAction',
    'NullHooks',
    'LoggingHooks',
    'MetricsHooks',
    'CompositeHooks',
    'create_hooks',
    # Evidence System
    'StepEvidence',
    'EvidenceStore',
    'StepEvidenceHook',
    'EvidenceExecutorHooks',
    'create_evidence_store',
    'create_evidence_hook',
    'create_evidence_executor_hooks',
    # Data Lineage
    'DataSource',
    'TrackedValue',
    'LineageContext',
    'trace_data_flow',
    'find_dependent_variables',
    'build_data_graph',
    'create_lineage_context',
    'wrap_with_lineage',
    # Replay System
    'ReplayMode',
    'ReplayConfig',
    'ReplayResult',
    'ReplayManager',
    'create_replay_manager',
    # Breakpoint System
    'BreakpointStatus',
    'ApprovalMode',
    'BreakpointRequest',
    'ApprovalResponse',
    'BreakpointResult',
    'BreakpointManager',
    'BreakpointStore',
    'BreakpointNotifier',
    'InMemoryBreakpointStore',
    'NullNotifier',
    'get_breakpoint_manager',
    'create_breakpoint_manager',
    'set_global_breakpoint_manager',
]
