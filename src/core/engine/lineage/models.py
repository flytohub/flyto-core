"""
Lineage Data Models

Data classes for tracking data sources and values.
"""

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

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
