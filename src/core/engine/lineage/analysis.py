"""
Lineage Analysis Functions

Functions for analyzing data flow and dependencies.
"""

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .context import LineageContext


def trace_data_flow(
    context: "LineageContext",
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
    context: "LineageContext",
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
    context: "LineageContext",
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
