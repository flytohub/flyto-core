"""
Connection Validation API

Validates connections between modules.
Used by flyto-cloud for edge-level validation.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .errors import ErrorCode


@dataclass
class ConnectionResult:
    """Result of connection validation"""
    valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


def validate_connection(
    from_module_id: str,
    to_module_id: str,
    from_port: str = 'output',
    to_port: str = 'input',
) -> ConnectionResult:
    """
    Validate if two modules can be connected.

    Args:
        from_module_id: Source module ID (e.g., 'browser.click')
        to_module_id: Target module ID (e.g., 'browser.screenshot')
        from_port: Source port name (default: 'output')
        to_port: Target port name (default: 'input')

    Returns:
        ConnectionResult with valid=True/False and error details

    Example:
        >>> validate_connection('browser.click', 'browser.screenshot')
        ConnectionResult(valid=True)

        >>> validate_connection('http.response', 'browser.click')
        ConnectionResult(
            valid=False,
            error_code='TYPE_MISMATCH',
            error_message='browser.click requires browser_page, but received http_response'
        )
    """
    # Self-connection check
    if from_module_id == to_module_id:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.SELF_CONNECTION,
            error_message='A node cannot connect to itself',
        )

    # Get module metadata
    from ..modules.registry import ModuleRegistry

    # Special handling for user templates (template.XXX) - they're not in core registry
    # Templates can connect to/from anything, so we allow all connections
    is_from_template = from_module_id.startswith('template.')
    is_to_template = to_module_id.startswith('template.')

    if is_from_template and is_to_template:
        # Both are templates - allow connection
        return ConnectionResult(valid=True)

    from_meta = ModuleRegistry.get_metadata(from_module_id) if not is_from_template else None
    to_meta = ModuleRegistry.get_metadata(to_module_id) if not is_to_template else None

    if not from_meta and not is_from_template:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.MODULE_NOT_FOUND,
            error_message=f'Module not found: {from_module_id}',
            meta={'module_id': from_module_id}
        )

    if not to_meta and not is_to_template:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.MODULE_NOT_FOUND,
            error_message=f'Module not found: {to_module_id}',
            meta={'module_id': to_module_id}
        )

    # If one side is a template, allow connection (templates are flexible)
    if is_from_template or is_to_template:
        return ConnectionResult(valid=True)

    # Check can_connect_to / can_receive_from rules
    can_connect_to = from_meta.get('can_connect_to', ['*'])
    can_receive_from = to_meta.get('can_receive_from', ['*'])

    # Wildcard check
    if '*' not in can_connect_to:
        # Check if to_module matches any pattern
        if not _matches_any_pattern(to_module_id, can_connect_to):
            return ConnectionResult(
                valid=False,
                error_code=ErrorCode.INCOMPATIBLE_MODULES,
                error_message=f'{from_module_id} cannot connect to {to_module_id}',
                meta={
                    'from_module': from_module_id,
                    'to_module': to_module_id,
                    'allowed': can_connect_to
                }
            )

    if '*' not in can_receive_from:
        # Check if from_module matches any pattern
        if not _matches_any_pattern(from_module_id, can_receive_from):
            return ConnectionResult(
                valid=False,
                error_code=ErrorCode.INCOMPATIBLE_MODULES,
                error_message=f'{to_module_id} cannot receive from {from_module_id}',
                meta={
                    'from_module': from_module_id,
                    'to_module': to_module_id,
                    'allowed': can_receive_from
                }
            )

    # Check port-level compatibility when ports are defined
    from_ports = from_meta.get('output_ports') or []
    to_ports = to_meta.get('input_ports') or []

    # Port alias mapping: VueFlow handle IDs ↔ flyto-core port IDs
    # VueFlow uses: 'output', 'target', 'in', etc.
    # flyto-core uses: 'success', 'error', 'input', 'iterate', 'done', etc.
    OUTPUT_PORT_ALIASES = {
        'output': 'success',
        'source': 'success',
        'body_out': 'iterate',
        'done_out': 'done',
    }
    INPUT_PORT_ALIASES = {
        'input': 'input',
        'target': 'input',
        'in': 'input',  # LoopNode uses 'in' for input
        'loop_back_in': 'input',  # LoopNode loop-back input
    }

    def find_port(ports: List, port_id: str, aliases: Dict) -> Optional[Dict]:
        """Find port by ID or alias"""
        if not ports:
            return None
        # Direct match
        match = next((p for p in ports if p.get('id') == port_id), None)
        if match:
            return match
        # Try alias
        alias_id = aliases.get(port_id)
        if alias_id:
            return next((p for p in ports if p.get('id') == alias_id), None)
        return None

    from_port_meta = find_port(from_ports, from_port, OUTPUT_PORT_ALIASES)
    to_port_meta = find_port(to_ports, to_port, INPUT_PORT_ALIASES)

    if from_ports and not from_port_meta:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.PORT_NOT_FOUND,
            error_message=f'Port not found: {from_port}',
            meta={'from_module': from_module_id, 'from_port': from_port}
        )
    if to_ports and not to_port_meta:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.PORT_NOT_FOUND,
            error_message=f'Port not found: {to_port}',
            meta={'to_module': to_module_id, 'to_port': to_port}
        )

    if from_port_meta and to_port_meta:
        from_edge_type = from_port_meta.get('edge_type')
        to_edge_type = to_port_meta.get('edge_type')
        if from_edge_type and to_edge_type and from_edge_type != to_edge_type:
            return ConnectionResult(
                valid=False,
                error_code=ErrorCode.INCOMPATIBLE_MODULES,
                error_message=f'Incompatible edge type: {from_edge_type} -> {to_edge_type}',
                meta={
                    'from_module': from_module_id,
                    'to_module': to_module_id,
                    'from_port': from_port,
                    'to_port': to_port,
                    'from_edge_type': from_edge_type,
                    'to_edge_type': to_edge_type,
                }
            )

        from_data_type = from_port_meta.get('data_type')
        to_data_type = to_port_meta.get('data_type')
        if from_data_type and to_data_type:
            from_types = from_data_type if isinstance(from_data_type, list) else [from_data_type]
            to_types = to_data_type if isinstance(to_data_type, list) else [to_data_type]
            if 'any' not in from_types and 'any' not in to_types:
                if not any(t in to_types for t in from_types):
                    return ConnectionResult(
                        valid=False,
                        error_code=ErrorCode.TYPE_MISMATCH,
                        error_message=f'{to_module_id} requires {to_types}, but received {from_types}',
                        meta={
                            'to_module': to_module_id,
                            'expected': to_types,
                            'received': from_types,
                            'from_port': from_port,
                            'to_port': to_port,
                        }
                    )
        # Port-level checks passed; skip module-level type checks
        return ConnectionResult(valid=True)

    # Check output_types / input_types compatibility (module-level fallback)
    output_types = from_meta.get('output_types', [])
    input_types = to_meta.get('input_types', [])

    if output_types and input_types:
        # If both have types, check compatibility
        if '*' not in input_types and '*' not in output_types:
            if not _types_compatible(output_types, input_types):
                return ConnectionResult(
                    valid=False,
                    error_code=ErrorCode.TYPE_MISMATCH,
                    error_message=f'{to_module_id} requires {input_types}, but received {output_types}',
                    meta={
                        'to_module': to_module_id,
                        'expected': input_types,
                        'received': output_types
                    }
                )

    return ConnectionResult(valid=True)


def _matches_any_pattern(module_id: str, patterns: List[str]) -> bool:
    """Check if module_id matches any pattern (supports wildcards like 'browser.*')"""
    for pattern in patterns:
        if pattern == '*':
            return True
        if pattern.endswith('.*'):
            # Category wildcard: 'browser.*' matches 'browser.click'
            prefix = pattern[:-2]
            if module_id.startswith(prefix + '.'):
                return True
        elif pattern == module_id:
            return True
    return False


def _types_compatible(output_types: List[str], input_types: List[str]) -> bool:
    """Check if output types are compatible with input types"""
    # Any common type means compatible
    for out_type in output_types:
        if out_type in input_types:
            return True
        # 'any' type accepts everything
        if 'any' in input_types:
            return True
    return False


def get_connectable(
    module_id: str,
    direction: str = 'next',
    port: str = 'default',
    limit: int = 50,
    search: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get all modules that can connect to/from the given module.

    Args:
        module_id: Current module ID
        direction: 'next' = downstream (what can this connect to)
                   'prev' = upstream (what can connect to this)
        port: Port name (for future multi-port support)
        limit: Maximum results to return
        search: Search filter for module_id or label
        category: Only return modules in this category

    Returns:
        List of connectable modules with metadata:
        [
            {
                'module_id': 'browser.screenshot',
                'label': 'Take Screenshot',
                'category': 'browser',
                'icon': 'Camera',
                'color': '#8B5CF6',
                'match_score': 1.0
            },
            ...
        ]
    """
    from .index import ConnectionIndex

    index = ConnectionIndex.get_instance()

    if direction == 'next':
        candidates = index.connectable_next.get(module_id, [])
    else:
        candidates = index.connectable_prev.get(module_id, [])

    # Get metadata for each candidate
    from ..modules.registry import ModuleRegistry

    results = []
    for candidate_id in candidates:
        if category and not candidate_id.startswith(category + '.'):
            continue

        if search and search.lower() not in candidate_id.lower():
            meta = ModuleRegistry.get_metadata(candidate_id)
            if meta and search.lower() not in meta.get('ui_label', '').lower():
                continue

        meta = ModuleRegistry.get_metadata(candidate_id)
        if meta:
            results.append({
                'module_id': candidate_id,
                'label': meta.get('ui_label', candidate_id),
                'category': meta.get('category', ''),
                'icon': meta.get('ui_icon', 'Box'),
                'color': meta.get('ui_color', '#6B7280'),
                'match_score': 1.0,  # Future: calculate based on type matching
            })

        if len(results) >= limit:
            break

    return results


def get_connectable_summary(
    module_id: str,
    direction: str = 'next',
) -> Dict[str, int]:
    """
    Get category counts of connectable modules.

    Args:
        module_id: Current module ID
        direction: 'next' or 'prev'

    Returns:
        {'browser': 12, 'http': 8, 'data': 15, ...}
    """
    from .index import ConnectionIndex

    index = ConnectionIndex.get_instance()
    return index.get_summary(module_id, direction)


def get_connectable_for_replacement(
    upstream_module_id: Optional[str] = None,
    downstream_module_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Get modules that can replace a node (compatible with both upstream and downstream).

    Returns intersection of:
    - Modules that can receive from upstream (if upstream exists)
    - Modules that can send to downstream (if downstream exists)

    Args:
        upstream_module_id: Module ID of the upstream node (optional)
        downstream_module_id: Module ID of the downstream node (optional)
        limit: Maximum results to return

    Returns:
        List of modules compatible with both upstream and downstream
    """
    from .index import ConnectionIndex
    from ..modules.registry import ModuleRegistry

    index = ConnectionIndex.get_instance()

    upstream_compatible = None
    downstream_compatible = None

    # Get modules that can receive from upstream (what comes AFTER upstream)
    if upstream_module_id:
        upstream_compatible = set(index.connectable_next.get(upstream_module_id, []))

    # Get modules that can send to downstream (what comes BEFORE downstream)
    if downstream_module_id:
        downstream_compatible = set(index.connectable_prev.get(downstream_module_id, []))

    # Calculate intersection
    if upstream_compatible is not None and downstream_compatible is not None:
        # Both connected: need intersection
        compatible_ids = upstream_compatible & downstream_compatible
    elif upstream_compatible is not None:
        # Only upstream connected
        compatible_ids = upstream_compatible
    elif downstream_compatible is not None:
        # Only downstream connected
        compatible_ids = downstream_compatible
    else:
        # No connections: return empty (caller should show all modules)
        return []

    # Get metadata for compatible modules
    results = []
    for module_id in compatible_ids:
        meta = ModuleRegistry.get_metadata(module_id)
        if meta:
            results.append({
                'module_id': module_id,
                'label': meta.get('ui_label', module_id),
                'category': meta.get('category', ''),
                'icon': meta.get('ui_icon', 'Box'),
                'color': meta.get('ui_color', '#6B7280'),
            })

        if len(results) >= limit:
            break

    return results


def validate_replacement(
    new_module_id: str,
    upstream_module_id: Optional[str] = None,
    downstream_module_id: Optional[str] = None,
    upstream_port: str = 'output',
    downstream_port: str = 'input',
) -> ConnectionResult:
    """
    Validate if a module can replace an existing node.

    Validates connections based on what's connected:
    1. If upstream exists: upstream → new_module
    2. If downstream exists: new_module → downstream

    Args:
        new_module_id: New module ID to replace with
        upstream_module_id: Upstream module ID (optional)
        downstream_module_id: Downstream module ID (optional)
        upstream_port: Upstream module's output port
        downstream_port: Downstream module's input port

    Returns:
        ConnectionResult with valid=True/False and error details
    """
    errors = []

    # Validate upstream → new_module
    if upstream_module_id:
        result = validate_connection(
            from_module_id=upstream_module_id,
            to_module_id=new_module_id,
            from_port=upstream_port,
            to_port='input',
        )
        if not result.valid:
            errors.append(f"Upstream → New: {result.error_message}")

    # Validate new_module → downstream
    if downstream_module_id:
        result = validate_connection(
            from_module_id=new_module_id,
            to_module_id=downstream_module_id,
            from_port='output',
            to_port=downstream_port,
        )
        if not result.valid:
            errors.append(f"New → Downstream: {result.error_message}")

    if errors:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.INCOMPATIBLE_MODULES,
            error_message="; ".join(errors),
        )

    return ConnectionResult(valid=True)
