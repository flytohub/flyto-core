"""
Data Lineage Tracking System

DEPRECATED: This file is maintained for backwards compatibility.
Please import from core.engine.lineage instead:

    from core.engine.lineage import (
        DataSource,
        TrackedValue,
        LineageContext,
        create_lineage_context,
    )

All functionality has been split into:
- core/engine/lineage/models.py - DataSource, TrackedValue
- core/engine/lineage/context.py - LineageContext
- core/engine/lineage/analysis.py - Analysis functions

Original design principles:
- Zero coupling: Works with any data type
- Transparent: Can be used without changing existing code
- Serializable: Full lineage can be persisted and restored
"""

# Re-export for backwards compatibility
from .lineage import (
    # Models
    DataSource,
    TrackedValue,
    # Context
    LineageContext,
    # Analysis
    build_data_graph,
    find_dependent_variables,
    trace_data_flow,
    # Factory
    create_lineage_context,
    wrap_with_lineage,
)

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
