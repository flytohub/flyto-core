"""
Workflow Routing

Edge-based routing and step connection handling for Workflow Spec v1.2.
"""

import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


class WorkflowRouter:
    """
    Handles edge-based routing and step connections.

    Supports:
    - Edge-based routing (Workflow Spec v1.1)
    - Step connections (Workflow Spec v1.2)
    - Legacy next_step routing
    - Upstream step tracking for item propagation (ITEM_PIPELINE_SPEC.md)
    """

    def __init__(self):
        # Index mapping step_id to position
        self._step_index: Dict[str, int] = {}
        self._step_map: Dict[str, Dict[str, Any]] = {}

        # Edge index: source_id -> [edges from this source]
        self._edge_index: Dict[str, List[Dict[str, Any]]] = {}

        # Reverse edge index: target_id -> [edges to this target]
        self._incoming_edges: Dict[str, List[Dict[str, Any]]] = {}

        # Event routes: "source_id:event" -> target_id
        self._event_routes: Dict[str, str] = {}

        # Step connections: step_id -> {port: [targets]}
        self._step_connections: Dict[str, Dict[str, List[str]]] = {}

    def build_step_index(self, steps: List[Dict[str, Any]]) -> None:
        """Build index mapping step IDs to their positions."""
        self._step_index = {}
        self._step_map = {}
        for idx, step in enumerate(steps):
            step_id = step.get('id')
            if step_id:
                self._step_index[step_id] = idx
                self._step_map[step_id] = step

    def build_edge_index(
        self,
        edges: List[Dict[str, Any]],
        steps: List[Dict[str, Any]],
    ) -> None:
        """
        Build edge index for event-based routing (Workflow Spec v1.2)

        Creates mappings:
        - _edge_index: source_id -> [edges from this source]
        - _event_routes: "source_id:event" -> target_id
        - _step_connections: step_id -> {port: [targets]} (from step.connections)

        Priority for routing (v1.2):
        1. step.connections (highest - semantic connections)
        2. _event_routes from edges (medium - canvas edges)
        3. next_step/params.target (lowest - legacy)
        """
        self._edge_index = {}
        self._incoming_edges = {}
        self._event_routes = {}
        self._step_connections = {}

        step_map = self._step_map

        # Build routes from edges (v1.1 pattern)
        for edge in edges:
            source = edge.get('source', '')
            source_handle = edge.get('sourceHandle', 'success')
            target = edge.get('target', '')
            edge_type = edge.get('type', edge.get('edge_type', 'data'))  # Default to 'data' for item propagation

            # Only process control/data edges for flow routing (skip resource edges)
            if edge_type == 'resource':
                continue

            if not source or not target:
                continue

            # Build source -> edges index
            if source not in self._edge_index:
                self._edge_index[source] = []
            self._edge_index[source].append(edge)

            # Build target -> incoming edges index (for upstream tracking)
            if target not in self._incoming_edges:
                self._incoming_edges[target] = []
            self._incoming_edges[target].append(edge)

            # Build event route: "source:handle" -> target
            route_key = f"{source}:{source_handle}"
            self._event_routes[route_key] = target

            # Add normalized event routes for UI handle IDs
            step = step_map.get(source)
            normalized_events = self._normalize_handle_to_events(source_handle, step)
            for event in normalized_events:
                if not event:
                    continue
                normalized_key = f"{source}:{event}"
                if normalized_key not in self._event_routes:
                    self._event_routes[normalized_key] = target

        # Build routes from step.connections (v1.2 pattern)
        for step in steps:
            step_id = step.get('id', '')
            connections = step.get('connections', {})

            if connections and step_id:
                self._step_connections[step_id] = {}
                for port_name, targets in connections.items():
                    # Handle both array and single value
                    if isinstance(targets, str):
                        targets = [targets]
                    if isinstance(targets, list) and targets:
                        self._step_connections[step_id][port_name] = targets
                        # Also add to _event_routes for backward compat
                        route_key = f"{step_id}:{port_name}"
                        if route_key not in self._event_routes:
                            self._event_routes[route_key] = targets[0]
                        # Add normalized event aliases for connections
                        for event in self._normalize_handle_to_events(port_name, step):
                            if not event:
                                continue
                            normalized_key = f"{step_id}:{event}"
                            if normalized_key not in self._event_routes:
                                self._event_routes[normalized_key] = targets[0]

        self._log_build_summary(edges)

    def _log_build_summary(self, edges: List[Dict[str, Any]]) -> None:
        """Log summary of built indices."""
        log_parts = []
        if edges:
            log_parts.append(f"{len(self._edge_index)} sources")
        if self._event_routes:
            log_parts.append(f"{len(self._event_routes)} routes")
        if self._step_connections:
            log_parts.append(f"{len(self._step_connections)} connection-based")
        if log_parts:
            logger.debug(f"Built edge index: {', '.join(log_parts)}")

    def get_next_step_index(
        self,
        step_id: str,
        result: Dict[str, Any],
        current_idx: int,
    ) -> int:
        """
        Determine next step index based on routing rules.

        Priority:
        1. step.connections (v1.2)
        2. edge-based routing (v1.1)
        3. legacy next_step field
        4. sequential (current_idx + 1)
        """
        if not isinstance(result, dict):
            return current_idx + 1

        event = result.get('__event__')
        step = self._step_map.get(step_id)

        # Special case: __end__ event signals workflow termination
        if event == '__end__':
            logger.debug(f"End event from {step_id}, terminating workflow")
            return 999999  # Return high value to exit step loop

        next_step_id = None

        # Priority 1: step.connections (v1.2)
        if step_id in self._step_connections:
            step_conns = self._step_connections[step_id]

            # Try explicit event first, then fallback to 'default' or 'success'
            events_to_try = [event] if event else []
            if event:
                events_to_try.extend(self._normalize_handle_to_events(event, step))
            events_to_try.extend(['default', 'success'])

            for try_event in events_to_try:
                if try_event and try_event in step_conns and step_conns[try_event]:
                    next_step_id = step_conns[try_event][0]
                    logger.debug(f"Connections routing: {step_id}.connections.{try_event} -> {next_step_id}")
                    break

        # Priority 2: Edge-based routing (v1.1)
        if not next_step_id and event and self._event_routes:
            events_to_try = [event]
            events_to_try.extend(self._normalize_handle_to_events(event, step))
            for try_event in events_to_try:
                route_key = f"{step_id}:{try_event}"
                if route_key in self._event_routes:
                    next_step_id = self._event_routes[route_key]
                    logger.debug(f"Edge routing: {route_key} -> {next_step_id}")
                    break

        # Priority 3: Legacy next_step field
        if not next_step_id:
            next_step_id = result.get('next_step')
            if next_step_id:
                logger.debug(f"Legacy routing: next_step -> {next_step_id}")

        # Resolve step_id to index
        if next_step_id and next_step_id in self._step_index:
            return self._step_index[next_step_id]

        return current_idx + 1

    def get_step_index(self, step_id: str) -> int:
        """Get index for a step ID, or -1 if not found."""
        return self._step_index.get(step_id, -1)

    @property
    def step_index(self) -> Dict[str, int]:
        """Get the step index mapping."""
        return self._step_index

    @property
    def event_routes(self) -> Dict[str, str]:
        """Get event routes mapping."""
        return self._event_routes

    @property
    def step_connections(self) -> Dict[str, Dict[str, List[str]]]:
        """Get step connections mapping."""
        return self._step_connections

    def get_upstream_steps(
        self,
        step_id: str,
        data_edges_only: bool = True
    ) -> Dict[str, List[str]]:
        """
        Get upstream step IDs that feed into this step.

        Args:
            step_id: Target step ID
            data_edges_only: If True, only return edges that pass items (data, iterate)

        Returns:
            Dict mapping input port name to list of source step IDs
            e.g. {"input": ["step1", "step2"], "secondary": ["step3"]}
        """
        incoming = self._incoming_edges.get(step_id, [])
        result: Dict[str, List[str]] = {}

        for edge in incoming:
            source = edge.get('source', '')
            edge_type = edge.get('type', edge.get('edge_type', 'data'))
            target_handle = edge.get('targetHandle', 'input')

            # Filter by edge type if requested
            if data_edges_only:
                # Only data and iterate edges pass items
                if edge_type not in ('data', 'iterate'):
                    continue

            # Group by target handle (input port)
            port = target_handle or 'input'
            if port not in result:
                result[port] = []
            if source and source not in result[port]:
                result[port].append(source)

        return result

    def get_upstream_step_ids(
        self,
        step_id: str,
        data_edges_only: bool = True
    ) -> List[str]:
        """
        Get flat list of upstream step IDs (convenience method).

        Args:
            step_id: Target step ID
            data_edges_only: If True, only return edges that pass items

        Returns:
            List of unique source step IDs
        """
        by_port = self.get_upstream_steps(step_id, data_edges_only)
        seen: Set[str] = set()
        result: List[str] = []
        for sources in by_port.values():
            for source in sources:
                if source not in seen:
                    result.append(source)
                    seen.add(source)
        return result

    def _normalize_handle_to_events(
        self,
        handle_id: str,
        step: Dict[str, Any] = None,
    ) -> List[str]:
        """
        Normalize UI handle IDs to canonical event names.

        Examples:
        - source-true -> true
        - source-item -> iterate
        - source-case-<id> -> case:<id> (+ case:<value> if available in step params)
        """
        if not handle_id:
            return []

        # Case: already an event key (case:xxx)
        if handle_id.startswith('case:'):
            return self._expand_case_events(handle_id, step)

        # Case: UI dynamic handle for switch
        if handle_id.startswith('source-case-'):
            case_id = handle_id.replace('source-case-', '')
            return self._expand_case_events(f"case:{case_id}", step)

        normalized = handle_id
        if normalized.startswith('source-'):
            normalized = normalized[len('source-'):]

        if normalized.startswith('branch-') or normalized.startswith('branch_'):
            return ['fork', normalized]

        alias_map = {
            'main': 'success',
            'success': 'success',
            'error': 'error',
            'true': 'true',
            'false': 'false',
            'default': 'default',
            'item': 'iterate',
            'iterate': 'iterate',
            'done': 'done',
            'body_out': 'iterate',
            'done_out': 'done',
            'trigger': 'trigger',
            'triggered': 'trigger',
            'start': 'start',
        }

        if normalized in ('merged', 'joined'):
            return [normalized, 'success']

        return [alias_map.get(normalized, normalized)]

    def _expand_case_events(
        self,
        case_event: str,
        step: Dict[str, Any] = None,
    ) -> List[str]:
        """
        Expand case events to include both id/value variants when possible.
        """
        if not case_event.startswith('case:'):
            return [case_event]

        events = [case_event]
        case_value = case_event.replace('case:', '')

        if step:
            params = step.get('params') or {}
            cases = params.get('cases') if isinstance(params, dict) else None
            if isinstance(cases, list):
                for item in cases:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get('id')) if item.get('id') is not None else None
                    item_value = str(item.get('value')) if item.get('value') is not None else None
                    if item_id == case_value and item_value:
                        events.append(f"case:{item_value}")
                        break
                    if item_value == case_value and item_id:
                        events.append(f"case:{item_id}")
                        break

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for event in events:
            if event not in seen:
                unique.append(event)
                seen.add(event)
        return unique
