"""
Workflow Validation API

Validates entire workflows.
Used by flyto-cloud before save/execute.
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field

from .errors import ErrorCode
from .connection import validate_connection


@dataclass
class WorkflowError:
    """A single workflow validation error"""
    code: str
    message: str
    path: str  # e.g., 'nodes[n1]', 'edges[e1]'
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Result of workflow validation"""
    valid: bool
    errors: List[WorkflowError] = field(default_factory=list)
    warnings: List[WorkflowError] = field(default_factory=list)


def validate_workflow(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> WorkflowResult:
    """
    Validate entire workflow.

    Checks:
    - All edges are valid connections
    - No orphan nodes (except start nodes)
    - Start nodes are valid
    - Required parameters are set
    - No cycles (except in loop modules)

    Args:
        nodes: List of node definitions
            [{'id': 'n1', 'module_id': 'browser.launch', 'params': {...}}, ...]
        edges: List of edge definitions
            [{'id': 'e1', 'source': 'n1', 'target': 'n2'}, ...]

    Returns:
        WorkflowResult with valid=True/False and error/warning lists
    """
    errors: List[WorkflowError] = []
    warnings: List[WorkflowError] = []

    # Build lookup maps
    node_map = {n['id']: n for n in nodes}
    node_ids = set(node_map.keys())

    # Track connections
    outgoing: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    incoming: Dict[str, List[str]] = {nid: [] for nid in node_ids}

    # Validate each edge
    for i, edge in enumerate(edges):
        source_id = edge.get('source')
        target_id = edge.get('target')
        edge_id = edge.get('id', f'edge_{i}')

        # Check nodes exist
        if source_id not in node_ids:
            errors.append(WorkflowError(
                code=ErrorCode.MODULE_NOT_FOUND,
                message=f'Source node not found: {source_id}',
                path=f'edges[{edge_id}]',
                meta={'node_id': source_id}
            ))
            continue

        if target_id not in node_ids:
            errors.append(WorkflowError(
                code=ErrorCode.MODULE_NOT_FOUND,
                message=f'Target node not found: {target_id}',
                path=f'edges[{edge_id}]',
                meta={'node_id': target_id}
            ))
            continue

        # Validate connection
        source_module = node_map[source_id].get('module_id', '')
        target_module = node_map[target_id].get('module_id', '')

        result = validate_connection(source_module, target_module)
        if not result.valid:
            errors.append(WorkflowError(
                code=result.error_code or ErrorCode.INCOMPATIBLE_MODULES,
                message=result.error_message or 'Invalid connection',
                path=f'edges[{edge_id}]',
                meta=result.meta
            ))

        # Track connections
        outgoing[source_id].append(target_id)
        incoming[target_id].append(source_id)

    # Find start nodes (nodes with no incoming edges)
    start_nodes = [nid for nid in node_ids if not incoming[nid]]

    # Validate start nodes
    start_errors = validate_start(nodes, edges)
    errors.extend(start_errors)

    # Check for orphan nodes (no connections at all, except single-node workflows)
    if len(nodes) > 1:
        for nid in node_ids:
            if not outgoing[nid] and not incoming[nid]:
                warnings.append(WorkflowError(
                    code=ErrorCode.ORPHAN_NODE,
                    message=f'Node {nid} is not connected to any other nodes',
                    path=f'nodes[{nid}]',
                    meta={'node_id': nid}
                ))

    # Check for cycles (simple DFS)
    cycle_errors = _detect_cycles(node_ids, outgoing, node_map)
    errors.extend(cycle_errors)

    return WorkflowResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_start(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[WorkflowError]:
    """
    Validate start nodes only.

    Args:
        nodes: List of node definitions
        edges: List of edge definitions

    Returns:
        List of errors (empty if valid)
    """
    errors: List[WorkflowError] = []

    if not nodes:
        return errors

    # Build incoming map
    node_ids = {n['id'] for n in nodes}
    incoming: Dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in edges:
        target_id = edge.get('target')
        if target_id in incoming:
            incoming[target_id] += 1

    # Find start nodes
    start_node_ids = [nid for nid in node_ids if incoming[nid] == 0]

    if not start_node_ids and len(nodes) > 1:
        errors.append(WorkflowError(
            code=ErrorCode.NO_START_NODE,
            message='Workflow has no start node',
            path='workflow',
            meta={}
        ))
        return errors

    # Validate each start node
    from ..modules.registry import ModuleRegistry

    for node in nodes:
        if node['id'] not in start_node_ids:
            continue

        module_id = node.get('module_id', '')
        meta = ModuleRegistry.get_metadata(module_id)

        if not meta:
            errors.append(WorkflowError(
                code=ErrorCode.MODULE_NOT_FOUND,
                message=f'Module not found: {module_id}',
                path=f'nodes[{node["id"]}]',
                meta={'module_id': module_id}
            ))
            continue

        # Check can_be_start
        can_be_start = meta.get('can_be_start', True)
        if not can_be_start:
            errors.append(WorkflowError(
                code=ErrorCode.INVALID_START_NODE,
                message=f'{module_id} cannot be used as a start node',
                path=f'nodes[{node["id"]}]',
                meta={'module_id': module_id}
            ))

        # Check start_requires_params
        required_params = meta.get('start_requires_params', [])
        node_params = node.get('params', {})

        for param in required_params:
            if param not in node_params or node_params[param] is None:
                errors.append(WorkflowError(
                    code=ErrorCode.MISSING_START_PARAMS,
                    message=f'Start node {module_id} requires parameter: {param}',
                    path=f'nodes[{node["id"]}].params.{param}',
                    meta={'module_id': module_id, 'param': param}
                ))

    return errors


def get_startable_modules() -> List[Dict[str, Any]]:
    """
    Get all modules that can be used as start nodes.

    Returns:
        List of module metadata for startable modules:
        [
            {
                'module_id': 'browser.launch',
                'label': 'Launch Browser',
                'category': 'browser',
                'icon': 'Globe',
                'start_requires_params': []
            },
            ...
        ]
    """
    from .index import ConnectionIndex
    from ..modules.registry import ModuleRegistry

    index = ConnectionIndex.get_instance()
    results = []

    for module_id in index.startable_modules:
        meta = ModuleRegistry.get_metadata(module_id)
        if meta:
            results.append({
                'module_id': module_id,
                'label': meta.get('ui_label', module_id),
                'category': meta.get('category', ''),
                'icon': meta.get('ui_icon', 'Box'),
                'color': meta.get('ui_color', '#6B7280'),
                'start_requires_params': meta.get('start_requires_params', []),
            })

    return results


def _detect_cycles(
    node_ids: Set[str],
    outgoing: Dict[str, List[str]],
    node_map: Dict[str, Dict[str, Any]],
) -> List[WorkflowError]:
    """Detect cycles in the workflow graph using DFS"""
    errors: List[WorkflowError] = []

    # Skip cycle detection for loop modules
    from ..modules.registry import ModuleRegistry

    loop_nodes = set()
    for nid in node_ids:
        module_id = node_map[nid].get('module_id', '')
        meta = ModuleRegistry.get_metadata(module_id)
        if meta and meta.get('node_type') == 'loop':
            loop_nodes.add(nid)

    # DFS for cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}
    path: List[str] = []

    def dfs(node: str) -> bool:
        """Returns True if cycle found"""
        color[node] = GRAY
        path.append(node)

        for next_node in outgoing[node]:
            if next_node in loop_nodes:
                continue  # Skip loop modules
            if color[next_node] == GRAY:
                # Found cycle
                cycle_start = path.index(next_node)
                cycle_path = path[cycle_start:] + [next_node]
                errors.append(WorkflowError(
                    code=ErrorCode.CYCLE_DETECTED,
                    message=f'Cycle detected: {" -> ".join(cycle_path)}',
                    path='workflow',
                    meta={'cycle': cycle_path}
                ))
                return True
            if color[next_node] == WHITE:
                if dfs(next_node):
                    return True

        path.pop()
        color[node] = BLACK
        return False

    for node in node_ids:
        if node not in loop_nodes and color[node] == WHITE:
            dfs(node)

    return errors
