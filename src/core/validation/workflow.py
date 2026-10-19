# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Workflow Validation API

Validates entire workflows.
Used by flyto-cloud before save/execute.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..canvas_handles import exit_edge_conflicts
from .connection import validate_connection
from .errors import ErrorCode


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


def _evaluate_show_condition(condition: Any, current_value: Any) -> bool:
    """
    Evaluate a single showIf/hideIf condition against a current param value.

    Supports:
    - {"$in": [values]}  → value in list
    - {"$ne": value}     → value != condition
    - {"$notEmpty": true} → value is not empty
    - [values]           → value in list (shorthand)
    - single value       → equality
    """
    if isinstance(condition, dict):
        if '$in' in condition:
            return current_value in condition['$in']
        if '$ne' in condition:
            return current_value != condition['$ne']
        if '$notEmpty' in condition:
            is_empty = current_value is None or current_value == ''
            return not is_empty if condition['$notEmpty'] else is_empty
        return False
    if isinstance(condition, list):
        return current_value in condition
    return current_value == condition


def _is_field_active(param_def: Dict[str, Any], params: Dict[str, Any]) -> bool:
    """
    Check if a field is currently active based on showIf/hideIf/displayOptions.
    Returns True if the field should be visible (and thus required checks apply).
    """
    # showIf: ALL conditions must match for the field to be visible
    show_if = param_def.get('showIf')
    if show_if and isinstance(show_if, dict):
        for dep_key, condition in show_if.items():
            if not _evaluate_show_condition(condition, params.get(dep_key)):
                return False

    # hideIf: ANY condition matching hides the field
    hide_if = param_def.get('hideIf')
    if hide_if and isinstance(hide_if, dict):
        for dep_key, condition in hide_if.items():
            if _evaluate_show_condition(condition, params.get(dep_key)):
                return False

    # displayOptions (n8n-style): { show: { field: [values] }, hide: { field: [values] } }
    display_options = param_def.get('displayOptions')
    if display_options and isinstance(display_options, dict):
        show = display_options.get('show')
        if show and isinstance(show, dict):
            for dep_key, condition in show.items():
                if not _evaluate_show_condition(condition, params.get(dep_key)):
                    return False
        hide = display_options.get('hide')
        if hide and isinstance(hide, dict):
            for dep_key, condition in hide.items():
                if _evaluate_show_condition(condition, params.get(dep_key)):
                    return False

    return True


def validate_node_params(
    node: Dict[str, Any],
    strict: bool = False,
) -> List[WorkflowError]:
    """
    Validate node parameters against module's params_schema.

    Checks:
    - All provided params keys exist in params_schema
    - Required params are present (respecting showIf/hideIf/displayOptions)
    - Param values match expected types

    Args:
        node: Node definition with 'id', 'module_id', 'params'
        strict: If True, unknown params are errors; if False, warnings

    Returns:
        List of validation errors/warnings
    """
    from ..modules.registry import ModuleRegistry

    results: List[WorkflowError] = []
    node_id = node.get('id', 'unknown')
    module_id = node.get('module_id', '')
    params = node.get('params', {})

    if not module_id:
        return results

    meta = ModuleRegistry.get_metadata(module_id)
    if not meta:
        return results

    params_schema = meta.get('params_schema', {})
    if not params_schema:
        return results  # No schema to validate against
    # Support JSON Schema style: {type, properties, required}
    if isinstance(params_schema, dict) and 'properties' in params_schema:
        properties = params_schema.get('properties') or {}
        required_list = params_schema.get('required') or []
    else:
        properties = params_schema
        required_list = []

    valid_keys = set(properties.keys()) if isinstance(properties, dict) else set()

    # template.invoke is an open-parameter boundary by design: every key beyond
    # its control fields is forwarded to the invoked template as an input.  The
    # child template owns that dynamic schema, so validating those keys against
    # the static registry entry would turn legitimate child inputs into false
    # UNKNOWN_PARAM warnings.
    if module_id != 'template.invoke':
        for param_key in params:
            if param_key not in valid_keys:
                results.append(WorkflowError(
                    code=ErrorCode.UNKNOWN_PARAM,
                    message=f'Unknown parameter "{param_key}" in {node_id}',
                    path=f'nodes[{node_id}].params.{param_key}',
                    meta={
                        'node_id': node_id,
                        'module_id': module_id,
                        'param': param_key,
                        'valid_params': ', '.join(sorted(valid_keys)) or '(none)',
                    }
                ))

    # Track already-reported params to avoid duplicates
    reported_missing = set()

    # Check for missing required params (from top-level required list)
    for param_key in required_list:
        # Skip if field is conditionally hidden
        param_def = properties.get(param_key, {}) if isinstance(properties, dict) else {}
        if isinstance(param_def, dict) and not _is_field_active(param_def, params):
            continue

        value = params.get(param_key)
        if value is None or value == '':
            reported_missing.add(param_key)
            results.append(WorkflowError(
                code=ErrorCode.MISSING_REQUIRED_PARAM,
                message=f'Missing required parameter: {param_key}',
                path=f'nodes[{node_id}].params.{param_key}',
                meta={
                    'node_id': node_id,
                    'module_id': module_id,
                    'param': param_key,
                }
            ))

    # Check per-property required flag
    if isinstance(properties, dict):
        for param_key, param_def in properties.items():
            if param_key in reported_missing:
                continue
            if isinstance(param_def, dict) and param_def.get('required', False):
                # Skip if field is conditionally hidden
                if not _is_field_active(param_def, params):
                    continue

                value = params.get(param_key)
                if value is None or value == '':
                    results.append(WorkflowError(
                        code=ErrorCode.MISSING_REQUIRED_PARAM,
                        message=f'Missing required parameter: {param_key}',
                        path=f'nodes[{node_id}].params.{param_key}',
                        meta={
                            'node_id': node_id,
                            'module_id': module_id,
                            'param': param_key,
                        }
                    ))

    results.extend(_exclusive_param_errors(node_id, module_id, properties, params))
    return results


def _is_set(value: Any) -> bool:
    """A param counts as set when it holds something; None and '' are unset."""
    return value is not None and value != ''


def _exclusive_param_errors(
    node_id: str,
    module_id: str,
    properties: Any,
    params: Dict[str, Any],
) -> List[WorkflowError]:
    """Each declared-exclusive param set beside a field that rules it out.

    A field's ``exclusive_with`` names the fields that, once set, make it
    unused (``browser.wait``: a selector rules out ``duration_ms``). The error
    sits on the ruled-out field, the one a panel greys out.
    """
    if not isinstance(properties, dict):
        return []
    found: List[WorkflowError] = []
    for param_key, param_def in properties.items():
        if not isinstance(param_def, dict) or not _is_set(params.get(param_key)):
            continue
        for other in param_def.get('exclusive_with') or []:
            if _is_set(params.get(other)):
                found.append(WorkflowError(
                    code=ErrorCode.PARAMS_EXCLUSIVE,
                    message=f'{param_key} is not used while {other} is set',
                    path=f'nodes[{node_id}].params.{param_key}',
                    meta={
                        'node_id': node_id,
                        'module_id': module_id,
                        'param': param_key,
                        'ruled_out_by': other,
                    },
                ))
                break
    return found


def _context_values(contexts: Any) -> List[str]:
    """Context names as plain strings (metadata may hold ContextType members)."""
    return [str(getattr(c, 'value', c)) for c in (contexts or [])]


def _upstream(node_ids: List[str], edges: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Every node each node can be reached from.

    With edges the document runs as a graph, so upstream is what the edges
    say. Without any, the engine runs the steps in list order, so every
    earlier step is upstream of a later one.
    """
    if not edges:
        return {nid: set(node_ids[:index]) for index, nid in enumerate(node_ids)}
    parents: Dict[str, Set[str]] = {nid: set() for nid in node_ids}
    for edge in edges:
        source, target = edge.get('source'), edge.get('target')
        if source in parents and target in parents and source != target:
            parents[target].add(source)
    found: Dict[str, Set[str]] = {}
    for nid in node_ids:
        seen: Set[str] = set()
        stack = list(parents[nid])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(parents.get(current, ()))
        found[nid] = seen - {nid}
    return found


def _session_context_errors(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> List[WorkflowError]:
    """Each step requiring a session context no upstream step provides.

    Read from the contract (``requires_context`` / ``provides_context``), never
    from a module name; only contexts with an establisher in
    ``CONTEXT_ESTABLISHERS`` are sessions, so only those are enforced.
    """
    from ..modules.registry import ModuleRegistry
    from ..modules.types.context import CONTEXT_ESTABLISHERS

    def contract(module_id: str) -> Dict[str, Any]:
        try:
            return ModuleRegistry.get_metadata(module_id) or {}
        except Exception:  # an unregistered module is reported elsewhere
            return {}

    node_ids = [n.get('id') for n in nodes if n.get('id')]
    contracts = {n.get('id'): contract(n.get('module_id') or '') for n in nodes if n.get('id')}
    upstream = _upstream(node_ids, edges)
    found: List[WorkflowError] = []
    for node in nodes:
        node_id = node.get('id')
        if not node_id:
            continue
        needed = [c for c in _context_values(contracts[node_id].get('requires_context')) if c in CONTEXT_ESTABLISHERS]
        if not needed:
            continue
        provided: Set[str] = set()
        for ancestor in upstream.get(node_id, ()):
            provided.update(_context_values(contracts.get(ancestor, {}).get('provides_context')))
        missing = [c for c in needed if c not in provided]
        if not missing:
            continue
        context = missing[0]
        found.append(WorkflowError(
            code=ErrorCode.CONTEXT_NOT_ESTABLISHED,
            message=f'{node_id} needs a {context} session opened before it',
            path=f'nodes[{node_id}]',
            meta={
                'node_id': node_id,
                'module_id': node.get('module_id') or '',
                'context': context,
                'missing': missing,
                'establish_with': CONTEXT_ESTABLISHERS[context],
            },
        ))
    return found


def _duration_only_waits(nodes: List[Dict[str, Any]]) -> List[WorkflowError]:
    """Flag browser.wait nodes that sleep instead of waiting on page state.

    A warning, never an error: an explicit pause stays valid, but a page
    almost always exposes the state the pause is guessing at, and a fixed
    sleep costs its whole duration on every run.
    """
    results: List[WorkflowError] = []
    for node in nodes:
        if node.get('module_id') != 'browser.wait':
            continue
        params = node.get('params') or {}
        if str(params.get('selector') or '').strip():
            continue
        node_id = node.get('id', 'unknown')
        results.append(WorkflowError(
            code=ErrorCode.DURATION_ONLY_WAIT,
            message=(
                f'{node_id} waits a fixed duration; wait on a selector state '
                'instead'
            ),
            path=f'nodes[{node_id}].params',
            meta={'node_id': node_id, 'module_id': 'browser.wait'},
        ))
    return results


def _exit_edge_errors(edges: List[Dict[str, Any]], node_map: Dict[str, Dict[str, Any]]) -> List[WorkflowError]:
    """Each edge beyond what its exit allows (core.canvas_handles), as a typed error on that edge."""
    from ..modules.registry import ModuleRegistry

    def ports_of(node_id: str) -> List[Dict[str, Any]]:
        module_id = (node_map.get(node_id) or {}).get('module_id') or ''
        try:
            return (ModuleRegistry.get_metadata(module_id) or {}).get('output_ports') or []
        except Exception:  # an unregistered module is judged by its handle alone
            return []

    return [
        WorkflowError(
            code=ErrorCode.EXIT_HAS_ONE_EDGE,
            message=f"{conflict['node_id']} already leaves its {conflict['exit']} exit by another edge",
            path=f"edges[{conflict['edge_id']}]",
            meta={'node_id': conflict['node_id'], 'exit': conflict['exit'],
                  'limit': conflict['limit'], 'target': conflict['target']},
        )
        for conflict in exit_edge_conflicts(edges, ports_of)
    ]


def validate_workflow(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    validate_params: bool = True,
    context_edges: Optional[List[Dict[str, Any]]] = None,
) -> WorkflowResult:
    """
    Validate entire workflow.

    Checks:
    - All edges are valid connections
    - No orphan nodes (except start nodes)
    - Start nodes are valid
    - Required parameters are set
    - Unknown params are flagged as warnings
    - Duration-only browser.wait nodes are flagged as warnings
    - No cycles (except in loop modules)

    Args:
        nodes: List of node definitions
            [{'id': 'n1', 'module_id': 'browser.launch', 'params': {...}}, ...]
        edges: List of edge definitions
            [{'id': 'e1', 'source': 'n1', 'target': 'n2'}, ...]
        validate_params: Whether to validate params against schema
        context_edges: The edges a session travels along, when a host
            validates fewer control-flow edges than the document has (a loop
            body reached by an iterate edge). Defaults to ``edges``.

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
        source_handle = edge.get('sourceHandle') or edge.get('source_handle') or edge.get('from_port')
        target_handle = edge.get('targetHandle') or edge.get('target_handle') or edge.get('to_port')
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

        # Check for node-level self-connection (different from module-level)
        if source_id == target_id:
            errors.append(WorkflowError(
                code=ErrorCode.SELF_CONNECTION,
                message='A node cannot connect to itself',
                path=f'edges[{edge_id}]',
                meta={'source': source_id, 'target': target_id}
            ))
            continue

        # Validate connection (module compatibility)
        source_module = node_map[source_id].get('module_id', '')
        target_module = node_map[target_id].get('module_id', '')

        # Skip module-level self-connection check if nodes are different
        # (e.g., two different flow.end nodes connected is NOT a self-connection)
        if source_module != target_module:
            result = validate_connection(
                source_module,
                target_module,
                from_port=source_handle or None,
                to_port=target_handle or None,
            )
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

    errors.extend(_exit_edge_errors(edges, node_map))

    # Validate start nodes
    start_errors = validate_start(nodes, edges)
    errors.extend(start_errors)

    # NOTE: ORPHAN_NODE check removed - users should be able to save
    # work-in-progress workflows with unconnected nodes

    # Validate params for each node
    if validate_params:
        for node in nodes:
            param_errors = validate_node_params(node, strict=False)
            for err in param_errors:
                if err.code == ErrorCode.UNKNOWN_PARAM:
                    warnings.append(err)
                else:
                    errors.append(err)

    warnings.extend(_duration_only_waits(nodes))

    # A step whose session no upstream step opens fails at run time; refuse it here.
    errors.extend(_session_context_errors(nodes, edges if context_edges is None else context_edges))

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
    incoming: Dict[str, int] = dict.fromkeys(node_ids, 0)

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
    from ..modules.registry import ModuleRegistry
    from .index import ConnectionIndex

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
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(node_ids, white)
    path: List[str] = []

    def dfs(node: str) -> bool:
        """Returns True if cycle found"""
        color[node] = gray
        path.append(node)

        for next_node in outgoing[node]:
            if next_node in loop_nodes:
                continue  # Skip loop modules
            if color[next_node] == gray:
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
            if color[next_node] == white and dfs(next_node):
                return True

        path.pop()
        color[node] = black
        return False

    for node in node_ids:
        if node not in loop_nodes and color[node] == white:
            dfs(node)

    return errors
