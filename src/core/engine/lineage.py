"""
Data Lineage Tracking System

Tracks the origin and transformation of data through workflow execution.
Each value can be traced back to its source step and output port.

This is a capability n8n lacks - full data provenance tracking.

Design principles:
- Zero coupling: Works with any data type
- Transparent: Can be used without changing existing code
- Serializable: Full lineage can be persisted and restored
"""

import copy
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')


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


class LineageContext:
    """
    Execution context with data lineage tracking.

    Extends standard dict-like context to track where each value came from.

    Usage:
        ctx = LineageContext(execution_id="exec_123")

        # Set value with lineage
        ctx.set_with_lineage(
            key="user",
            value={"name": "John"},
            step_id="fetch_user",
            output_port="result"
        )

        # Get value with lineage info
        tracked = ctx.get_tracked("user")
        print(tracked.source)  # fetch_user.result

        # Get raw value (for backward compatibility)
        raw = ctx.get("user")  # {"name": "John"}
    """

    def __init__(
        self,
        execution_id: str,
        initial_values: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize lineage context.

        Args:
            execution_id: Unique execution identifier
            initial_values: Optional initial values (no lineage)
        """
        self.execution_id = execution_id
        self._values: Dict[str, TrackedValue] = {}
        self._raw_cache: Dict[str, Any] = {}

        if initial_values:
            for key, value in initial_values.items():
                self.set(key, value)

    def set(
        self,
        key: str,
        value: Any,
        step_id: Optional[str] = None,
        output_port: str = "output",
        item_index: Optional[int] = None,
    ) -> None:
        """
        Set a value with optional lineage tracking.

        Args:
            key: Variable name
            value: The value to store
            step_id: Source step ID (enables lineage tracking)
            output_port: Source output port
            item_index: Index if from array
        """
        if isinstance(value, TrackedValue):
            self._values[key] = value
            self._raw_cache[key] = value.data
        elif step_id:
            source = DataSource(
                step_id=step_id,
                output_port=output_port,
                item_index=item_index,
                timestamp=datetime.now(),
            )
            self._values[key] = TrackedValue(data=value, source=source)
            self._raw_cache[key] = value
        else:
            # No lineage tracking for values without step_id
            self._values[key] = TrackedValue(data=value)
            self._raw_cache[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get raw value (backward compatible)"""
        return self._raw_cache.get(key, default)

    def get_tracked(self, key: str) -> Optional[TrackedValue]:
        """Get value with lineage information"""
        return self._values.get(key)

    def get_lineage(self, key: str) -> List[str]:
        """Get lineage chain for a value"""
        tracked = self._values.get(key)
        if tracked:
            return tracked.get_full_lineage()
        return []

    def get_origin(self, key: str) -> Optional[DataSource]:
        """Get original source of a value"""
        tracked = self._values.get(key)
        if tracked:
            return tracked.get_origin()
        return None

    def keys(self) -> List[str]:
        """Get all variable names"""
        return list(self._values.keys())

    def items(self) -> List[tuple]:
        """Get all key-value pairs (raw values)"""
        return list(self._raw_cache.items())

    def tracked_items(self) -> List[tuple]:
        """Get all key-TrackedValue pairs"""
        return list(self._values.items())

    def to_dict(self) -> Dict[str, Any]:
        """Get raw values as dict (backward compatible)"""
        return dict(self._raw_cache)

    def to_tracked_dict(self) -> Dict[str, Dict[str, Any]]:
        """Get all values with lineage as dict"""
        return {
            key: tracked.to_dict()
            for key, tracked in self._values.items()
        }

    def copy(self) -> "LineageContext":
        """Create a deep copy of the context"""
        new_ctx = LineageContext(execution_id=self.execution_id)
        for key, tracked in self._values.items():
            new_ctx._values[key] = TrackedValue(
                data=copy.deepcopy(tracked.data),
                source=tracked.source,
                lineage=list(tracked.lineage),
            )
            new_ctx._raw_cache[key] = copy.deepcopy(tracked.data)
        return new_ctx

    def merge(self, other: "LineageContext") -> None:
        """Merge another context into this one"""
        for key, tracked in other._values.items():
            self._values[key] = tracked
            self._raw_cache[key] = tracked.data

    def update(self, values: Dict[str, Any]) -> None:
        """Update with raw values (no lineage)"""
        for key, value in values.items():
            self.set(key, value)

    def record_step_output(
        self,
        step_id: str,
        outputs: Dict[str, Any],
    ) -> None:
        """
        Record all outputs from a step with lineage.

        Args:
            step_id: The step that produced these outputs
            outputs: Dict of output_port -> value
        """
        for port, value in outputs.items():
            key = f"{step_id}.{port}"
            self.set(key, value, step_id=step_id, output_port=port)

            # Also set as step_id for convenience
            if port == "result" or port == "output":
                self.set(step_id, value, step_id=step_id, output_port=port)

    def get_step_outputs(self, step_id: str) -> Dict[str, Any]:
        """Get all outputs from a specific step"""
        prefix = f"{step_id}."
        return {
            key[len(prefix):]: value
            for key, value in self._raw_cache.items()
            if key.startswith(prefix)
        }

    def find_by_origin(self, step_id: str) -> List[str]:
        """Find all variables that originated from a step"""
        result = []
        for key, tracked in self._values.items():
            origin = tracked.get_origin()
            if origin and origin.step_id == step_id:
                result.append(key)
        return result

    def __contains__(self, key: str) -> bool:
        return key in self._values

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"LineageContext(execution_id={self.execution_id}, vars={len(self._values)})"


# =============================================================================
# Lineage Analysis Functions
# =============================================================================

def trace_data_flow(
    context: LineageContext,
    target_key: str,
) -> Dict[str, Any]:
    """
    Trace the complete data flow for a variable.

    Args:
        context: LineageContext to analyze
        target_key: Variable to trace

    Returns:
        Dict with lineage analysis
    """
    tracked = context.get_tracked(target_key)
    if not tracked:
        return {"error": f"Variable '{target_key}' not found"}

    return {
        "variable": target_key,
        "current_value": tracked.data,
        "origin": str(tracked.get_origin()) if tracked.get_origin() else None,
        "lineage_chain": tracked.get_full_lineage(),
        "transformation_count": len(tracked.lineage),
    }


def find_dependent_variables(
    context: LineageContext,
    step_id: str,
) -> List[Dict[str, Any]]:
    """
    Find all variables that depend on a step's output.

    Useful for impact analysis when a step changes.

    Args:
        context: LineageContext to analyze
        step_id: Step to find dependents for

    Returns:
        List of dependent variable info
    """
    dependents = []

    for key, tracked in context.tracked_items():
        for source in tracked.lineage:
            if source.step_id == step_id:
                dependents.append({
                    "variable": key,
                    "dependency_type": source.output_port,
                    "transformation": source.transformation,
                })
                break

    return dependents


def build_data_graph(
    context: LineageContext,
) -> Dict[str, Any]:
    """
    Build a graph representation of data flow.

    Returns:
        Dict with nodes (variables) and edges (data flow)
    """
    nodes = []
    edges = []
    seen_steps = set()

    for key, tracked in context.tracked_items():
        nodes.append({
            "id": key,
            "type": "variable",
            "value_type": type(tracked.data).__name__,
        })

        for i, source in enumerate(tracked.lineage):
            if source.step_id not in seen_steps:
                nodes.append({
                    "id": source.step_id,
                    "type": "step",
                })
                seen_steps.add(source.step_id)

            if i == 0:
                # First in lineage - edge from step to variable
                edges.append({
                    "from": source.step_id,
                    "to": key,
                    "port": source.output_port,
                    "transformation": source.transformation,
                })
            else:
                # Transformation chain
                prev_source = tracked.lineage[i - 1]
                edges.append({
                    "from": f"{prev_source.step_id}.{prev_source.output_port}",
                    "to": f"{source.step_id}.{source.output_port}",
                    "transformation": source.transformation,
                })

    return {
        "nodes": nodes,
        "edges": edges,
    }


# =============================================================================
# Factory Functions
# =============================================================================

def create_lineage_context(
    execution_id: str,
    initial_values: Optional[Dict[str, Any]] = None,
) -> LineageContext:
    """
    Create a new lineage context.

    Args:
        execution_id: Unique execution identifier
        initial_values: Optional initial values

    Returns:
        Configured LineageContext
    """
    return LineageContext(
        execution_id=execution_id,
        initial_values=initial_values,
    )


def wrap_with_lineage(
    value: Any,
    step_id: str,
    output_port: str = "output",
) -> TrackedValue:
    """
    Wrap a value with lineage tracking.

    Args:
        value: Value to wrap
        step_id: Source step ID
        output_port: Source output port

    Returns:
        TrackedValue with lineage
    """
    source = DataSource(
        step_id=step_id,
        output_port=output_port,
        timestamp=datetime.now(),
    )
    return TrackedValue(data=value, source=source)
