"""
Data Lineage Tracking Package

Tracks the origin and transformation of data through workflow execution.
Each value can be traced back to its source step and output port.

This is a capability n8n lacks - full data provenance tracking.

Design principles:
- Zero coupling: Works with any data type
- Transparent: Can be used without changing existing code
- Serializable: Full lineage can be persisted and restored
"""

from datetime import datetime
from typing import Any, Dict, Optional

from .models import DataSource, TrackedValue
from .context import LineageContext
from .analysis import (
    build_data_graph,
    find_dependent_variables,
    trace_data_flow,
)


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


__all__ = [
    # Models
    "DataSource",
    "TrackedValue",
    # Context
    "LineageContext",
    # Analysis
    "build_data_graph",
    "find_dependent_variables",
    "trace_data_flow",
    # Factory
    "create_lineage_context",
    "wrap_with_lineage",
]
