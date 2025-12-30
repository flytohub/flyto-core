"""
Loop / ForEach Module Package

Provides iteration functionality for workflows:
- Edge-based loops (Workflow Spec v1.2)
- Nested loops with internal sub-step execution
"""

from .module import LoopModule, LOOP_CONFIG, FOREACH_CONFIG
from .edge_mode import execute_edge_mode, ITERATION_PREFIX
from .nested_mode import execute_nested_mode
from .resolver import resolve_params, resolve_variable

__all__ = [
    "LoopModule",
    "LOOP_CONFIG",
    "FOREACH_CONFIG",
    "execute_edge_mode",
    "execute_nested_mode",
    "resolve_params",
    "resolve_variable",
    "ITERATION_PREFIX",
]
