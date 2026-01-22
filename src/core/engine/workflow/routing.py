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
    """

    def __init__(self):
        # Index mapping step_id to position
        self._step_index: Dict[str, int] = {}

        # Edge index: source_id -> [edges from this source]
        self._edge_index: Dict[str, List[Dict[str, Any]]] = {}

        # Event routes: "source_id:event" -> target_id
        self._event_routes: Dict[str, str] = {}

        # Step connections: step_id -> {port: [targets]}
        self._step_connections: Dict[str, Dict[str, List[str]]] = {}

    def build_step_index(self, steps: List[Dict[str, Any]]) -> None:
        """Build index mapping step IDs to their positions."""
        self._step_index = {}
        for idx, step in enumerate(steps):
            step_id = step.get('id')
            if step_id:
                self._step_index[step_id] = idx

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
        self._event_routes = {}
        self._step_connections = {}

        # Build routes from edges (v1.1 pattern)
        for edge in edges:
            source = edge.get('source', '')
            source_handle = edge.get('sourceHandle', 'success')
            target = edge.get('target', '')
            edge_type = edge.get('type', edge.get('edge_type', 'control'))

            # Only process control edges for flow routing
            if edge_type == 'resource':
                continue

            if not source or not target:
                continue

            # Build source -> edges index
            if source not in self._edge_index:
                self._edge_index[source] = []
            self._edge_index[source].append(edge)

            # Build event route: "source:handle" -> target
            route_key = f"{source}:{source_handle}"
            self._event_routes[route_key] = target

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
            events_to_try.extend(['default', 'success'])

            for try_event in events_to_try:
                if try_event and try_event in step_conns and step_conns[try_event]:
                    next_step_id = step_conns[try_event][0]
                    logger.debug(f"Connections routing: {step_id}.connections.{try_event} -> {next_step_id}")
                    break

        # Priority 2: Edge-based routing (v1.1)
        if not next_step_id and event and self._event_routes:
            route_key = f"{step_id}:{event}"
            if route_key in self._event_routes:
                next_step_id = self._event_routes[route_key]
                logger.debug(f"Edge routing: {route_key} -> {next_step_id}")

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
