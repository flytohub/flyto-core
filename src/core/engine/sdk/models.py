"""
SDK Data Models

Defines all data structures for the Engine SDK interface.
These models are the contract between flyto-core and flyto-cloud.

Version: 1.0.0
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union


# =============================================================================
# Enums
# =============================================================================

class IntrospectionMode(str, Enum):
    """Mode for variable catalog generation"""
    EDIT = "edit"      # Based on graph structure only
    RUNTIME = "runtime"  # With execution context


class VarSource(str, Enum):
    """Source of variable type/example information"""
    SCHEMA = "schema"  # Inferred from module schema
    TRACE = "trace"    # From actual execution trace


class VarAvailability(str, Enum):
    """When a variable is available"""
    EDIT = "edit"
    RUNTIME = "runtime"
    BOTH = "both"


class EventType(str, Enum):
    """Engine event types for streaming"""
    ENGINE_START = "engine_start"
    NODE_START = "node_start"
    NODE_END = "node_end"
    LOG = "log"
    PARTIAL_OUTPUT = "partial_output"
    ERROR = "error"
    ENGINE_END = "engine_end"


class ExecutionStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContextLayer(str, Enum):
    """Context security layers"""
    PUBLIC = "public"
    PRIVATE = "private"
    SECRETS = "secrets"


class ResolutionMode(str, Enum):
    """Variable resolution output mode"""
    RAW = "raw"        # Return original type
    STRING = "string"  # Stringify for template insertion


# =============================================================================
# Variable Catalog Models
# =============================================================================

@dataclass
class VarInfo:
    """Single variable/field information"""
    path: str
    var_type: str  # string, number, boolean, object, array, any
    description: str = ""
    example: Any = None
    origin_node: Optional[str] = None
    is_available: bool = True
    source: VarSource = VarSource.SCHEMA
    confidence: float = 1.0
    availability: VarAvailability = VarAvailability.BOTH


@dataclass
class PortVarInfo:
    """Variable info for a specific port"""
    port_id: str
    var_type: str
    description: str = ""
    example: Any = None
    fields: Dict[str, VarInfo] = field(default_factory=dict)


@dataclass
class NodeVarInfo:
    """Variable info for a specific node"""
    node_id: str
    node_type: str  # module_id
    is_reachable: bool = True
    ports: Dict[str, PortVarInfo] = field(default_factory=dict)
    # Branch tracking
    is_conditional: bool = False  # True if downstream of a branch/switch
    branch_source: Optional[str] = None  # The branch/switch node ID
    branch_port: Optional[str] = None  # The port taken (true/false/case_X)


@dataclass
class VarCatalog:
    """Available variables for a node"""
    schema_version: str = "1.0"
    mode: IntrospectionMode = IntrospectionMode.EDIT
    node_id: str = ""

    # Input ports: {{input}} = {{inputs.main}}
    inputs: Dict[str, PortVarInfo] = field(default_factory=dict)

    # Upstream nodes: {{node_id.port.field}}
    nodes: Dict[str, NodeVarInfo] = field(default_factory=dict)

    # Globals: {{global.var}}
    globals: Dict[str, VarInfo] = field(default_factory=dict)

    # Parameters: {{params.name}}
    params: Dict[str, VarInfo] = field(default_factory=dict)

    # Environment (filtered): {{env.VAR}}
    env: Dict[str, VarInfo] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "node_id": self.node_id,
            "inputs": {k: self._port_to_dict(v) for k, v in self.inputs.items()},
            "nodes": {k: self._node_to_dict(v) for k, v in self.nodes.items()},
            "globals": {k: self._var_to_dict(v) for k, v in self.globals.items()},
            "params": {k: self._var_to_dict(v) for k, v in self.params.items()},
            "env": {k: self._var_to_dict(v) for k, v in self.env.items()},
        }

    def _var_to_dict(self, v: VarInfo) -> Dict[str, Any]:
        return {
            "path": v.path,
            "type": v.var_type,
            "description": v.description,
            "example": v.example,
            "origin_node": v.origin_node,
            "is_available": v.is_available,
            "source": v.source.value,
            "confidence": v.confidence,
            "availability": v.availability.value,
        }

    def _port_to_dict(self, p: PortVarInfo) -> Dict[str, Any]:
        return {
            "port_id": p.port_id,
            "type": p.var_type,
            "description": p.description,
            "example": p.example,
            "fields": {k: self._var_to_dict(v) for k, v in p.fields.items()},
        }

    def _node_to_dict(self, n: NodeVarInfo) -> Dict[str, Any]:
        result = {
            "node_id": n.node_id,
            "node_type": n.node_type,
            "is_reachable": n.is_reachable,
            "ports": {k: self._port_to_dict(v) for k, v in n.ports.items()},
        }
        # Include branch info if conditional
        if n.is_conditional:
            result["is_conditional"] = True
            result["branch_source"] = n.branch_source
            result["branch_port"] = n.branch_port
        return result


# =============================================================================
# Engine Event Models
# =============================================================================

@dataclass
class EngineEvent:
    """Event emitted during workflow execution"""
    event_type: EventType
    timestamp: float
    execution_id: str
    node_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type.value,
            "ts": self.timestamp,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "payload": self.payload,
        }


# =============================================================================
# Execution Models
# =============================================================================

@dataclass
class NodeSnapshot:
    """Snapshot of node input/output for debugging"""
    node_id: str
    module_id: str
    status: ExecutionStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: float = 0.0
    input_snapshot: Dict[str, Any] = field(default_factory=dict)
    output_snapshot: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class ExecutionTrace:
    """Complete execution trace for debugging"""
    execution_id: str
    workflow_id: str
    status: ExecutionStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: float = 0.0
    nodes: List[NodeSnapshot] = field(default_factory=list)
    final_output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "nodes": [self._node_to_dict(n) for n in self.nodes],
            "final_output": self.final_output,
            "error": self.error,
        }

    def _node_to_dict(self, n: NodeSnapshot) -> Dict[str, Any]:
        return {
            "node_id": n.node_id,
            "module_id": n.module_id,
            "status": n.status.value,
            "started_at": n.started_at.isoformat() if n.started_at else None,
            "ended_at": n.ended_at.isoformat() if n.ended_at else None,
            "duration_ms": n.duration_ms,
            "input_snapshot": n.input_snapshot,
            "output_snapshot": n.output_snapshot,
            "error": n.error,
            "error_type": n.error_type,
        }


# =============================================================================
# Validation Models
# =============================================================================

@dataclass
class ValidationError:
    """Single validation error"""
    code: str
    path: str
    message: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationWarning:
    """Single validation warning"""
    code: str
    path: str
    message: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of workflow validation"""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationWarning] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [
                {"code": e.code, "path": e.path, "message": e.message, "meta": e.meta}
                for e in self.errors
            ],
            "warnings": [
                {"code": w.code, "path": w.path, "message": w.message, "meta": w.meta}
                for w in self.warnings
            ],
        }


# =============================================================================
# Expression Models
# =============================================================================

@dataclass
class ExpressionToken:
    """Token from parsed expression"""
    token_type: Literal["identifier", "index", "quoted_key"]
    value: str
    start: int
    end: int


@dataclass
class ParsedExpression:
    """Parsed variable expression"""
    raw: str
    is_valid: bool
    tokens: List[ExpressionToken] = field(default_factory=list)
    error: Optional[str] = None
    resolved_type: Optional[str] = None


@dataclass
class AutocompleteItem:
    """Single autocomplete suggestion"""
    path: str
    display: str
    var_type: str
    description: str = ""
    insert_text: str = ""
    score: float = 1.0


@dataclass
class AutocompleteResult:
    """Autocomplete suggestions"""
    prefix: str
    items: List[AutocompleteItem] = field(default_factory=list)


# =============================================================================
# Execution Request/Response
# =============================================================================

@dataclass
class ExecutionOptions:
    """Options for workflow execution"""
    timeout_ms: Optional[int] = None
    max_parallel: int = 10
    step_mode: bool = False
    breakpoints: List[str] = field(default_factory=list)
    enable_trace: bool = True
    stream_events: bool = False


@dataclass
class ExecutionResult:
    """Result of workflow execution"""
    ok: bool
    execution_id: str
    status: ExecutionStatus
    outputs: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None
    trace: Optional[ExecutionTrace] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "ok": self.ok,
            "execution_id": self.execution_id,
            "status": self.status.value,
            "outputs": self.outputs,
            "variables": self.variables,
            "error": self.error,
            "error_code": self.error_code,
        }
        if self.trace:
            result["trace"] = self.trace.to_dict()
        return result
