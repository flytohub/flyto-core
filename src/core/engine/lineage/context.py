"""
Lineage Context

Execution context with data lineage tracking.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import DataSource, TrackedValue

logger = logging.getLogger(__name__)


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
