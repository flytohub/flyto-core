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

    from_meta = ModuleRegistry.get_metadata(from_module_id)
    to_meta = ModuleRegistry.get_metadata(to_module_id)

    if not from_meta:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.MODULE_NOT_FOUND,
            error_message=f'Module not found: {from_module_id}',
            meta={'module_id': from_module_id}
        )

    if not to_meta:
        return ConnectionResult(
            valid=False,
            error_code=ErrorCode.MODULE_NOT_FOUND,
            error_message=f'Module not found: {to_module_id}',
            meta={'module_id': to_module_id}
        )

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

    # Check output_types / input_types compatibility
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
