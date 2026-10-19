# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Canvas handles: the one table that says which declared port an edge end means.

A canvas edge names its ends by handle id. Connection validation
(``core.validation.connection``) and the engine's router
(``core.engine.workflow.routing``) both read an edge through this module, so a
save that accepts an edge and a run that follows it can never disagree about
which port, and therefore which emitted event, the edge stands for.

Reading rule, in order, for a handle against a module's declared ports:

1. a port whose ``id`` or declared ``handle_id`` is the handle;
2. a row of ``HANDLE_ALIASES`` naming a port id the module declares;
3. the handle with its side prefix (``source-`` / ``target-``) removed;
4. a generic handle (``GENERIC_HANDLES``) means the module's one ordinary
   port: ``success`` when declared, otherwise the only port that is not a side
   exit. A module with several ordinary ports needs the edge to name one.

Old saved edges keep whatever handle ids they were drawn with; this rule reads
them as they are, so no migration rewrites a stored workflow.
"""

from typing import Any, Dict, Iterable, List, Optional

OUTPUT = 'output'
INPUT = 'input'

#: Side prefix a canvas puts before a declared port id.
SIDE_PREFIX = {OUTPUT: 'source-', INPUT: 'target-'}

#: Handle ids that stand for "this node's ordinary port", whatever it is named.
GENERIC_HANDLES = {
    OUTPUT: frozenset({'output', 'source', 'main'}),
    INPUT: frozenset({'input', 'target', 'in'}),
}

#: Port ids that are a side exit, never what a generic handle means.
SIDE_EXITS = {OUTPUT: frozenset({'error'}), INPUT: frozenset()}

#: Port id a generic handle means when the module declares it.
GENERIC_PREFERRED = {OUTPUT: 'success', INPUT: 'input'}

#: Fixed handle ids a node draws for a named port: (side, handle) -> port id.
HANDLE_ALIASES = {
    (OUTPUT, 'body_out'): 'iterate',
    (OUTPUT, 'done_out'): 'done',
    (OUTPUT, 'item'): 'iterate',
    (OUTPUT, 'source-item'): 'iterate',
}

#: Events a module may emit under another name than its port declares; each
#: maps to the other names a route may have been stored under. Kept for
#: workflows saved before ports declared their events.
EVENT_SYNONYMS = {
    'triggered': ('trigger',),
    'trigger': ('triggered',),
    'merged': ('success',),
    'joined': ('success',),
}


def _ports(ports: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    return [p for p in ports or [] if isinstance(p, dict) and p.get('id')]


def _by_id(ports: List[Dict[str, Any]], port_id: str) -> Optional[Dict[str, Any]]:
    return next((p for p in ports if p.get('id') == port_id), None)


def ordinary_port(ports: Optional[Iterable[Any]], side: str) -> Optional[Dict[str, Any]]:
    """The one port a generic handle on ``side`` means, if the module has exactly one."""
    declared = _ports(ports)
    preferred = _by_id(declared, GENERIC_PREFERRED[side])
    if preferred is not None:
        return preferred
    ordinary = [p for p in declared if p['id'] not in SIDE_EXITS[side]]
    return ordinary[0] if len(ordinary) == 1 else None


def resolve_port(ports: Optional[Iterable[Any]], handle: Optional[str], side: str) -> Optional[Dict[str, Any]]:
    """The declared port an edge end drawn from ``handle`` means, or None."""
    declared = _ports(ports)
    if not declared or not handle:
        return None
    match = _by_id(declared, handle) or next((p for p in declared if p.get('handle_id') == handle), None)
    if match is not None:
        return match
    alias = HANDLE_ALIASES.get((side, handle))
    if alias and _by_id(declared, alias) is not None:
        return _by_id(declared, alias)
    prefix = SIDE_PREFIX[side]
    if handle.startswith(prefix):
        stripped = handle[len(prefix):]
        match = _by_id(declared, stripped) or _by_id(declared, HANDLE_ALIASES.get((side, stripped), ''))
        if match is not None:
            return match
    if handle in GENERIC_HANDLES[side]:
        return ordinary_port(declared, side)
    return None


def port_event(port: Dict[str, Any]) -> str:
    """The event a module emits when it leaves through ``port``."""
    return port.get('event') or port['id']


def handle_events(handle: Optional[str], ports: Optional[Iterable[Any]] = None) -> List[str]:
    """Every event name an output handle may be routed under, most specific first.

    With the module's declared ports this is the resolved port's event. Without
    them (an unknown module, a workflow-local step) the same table is read
    without ports: a generic handle means ``success``, an alias its port id, a
    prefixed handle its bare id.
    """
    if not handle:
        return []
    port = resolve_port(ports, handle, OUTPUT)
    if port is not None:
        names = [port_event(port), port['id']]
    else:
        bare = handle[len(SIDE_PREFIX[OUTPUT]):] if handle.startswith(SIDE_PREFIX[OUTPUT]) else handle
        if handle in GENERIC_HANDLES[OUTPUT] or bare in GENERIC_HANDLES[OUTPUT]:
            names = [GENERIC_PREFERRED[OUTPUT]]
        else:
            names = [HANDLE_ALIASES.get((OUTPUT, handle)) or HANDLE_ALIASES.get((OUTPUT, bare)) or bare]
    for name in list(names):
        names.extend(EVENT_SYNONYMS.get(name, ()))
    return list(dict.fromkeys(names))


#: How many edges may leave one exit when its port does not say: one. Two
#: lines from one exit never say which runs; running several at once is an
#: explicit fork (flow.fork / flow.parallel), choosing is flow.branch /
#: flow.switch. A port that accepts more declares ``max_connections``
#: (``None`` = no limit) in its own contract.
DEFAULT_EXIT_EDGES = 1
#: Edge kinds that are not a step's exit (an AI agent's model/tools wiring).
NON_EXIT_EDGE_TYPES = frozenset({'resource'})


def exit_edge_limit(port: Optional[Dict[str, Any]]) -> Optional[int]:
    """How many edges may leave ``port``: its declared ``max_connections``, else one."""
    if isinstance(port, dict) and 'max_connections' in port:
        return port['max_connections']
    return DEFAULT_EXIT_EDGES


def _edge_kind(edge: Dict[str, Any]) -> str:
    data = edge.get('data') or {}
    return edge.get('edge_type') or data.get('edgeType') or data.get('edge_type') or edge.get('type') or ''


def _edge_source_handle(edge: Dict[str, Any]) -> str:
    return edge.get('sourceHandle') or edge.get('source_handle') or edge.get('from_port') or 'output'


def exit_edge_conflicts(edges: Iterable[Dict[str, Any]], ports_of) -> List[Dict[str, Any]]:
    """Every edge beyond what its exit allows, in document order.

    ``ports_of(node_id)`` returns that node's declared output ports. Each
    conflict names the edge, its source node, the exit (the resolved port id,
    or the handle when the module declares none) and the exit's limit.
    """
    counts: Dict[tuple, int] = {}
    conflicts: List[Dict[str, Any]] = []
    for index, edge in enumerate(edges or []):
        source = edge.get('source')
        if not source or _edge_kind(edge) in NON_EXIT_EDGE_TYPES:
            continue
        handle = _edge_source_handle(edge)
        ports = ports_of(source) or []
        port = resolve_port(ports, handle, OUTPUT)
        exit_id = port['id'] if port else handle
        limit = exit_edge_limit(port)
        key = (source, exit_id)
        counts[key] = counts.get(key, 0) + 1
        if limit is not None and counts[key] > limit:
            conflicts.append({
                'edge_id': edge.get('id', f'edge_{index}'),
                'node_id': source,
                'exit': exit_id,
                'limit': limit,
                'target': edge.get('target'),
            })
    return conflicts
