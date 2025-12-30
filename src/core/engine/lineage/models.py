"""
Lineage Data Models

Data classes for tracking data sources and values.

Extended with:
- StepCategory: Classify steps into observe/evaluate/decide/act/verify
- Artifact: Evidence and products (screenshots, reports, patches)
- Decision: AI decision with confidence and evidence
- Step: A module execution with category and artifacts
- Edge: Produces/consumes relationships
- Run: Complete execution context
"""

import copy
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

T = TypeVar('T')


# =============================================================================
# Step Categories (Swimlane Classification)
# =============================================================================

class StepCategory(str, Enum):
    """
    Step category for swimlane visualization.

    Maps to the 4-lane view: Observe -> Evaluate -> Decide -> Act/Verify
    """
    OBSERVE = "observe"      # Capture data: screenshot, API response, read file
    EVALUATE = "evaluate"    # Analyze/score: UI evaluation, validation
    DECIDE = "decide"        # AI decision: need_fix, pass, fail
    ACT = "act"              # Execute action: click, type, write file
    VERIFY = "verify"        # Confirm result: re-test, compare


# =============================================================================
# Artifact Types
# =============================================================================

class ArtifactType(str, Enum):
    """Types of artifacts that can be produced"""
    SCREENSHOT = "screenshot"
    REPORT = "report"
    DECISION = "decision"
    PATCH = "patch"
    DIFF = "diff"
    LOG = "log"
    DATA = "data"


@dataclass
class Artifact:
    """
    Evidence or product from a step.

    Examples:
    - Screenshot of a page
    - UI evaluation report
    - AI decision record
    - Code patch
    - Diff comparison
    """
    id: str
    type: ArtifactType
    name: str
    produced_by: str  # step_id
    timestamp: datetime = field(default_factory=datetime.now)
    path: Optional[str] = None  # File path if stored externally
    data: Optional[Dict[str, Any]] = None  # Inline data
    mime_type: Optional[str] = None

    def __post_init__(self):
        if not self.id:
            self.id = f"artifact_{uuid.uuid4().hex[:8]}"
        if isinstance(self.type, str):
            self.type = ArtifactType(self.type)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "produced_by": self.produced_by,
            "timestamp": self.timestamp.isoformat(),
            "path": self.path,
            "data": self.data,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Artifact":
        """Create from dictionary"""
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


# =============================================================================
# Decision Node (AI Explainability)
# =============================================================================

@dataclass
class Decision:
    """
    AI decision with explainability.

    Key differentiator - shows WHY AI made a decision.
    """
    decision: str  # e.g., "need_fix", "pass", "fail", "retry"
    reason: str    # Human-readable explanation
    confidence: float  # 0.0 to 1.0
    evidence: List[str] = field(default_factory=list)  # artifact_ids
    alternatives: Optional[List[Dict[str, Any]]] = None  # Other considered options
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "alternatives": self.alternatives,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Decision":
        """Create from dictionary"""
        return cls(**data)


# =============================================================================
# Step (Module Execution Record)
# =============================================================================

@dataclass
class Step:
    """
    A single module execution within a run.

    Tracks inputs, outputs, timing, and produced artifacts.
    """
    id: str
    module_id: str
    category: StepCategory
    name: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)  # artifact_ids
    decision: Optional[Decision] = None  # For DECIDE steps
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    error: Optional[str] = None
    parent_step_id: Optional[str] = None  # For nested steps (loops)
    iteration: Optional[int] = None  # Loop iteration index

    def __post_init__(self):
        if not self.id:
            self.id = f"step_{uuid.uuid4().hex[:8]}"
        if isinstance(self.category, str):
            self.category = StepCategory(self.category)

    @property
    def duration_ms(self) -> Optional[float]:
        """Get step duration in milliseconds"""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() * 1000
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "module_id": self.module_id,
            "category": self.category.value,
            "name": self.name,
            "inputs": self._safe_serialize(self.inputs),
            "outputs": self._safe_serialize(self.outputs),
            "artifacts": self.artifacts,
            "decision": self.decision.to_dict() if self.decision else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "parent_step_id": self.parent_step_id,
            "iteration": self.iteration,
        }

    def _safe_serialize(self, data: Any) -> Any:
        """Safely serialize data for JSON"""
        if isinstance(data, (str, int, float, bool, type(None))):
            return data
        if isinstance(data, (list, tuple)):
            return [self._safe_serialize(item) for item in data]
        if isinstance(data, dict):
            return {k: self._safe_serialize(v) for k, v in data.items()}
        if isinstance(data, datetime):
            return data.isoformat()
        if isinstance(data, bytes):
            return f"<binary:{len(data)}bytes>"
        if isinstance(data, Enum):
            return data.value
        return str(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        """Create from dictionary"""
        if isinstance(data.get("started_at"), str):
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if isinstance(data.get("ended_at"), str):
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])
        if data.get("decision"):
            data["decision"] = Decision.from_dict(data["decision"])
        # Remove computed field
        data.pop("duration_ms", None)
        return cls(**data)


# =============================================================================
# Edge (Data Flow Relationship)
# =============================================================================

class EdgeType(str, Enum):
    """Edge types for data flow graph"""
    PRODUCES = "produces"    # Step produces Artifact
    CONSUMES = "consumes"    # Step consumes Artifact


@dataclass
class Edge:
    """
    Relationship between steps and artifacts.

    Only two types: produces and consumes.
    """
    source: str  # step_id or artifact_id
    target: str  # artifact_id or step_id
    edge_type: EdgeType

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "source": self.source,
            "target": self.target,
            "type": self.edge_type.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Edge":
        """Create from dictionary"""
        return cls(
            source=data["source"],
            target=data["target"],
            edge_type=EdgeType(data["type"]),
        )


# =============================================================================
# Run (Complete Execution Context)
# =============================================================================

@dataclass
class Run:
    """
    A complete workflow execution.

    Contains all steps, artifacts, and edges for a single run.
    """
    id: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    steps: List[Step] = field(default_factory=list)
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = f"run_{uuid.uuid4().hex[:8]}"

    @property
    def duration_ms(self) -> Optional[float]:
        """Get run duration in milliseconds"""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds() * 1000
        return None

    def get_steps_by_category(self, category: StepCategory) -> List[Step]:
        """Get all steps of a specific category"""
        return [s for s in self.steps if s.category == category]

    def get_decision_steps(self) -> List[Step]:
        """Get all steps that contain decisions"""
        return [s for s in self.steps if s.decision is not None]

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Get artifact by ID"""
        return self.artifacts.get(artifact_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "steps": [s.to_dict() for s in self.steps],
            "artifacts": {k: v.to_dict() for k, v in self.artifacts.items()},
            "edges": [e.to_dict() for e in self.edges],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Run":
        """Create from dictionary"""
        if isinstance(data.get("started_at"), str):
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if isinstance(data.get("ended_at"), str):
            data["ended_at"] = datetime.fromisoformat(data["ended_at"])
        data["steps"] = [Step.from_dict(s) for s in data.get("steps", [])]
        data["artifacts"] = {
            k: Artifact.from_dict(v)
            for k, v in data.get("artifacts", {}).items()
        }
        data["edges"] = [Edge.from_dict(e) for e in data.get("edges", [])]
        # Remove computed field
        data.pop("duration_ms", None)
        return cls(**data)


# =============================================================================
# Original Models (DataSource, TrackedValue) - Unchanged
# =============================================================================


@dataclass
class DataSource:
    """
    Records where a piece of data originated.

    Attributes:
        step_id: The step that produced this data
        output_port: The output port name (e.g., 'success', 'result')
        item_index: Index if data came from an array
        timestamp: When the data was produced
        transformation: Optional description of how data was transformed
    """
    step_id: str
    output_port: str = "output"
    item_index: Optional[int] = None
    timestamp: Optional[datetime] = None
    transformation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        if data.get('timestamp'):
            data['timestamp'] = data['timestamp'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataSource":
        """Create from dictionary"""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

    def __str__(self) -> str:
        """Human-readable representation"""
        parts = [f"{self.step_id}.{self.output_port}"]
        if self.item_index is not None:
            parts[0] += f"[{self.item_index}]"
        if self.transformation:
            parts.append(f"({self.transformation})")
        return " ".join(parts)


@dataclass
class TrackedValue(Generic[T]):
    """
    A value with its data lineage attached.

    Wraps any value and tracks where it came from and how it was transformed.

    Usage:
        # Create tracked value from step output
        result = TrackedValue(
            data={"name": "John"},
            source=DataSource(step_id="fetch_user", output_port="result")
        )

        # Access the actual data
        print(result.data)  # {"name": "John"}

        # Check lineage
        print(result.source)  # fetch_user.result

        # Chain transformations
        transformed = result.derive(
            data=result.data["name"].upper(),
            transformation="uppercase name"
        )
    """
    data: T
    source: Optional[DataSource] = None
    lineage: List[DataSource] = field(default_factory=list)

    def __post_init__(self):
        """Initialize lineage from source if provided"""
        if self.source and not self.lineage:
            self.lineage = [self.source]

    def derive(
        self,
        data: Any,
        transformation: str,
        output_port: str = "derived",
    ) -> "TrackedValue":
        """
        Create a new TrackedValue derived from this one.

        Args:
            data: The new data value
            transformation: Description of the transformation
            output_port: Output port name for the derived value

        Returns:
            New TrackedValue with extended lineage
        """
        new_source = DataSource(
            step_id=self.source.step_id if self.source else "unknown",
            output_port=output_port,
            timestamp=datetime.now(),
            transformation=transformation,
        )

        return TrackedValue(
            data=data,
            source=new_source,
            lineage=self.lineage + [new_source],
        )

    def get_origin(self) -> Optional[DataSource]:
        """Get the original source of this data"""
        if self.lineage:
            return self.lineage[0]
        return self.source

    def get_full_lineage(self) -> List[str]:
        """Get human-readable lineage chain"""
        return [str(source) for source in self.lineage]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "data": self._serialize_data(self.data),
            "source": self.source.to_dict() if self.source else None,
            "lineage": [s.to_dict() for s in self.lineage],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackedValue":
        """Create from dictionary"""
        source = None
        if data.get("source"):
            source = DataSource.from_dict(data["source"])

        lineage = [
            DataSource.from_dict(s)
            for s in data.get("lineage", [])
        ]

        return cls(
            data=data.get("data"),
            source=source,
            lineage=lineage,
        )

    def _serialize_data(self, data: Any) -> Any:
        """Serialize data for JSON storage"""
        if isinstance(data, (str, int, float, bool, type(None))):
            return data
        if isinstance(data, (list, tuple)):
            return [self._serialize_data(item) for item in data]
        if isinstance(data, dict):
            return {k: self._serialize_data(v) for k, v in data.items()}
        if isinstance(data, datetime):
            return data.isoformat()
        if isinstance(data, bytes):
            return f"<binary:{len(data)}bytes>"
        return str(data)

    def unwrap(self) -> T:
        """Get the underlying data value"""
        return self.data

    def __repr__(self) -> str:
        origin = self.get_origin()
        origin_str = str(origin) if origin else "unknown"
        return f"TrackedValue({type(self.data).__name__}, from={origin_str})"
