# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Workflow Routing

Edge-based routing and step connection handling for Workflow Spec v1.2.
"""

import logging
from typing import Any, Dict, List, Set

from ...canvas_handles import (
    GENERIC_HANDLES,
    INPUT,
    OUTPUT,
    exit_edge_conflicts,
    handle_events,
    ordinary_port,
    port_event,
    resolve_port,
)

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

        # Resource edge index: target_id -> {port_name: [source_ids]}
        self._resource_edges: Dict[str, Dict[str, List[str]]] = {}

        # Set of step IDs that are resource sources (sub-nodes like ai.tool, ai.model)
        self._resource_source_ids: Set[str] = set()

        # Steps some other step reaches through a routed exit (a branch's
        # true/false, a loop's body or done, an error exit): entered only
        # through that exit, never by stepping on in list order.
        self._routed_targets: Set[str] = set()
        # source_id -> the steps it names as its ordinary way on
        self._successors: Dict[str, Set[str]] = {}
        # A document that draws its plain edges is read as a graph: a step goes
        # on along its ordinary edge, and a path with no edge ends there.
        self._graph_mode = False
        # Open forks, innermost last: the branch targets still to run and the
        # join step the branches converge on (see flow.fork's contract).
        self._fork_frames: List[Dict[str, Any]] = []

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
        self._resource_edges = {}
        self._resource_source_ids = set()
        self._routed_targets = set()
        self._successors = {}
        self._fork_frames = []
        self._graph_mode = any(
            e.get('source') and e.get('target') and (e.get('edge_type') or (e.get('data') or {}).get('edgeType')) != 'resource'
            for e in edges or []
        )

        step_map = self._step_map

        # Build routes from edges (v1.1 pattern)
        for edge in edges:
            source = edge.get('source', '')
            source_handle = edge.get('sourceHandle', 'success')
            target = edge.get('target', '')
            # Check edge type: top-level 'type'/'edge_type' or nested 'data.edgeType'/'data.edge_type'
            edge_data = edge.get('data') or {}
            edge_type = (
                edge.get('edge_type')
                or edge_data.get('edgeType')
                or edge_data.get('edge_type')
                or edge.get('type', 'data')
            )

            # Track resource edges separately (for AI Agent sub-nodes)
            if edge_type == 'resource':
                if target and source:
                    target_handle = edge.get('targetHandle') or edge.get('target_handle') or ''
                    # Normalize handle: "target-model" -> "model"
                    port_name = target_handle.replace('target-', '') if target_handle.startswith('target-') else (target_handle or 'input')
                    if target not in self._resource_edges:
                        self._resource_edges[target] = {}
                    if port_name not in self._resource_edges[target]:
                        self._resource_edges[target][port_name] = []
                    if source not in self._resource_edges[target][port_name]:
                        self._resource_edges[target][port_name].append(source)
                    self._resource_source_ids.add(source)
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
            if self._is_routed_exit(source_handle, step_map.get(source)):
                self._routed_targets.add(target)
            else:
                self._successors.setdefault(source, set()).add(target)

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
                        if self._is_routed_exit(port_name, step):
                            self._routed_targets.update(targets)
                        else:
                            self._successors.setdefault(step_id, set()).update(targets)
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

    def exit_conflicts(self, edges: List[Dict[str, Any]], steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Edges and connection targets beyond what their exit allows (core.canvas_handles)."""
        lines = list(edges or [])
        for step in steps:
            for port_name, targets in (step.get('connections') or {}).items():
                for target in [targets] if isinstance(targets, str) else list(targets or []):
                    lines.append({'id': f"{step.get('id')}.{port_name}->{target}", 'source': step.get('id'),
                                  'sourceHandle': port_name, 'target': target})
        return exit_edge_conflicts(lines, lambda step_id: self._declared_output_ports(self._step_map.get(step_id)))

    def _is_routed_exit(self, handle: str, step: Dict[str, Any] = None) -> bool:
        """Whether leaving ``step`` by ``handle`` is a routed exit, not its ordinary way on."""
        if not handle or handle in GENERIC_HANDLES[OUTPUT] or handle in ('success', 'default'):
            return False
        ports = self._declared_output_ports(step)
        port = resolve_port(ports, handle, OUTPUT)
        if port is None:
            return True
        return port is not ordinary_port(ports, OUTPUT)

    def next_in_order(self, step_id: str, current_idx: int, steps_count: int) -> int:
        """The index the run steps on to when ``step_id`` names no route of its own.

        A document that draws its plain edges goes on along the step's ordinary
        edge; a step with none ends its path (the next fork branch, the join,
        or the end of the run). A document without edges runs in list order,
        skipping every step another step reaches only through a routed exit,
        unless this step names it as its ordinary successor.
        """
        own = self._successors.get(step_id, set())
        if self._graph_mode:
            successor = next(iter(sorted(own, key=lambda s: self._step_index.get(s, steps_count))), None)
            if successor is None or successor not in self._step_index:
                return self.path_end(steps_count)
            index = self._step_index[successor]
            if self._fork_frames and self._is_join(successor):
                self._fork_frames[-1]['join'] = index
                return self.path_end(steps_count)
            return index
        order = sorted(self._step_index, key=self._step_index.get)
        index = current_idx + 1
        while index < steps_count and index < len(order):
            candidate = order[index]
            if candidate not in self._routed_targets or candidate in own:
                return index
            index += 1
        return index

    # -----------------------------------------------------------------
    # Forks (flow.fork): every branch, in exit order, then the join
    # -----------------------------------------------------------------

    def start_fork(self, step_id: str, current_idx: int, steps_count: int) -> int:
        """Begin a fork: run its first branch now and keep the rest for when it ends.

        Branches are the step's exits whose declared event is ``fork``, in the
        order the module declares them. A fork with no connected branch ends
        its path.
        """
        ports = self._declared_output_ports(self._step_map.get(step_id))
        order = [p['id'] for p in ports if isinstance(p, dict) and p.get('id') and port_event(p) == 'fork']
        targets = []
        for edge in self._edge_index.get(step_id, []):
            port = resolve_port(ports, edge.get('sourceHandle') or '', OUTPUT)
            if port is not None and port['id'] in order and edge.get('target') in self._step_index:
                targets.append((order.index(port['id']), self._step_index[edge['target']]))
        targets.sort()
        if not targets:
            return self.path_end(steps_count)
        self._fork_frames.append({'step_id': step_id, 'pending': [index for _, index in targets[1:]], 'join': None})
        return targets[0][1]

    def path_end(self, steps_count: int) -> int:
        """Where the run goes when a path ends: the open fork's next branch, its join, or the end."""
        while self._fork_frames:
            frame = self._fork_frames[-1]
            if frame['pending']:
                return frame['pending'].pop(0)
            self._fork_frames.pop()
            if frame['join'] is not None:
                return frame['join']
        return steps_count

    def _is_join(self, step_id: str) -> bool:
        """A step that declares more than one input port joins paths (flow.merge, flow.join)."""
        return len(self.declared_input_ports(self._step_map.get(step_id))) > 1

    @staticmethod
    def declared_input_ports(step: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """The input ports the step's module declares, or none when it is not registered."""
        module_id = (step or {}).get('module')
        if not isinstance(module_id, str) or not module_id:
            return []
        try:
            from ...modules.registry import ModuleRegistry
            meta = ModuleRegistry.get_metadata(module_id) or {}
        except Exception:  # an unregistered module declares nothing
            return []
        return [p for p in meta.get('input_ports') or [] if isinstance(p, dict) and p.get('id')]

    def inputs_by_port(self, step_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """For a joining step: each declared input port's value, from the edge drawn to it."""
        ports = self.declared_input_ports(self._step_map.get(step_id))
        if len(ports) < 2:
            return {}
        values: Dict[str, Any] = {}
        unnamed = []
        for edge in self._incoming_edges.get(step_id, []):
            handle = edge.get('targetHandle') or edge.get('target_handle') or ''
            port = resolve_port(ports, handle, INPUT) if handle else None
            if port is None:
                unnamed.append(edge)
            elif edge.get('source') in context:
                values[port['id']] = context[edge['source']]
        # An edge drawn without naming an input takes the first one still free.
        free = [p['id'] for p in ports if p['id'] not in values]
        for edge, port_id in zip(unnamed, free, strict=False):
            if edge.get('source') in context:
                values[port_id] = context[edge['source']]
        return values

    def has_route(self, step_id: str, event: str) -> bool:
        """Whether the step names a route for ``event`` (a connection or an edge)."""
        return bool((self._step_connections.get(step_id) or {}).get(event)) or f"{step_id}:{event}" in self._event_routes

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

    # -----------------------------------------------------------------
    # Error edge validation
    # -----------------------------------------------------------------

    def validate_error_edges(self) -> List[Dict[str, Any]]:
        """
        Validate all error edges in the edge index.

        Checks:
        - Error edge should not connect back to the same node (self-loop)
        - Error edge should not create a cycle (target is ancestor of source)
        - Warn if error edge targets a flow control node (loop, branch, switch)

        Returns:
            List of warning dicts: [{"level": "warning", "message": "..."}]
        """
        # Import here to avoid circular imports
        from ..flow_control import FLOW_CONTROL_MODULES

        warnings: List[Dict[str, Any]] = []

        for source_id, edges in self._edge_index.items():
            for edge in edges:
                source_handle = edge.get('sourceHandle', '')
                if source_handle != 'source-error':
                    continue

                target_id = edge.get('target', '')
                if not target_id:
                    continue

                # Check 1: self-loop (error edge back to the same node)
                if target_id == source_id:
                    warnings.append({
                        'level': 'warning',
                        'message': (
                            f"Error edge from '{source_id}' connects back to itself. "
                            f"This will cause an infinite retry loop if the step keeps failing."
                        ),
                    })
                    continue

                # Check 2: cycle detection (target is ancestor of source)
                if self._is_ancestor(target_id, source_id):
                    warnings.append({
                        'level': 'warning',
                        'message': (
                            f"Error edge from '{source_id}' to '{target_id}' creates a cycle. "
                            f"If the step keeps failing, this may cause an infinite loop."
                        ),
                    })

                # Check 3: error edge targets a flow control node
                target_step = self._step_map.get(target_id)
                if target_step:
                    target_module = target_step.get('module', '')
                    if target_module in FLOW_CONTROL_MODULES:
                        warnings.append({
                            'level': 'warning',
                            'message': (
                                f"Error edge from '{source_id}' connects to flow control "
                                f"node '{target_id}' (module: {target_module}). "
                                f"Error handling via flow control nodes may produce "
                                f"unexpected routing behavior."
                            ),
                        })

        return warnings

    def _is_ancestor(self, candidate_id: str, node_id: str) -> bool:
        """
        Check if candidate_id is an ancestor of node_id by walking
        incoming edges (reverse direction). Uses BFS with visited set
        to avoid infinite loops in cyclic graphs.

        Args:
            candidate_id: The potential ancestor node
            node_id: The node to check ancestors of

        Returns:
            True if candidate_id can reach node_id via forward edges
            (i.e. candidate_id is upstream of node_id)
        """
        visited: Set[str] = set()
        queue: List[str] = [node_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            incoming = self._incoming_edges.get(current, [])
            for edge in incoming:
                source = edge.get('source', '')
                if not source:
                    continue
                if source == candidate_id:
                    return True
                if source not in visited:
                    queue.append(source)

        return False

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

        return self.next_in_order(step_id, current_idx, len(self._step_index))

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
            # Only data and iterate edges pass items
            if data_edges_only and edge_type not in ('data', 'iterate'):
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

    def get_resource_sources(self, step_id: str) -> Dict[str, List[str]]:
        """
        Get resource sub-node sources for a step.

        Returns:
            Dict mapping port name to list of source step IDs
            e.g. {"model": ["ai_model_1"], "tools": ["tool_1", "tool_2"]}
        """
        return self._resource_edges.get(step_id, {})

    def is_resource_source(self, step_id: str) -> bool:
        """Check if a step is a resource sub-node (only connects via resource edges)."""
        return step_id in self._resource_source_ids

    def has_outgoing_edges(self, step_id: str) -> bool:
        """Check if a step has outgoing edges (used by loop-back detection)."""
        return step_id in self._edge_index

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

        normalized = handle_id[len('source-'):] if handle_id.startswith('source-') else handle_id
        if normalized.startswith('branch-') or normalized.startswith('branch_'):
            return ['fork', normalized]

        # Which declared port the handle means, and the event that port emits,
        # come from the one table connection validation also reads.
        return handle_events(handle_id, self._declared_output_ports(step))

    @staticmethod
    def _declared_output_ports(step: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """The output ports the step's module declares, or none when it is not registered."""
        module_id = (step or {}).get('module')
        if not isinstance(module_id, str) or not module_id:
            return []
        try:
            from ...modules.registry import ModuleRegistry
            meta = ModuleRegistry.get_metadata(module_id) or {}
        except Exception:  # an unregistered or unloadable module routes by the table alone
            return []
        return list(meta.get('output_ports') or [])

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
