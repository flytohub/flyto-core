"""
Variable Catalog Builder

Builds VarCatalog for a node based on workflow graph and optional runtime context.
Supports both edit-time (schema-based) and runtime (trace-based) introspection.

Version: 1.0.0
"""

import logging
from typing import Any, Dict, List, Optional, Set

from ..sdk.models import (
    IntrospectionMode,
    NodeVarInfo,
    PortVarInfo,
    VarAvailability,
    VarCatalog,
    VarInfo,
    VarSource,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default port names
DEFAULT_INPUT_PORT = "main"
DEFAULT_OUTPUT_PORT = "output"

# Type mapping from schema types to simplified types
TYPE_MAP: Dict[str, str] = {
    "string": "string",
    "text": "string",
    "number": "number",
    "integer": "number",
    "float": "number",
    "boolean": "boolean",
    "bool": "boolean",
    "object": "object",
    "dict": "object",
    "array": "array",
    "list": "array",
}

# Branch/Switch module patterns
BRANCH_MODULES = {
    "flow.branch",
    "flow.switch",
    "flow.condition",
}

# Merge module patterns
MERGE_MODULES = {
    "flow.merge",
    "flow.join",
}


# =============================================================================
# Graph Analyzer
# =============================================================================

class GraphAnalyzer:
    """Analyzes workflow graph for reachability and data flow"""

    def __init__(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ):
        self._nodes = {n.get("id", ""): n for n in nodes if n.get("id")}
        self._edges = edges

        # Build adjacency maps
        self._incoming: Dict[str, List[Dict[str, Any]]] = {}
        self._outgoing: Dict[str, List[Dict[str, Any]]] = {}

        for edge in edges:
            source = edge.get("source", "")
            target = edge.get("target", "")

            if target not in self._incoming:
                self._incoming[target] = []
            self._incoming[target].append(edge)

            if source not in self._outgoing:
                self._outgoing[source] = []
            self._outgoing[source].append(edge)

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node by ID"""
        return self._nodes.get(node_id)

    def get_upstream_nodes(self, node_id: str) -> Set[str]:
        """Get all nodes that are upstream of the given node"""
        visited: Set[str] = set()
        queue = [node_id]

        while queue:
            current = queue.pop(0)
            for edge in self._incoming.get(current, []):
                source = edge.get("source", "")
                if source and source not in visited:
                    visited.add(source)
                    queue.append(source)

        return visited

    def get_upstream_with_branches(self, node_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Get upstream nodes with branch information.

        Returns dict of node_id -> {
            'module_id': str,
            'is_conditional': bool,
            'branch_source': Optional[str],  # The branch/switch node ID
            'branch_port': Optional[str],    # The port taken (true/false/case_X)
        }
        """
        result: Dict[str, Dict[str, Any]] = {}
        visited: Set[str] = set()
        # Queue of (node_id, is_conditional, branch_source, branch_port)
        queue: List[tuple] = [(node_id, False, None, None)]

        while queue:
            current, is_cond, branch_src, branch_port = queue.pop(0)

            for edge in self._incoming.get(current, []):
                source = edge.get("source", "")
                source_handle = edge.get("sourceHandle", DEFAULT_OUTPUT_PORT)

                if not source or source in visited:
                    continue

                visited.add(source)
                module_id = self.get_module_id(source)

                # Check if this is a branch/switch node
                is_branch = module_id in BRANCH_MODULES

                # Nodes downstream of a branch are conditional
                new_is_cond = is_cond or is_branch
                new_branch_src = source if is_branch else branch_src
                new_branch_port = source_handle if is_branch else branch_port

                result[source] = {
                    'module_id': module_id,
                    'is_conditional': new_is_cond,
                    'branch_source': new_branch_src,
                    'branch_port': new_branch_port,
                }

                queue.append((source, new_is_cond, new_branch_src, new_branch_port))

        return result

    def is_branch_node(self, node_id: str) -> bool:
        """Check if a node is a branch/switch node"""
        module_id = self.get_module_id(node_id)
        return module_id in BRANCH_MODULES

    def is_merge_node(self, node_id: str) -> bool:
        """Check if a node is a merge node"""
        module_id = self.get_module_id(node_id)
        return module_id in MERGE_MODULES

    def get_branch_ports(self, node_id: str) -> List[str]:
        """Get output ports of a branch/switch node"""
        module_id = self.get_module_id(node_id)
        schema = SchemaIntrospector().get_module_schema(module_id)
        output_ports = schema.get("output_ports", [])
        return [p.get("id", "output") for p in output_ports]

    def get_direct_inputs(self, node_id: str) -> List[Dict[str, Any]]:
        """Get edges directly connecting to the node"""
        return self._incoming.get(node_id, [])

    def get_module_id(self, node_id: str) -> str:
        """Get module ID for a node"""
        node = self._nodes.get(node_id, {})
        data = node.get("data", node)
        return data.get("module", data.get("module_id", ""))


# =============================================================================
# Schema Introspector
# =============================================================================

class SchemaIntrospector:
    """Introspects module schemas for type information"""

    def __init__(self):
        self._module_cache: Dict[str, Dict[str, Any]] = {}

    def get_module_schema(self, module_id: str) -> Dict[str, Any]:
        """Get schema for a module"""
        if module_id in self._module_cache:
            return self._module_cache[module_id]

        try:
            from core.modules.registry import get_registry
            registry = get_registry()
            meta = registry.get_module_metadata(module_id)
            if meta:
                self._module_cache[module_id] = meta
                return meta
        except Exception as e:
            logger.debug(f"Could not get schema for {module_id}: {e}")

        return {}

    def get_output_schema(self, module_id: str) -> Dict[str, Any]:
        """Get output schema for a module"""
        schema = self.get_module_schema(module_id)
        return schema.get("output_schema", {})

    def get_output_ports(self, module_id: str) -> List[Dict[str, Any]]:
        """Get output port definitions for a module"""
        schema = self.get_module_schema(module_id)
        return schema.get("output_ports", [])

    def get_input_ports(self, module_id: str) -> List[Dict[str, Any]]:
        """Get input port definitions for a module"""
        schema = self.get_module_schema(module_id)
        return schema.get("input_ports", [])

    def infer_type_from_value(self, value: Any) -> str:
        """Infer type from a runtime value"""
        if value is None:
            return "any"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "number"
        elif isinstance(value, float):
            return "number"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, dict):
            return "object"
        elif isinstance(value, (list, tuple)):
            return "array"
        else:
            return "any"


# =============================================================================
# Catalog Builder
# =============================================================================

class CatalogBuilder:
    """Builds VarCatalog for a node"""

    def __init__(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        params: Optional[Dict[str, Any]] = None,
        context_snapshot: Optional[Dict[str, Any]] = None,
    ):
        self._graph = GraphAnalyzer(nodes, edges)
        self._schema = SchemaIntrospector()
        self._params = params or {}
        self._snapshot = context_snapshot or {}

    def build(
        self,
        node_id: str,
        mode: IntrospectionMode = IntrospectionMode.EDIT,
    ) -> VarCatalog:
        """
        Build VarCatalog for a node.

        Args:
            node_id: Target node ID
            mode: Introspection mode (edit or runtime)

        Returns:
            VarCatalog with available variables
        """
        catalog = VarCatalog(
            mode=mode,
            node_id=node_id,
        )

        # Build inputs
        catalog.inputs = self._build_inputs(node_id, mode)

        # Build upstream nodes
        catalog.nodes = self._build_nodes(node_id, mode)

        # Build params
        catalog.params = self._build_params()

        # Build globals
        catalog.globals = self._build_globals()

        # Build env
        catalog.env = self._build_env()

        return catalog

    def _build_inputs(
        self,
        node_id: str,
        mode: IntrospectionMode,
    ) -> Dict[str, PortVarInfo]:
        """Build input port variables"""
        result: Dict[str, PortVarInfo] = {}

        # Get node's input port definitions
        module_id = self._graph.get_module_id(node_id)
        input_ports = self._schema.get_input_ports(module_id)

        # Get direct incoming edges
        direct_inputs = self._graph.get_direct_inputs(node_id)

        for port_def in input_ports:
            port_id = port_def.get("id", DEFAULT_INPUT_PORT)

            # Find edge connecting to this port
            edge = next(
                (e for e in direct_inputs
                 if e.get("targetHandle", DEFAULT_INPUT_PORT) == port_id),
                None
            )

            port_info = PortVarInfo(
                port_id=port_id,
                var_type=port_def.get("data_type", "any"),
                description=port_def.get("description", ""),
            )

            # Get example from snapshot if runtime mode
            if mode == IntrospectionMode.RUNTIME and edge:
                source_id = edge.get("source", "")
                source_handle = edge.get("sourceHandle", DEFAULT_OUTPUT_PORT)
                snapshot_key = f"{source_id}.{source_handle}"

                if snapshot_key in self._snapshot:
                    port_info.example = self._snapshot[snapshot_key]

            # Build fields from schema or snapshot
            port_info.fields = self._build_fields(
                port_id,
                port_info.var_type,
                mode,
                edge,
            )

            result[port_id] = port_info

        # Ensure 'main' port exists for {{input}} shorthand
        if DEFAULT_INPUT_PORT not in result:
            result[DEFAULT_INPUT_PORT] = PortVarInfo(
                port_id=DEFAULT_INPUT_PORT,
                var_type="any",
                description="Main input",
            )

        return result

    def _build_nodes(
        self,
        node_id: str,
        mode: IntrospectionMode,
    ) -> Dict[str, NodeVarInfo]:
        """Build upstream node variables with branch awareness"""
        result: Dict[str, NodeVarInfo] = {}

        # Get upstream with branch info
        upstream_info = self._graph.get_upstream_with_branches(node_id)

        for up_id, branch_info in upstream_info.items():
            module_id = branch_info['module_id']
            is_conditional = branch_info['is_conditional']
            branch_source = branch_info.get('branch_source')
            branch_port = branch_info.get('branch_port')

            node_info = NodeVarInfo(
                node_id=up_id,
                node_type=module_id,
                is_reachable=True,
            )

            # Mark conditional availability
            availability = (
                VarAvailability.CONDITIONAL
                if is_conditional
                else VarAvailability.BOTH
            )

            # Build ports from schema
            output_ports = self._schema.get_output_ports(module_id)

            for port_def in output_ports:
                port_id = port_def.get("id", DEFAULT_OUTPUT_PORT)

                port_info = PortVarInfo(
                    port_id=port_id,
                    var_type=port_def.get("data_type", "any"),
                    description=port_def.get("description", ""),
                )

                # Add branch context to description for conditional vars
                if is_conditional and branch_source and branch_port:
                    port_info.description = (
                        f"{port_info.description} "
                        f"(via {branch_source}.{branch_port})"
                    ).strip()

                # Get example from snapshot if runtime mode
                if mode == IntrospectionMode.RUNTIME:
                    snapshot_key = f"{up_id}.{port_id}"
                    if snapshot_key in self._snapshot:
                        port_info.example = self._snapshot[snapshot_key]
                        # Infer fields from actual value
                        if isinstance(port_info.example, dict):
                            port_info.fields = self._infer_fields_from_value(
                                port_info.example,
                                f"{up_id}.{port_id}",
                                availability=availability,
                            )

                node_info.ports[port_id] = port_info

            # Ensure default output port exists
            if DEFAULT_OUTPUT_PORT not in node_info.ports:
                node_info.ports[DEFAULT_OUTPUT_PORT] = PortVarInfo(
                    port_id=DEFAULT_OUTPUT_PORT,
                    var_type="any",
                    description="Output",
                )

            # Store branch metadata in node info
            if is_conditional:
                node_info.is_conditional = True
                node_info.branch_source = branch_source
                node_info.branch_port = branch_port

            result[up_id] = node_info

        return result

    def _build_params(self) -> Dict[str, VarInfo]:
        """Build workflow parameter variables"""
        result: Dict[str, VarInfo] = {}

        for key, value in self._params.items():
            result[key] = VarInfo(
                path=f"params.{key}",
                var_type=self._schema.infer_type_from_value(value),
                description=f"Workflow parameter: {key}",
                example=value,
                source=VarSource.TRACE if value is not None else VarSource.SCHEMA,
                availability=VarAvailability.BOTH,
            )

        return result

    def _build_globals(self) -> Dict[str, VarInfo]:
        """Build global variables"""
        result: Dict[str, VarInfo] = {}

        # Add workflow metadata if available
        if "workflow" in self._snapshot:
            wf = self._snapshot["workflow"]
            for key in ["id", "name", "version"]:
                if key in wf:
                    result[f"workflow.{key}"] = VarInfo(
                        path=f"global.workflow.{key}",
                        var_type="string",
                        description=f"Workflow {key}",
                        example=wf.get(key),
                        source=VarSource.TRACE,
                        availability=VarAvailability.BOTH,
                    )

        return result

    def _build_env(self) -> Dict[str, VarInfo]:
        """Build environment variables (filtered)"""
        import os
        from ..context.layers import ENV_ALLOWLIST

        result: Dict[str, VarInfo] = {}

        for key in ENV_ALLOWLIST:
            value = os.environ.get(key)
            if value is not None:
                result[key] = VarInfo(
                    path=f"env.{key}",
                    var_type="string",
                    description=f"Environment variable: {key}",
                    example=value,
                    source=VarSource.TRACE,
                    availability=VarAvailability.BOTH,
                )

        return result

    def _build_fields(
        self,
        port_id: str,
        port_type: str,
        mode: IntrospectionMode,
        edge: Optional[Dict[str, Any]],
    ) -> Dict[str, VarInfo]:
        """Build field variables for a port"""
        result: Dict[str, VarInfo] = {}

        if mode == IntrospectionMode.RUNTIME and edge:
            source_id = edge.get("source", "")
            source_handle = edge.get("sourceHandle", DEFAULT_OUTPUT_PORT)
            snapshot_key = f"{source_id}.{source_handle}"

            if snapshot_key in self._snapshot:
                value = self._snapshot[snapshot_key]
                if isinstance(value, dict):
                    result = self._infer_fields_from_value(
                        value,
                        f"input.{port_id}" if port_id != DEFAULT_INPUT_PORT else "input",
                    )

        return result

    def _infer_fields_from_value(
        self,
        value: Dict[str, Any],
        prefix: str,
        depth: int = 0,
        max_depth: int = 3,
        availability: VarAvailability = VarAvailability.RUNTIME,
    ) -> Dict[str, VarInfo]:
        """Infer field structure from a runtime value"""
        if depth >= max_depth:
            return {}

        result: Dict[str, VarInfo] = {}

        for key, val in value.items():
            path = f"{prefix}.{key}"
            var_type = self._schema.infer_type_from_value(val)

            result[key] = VarInfo(
                path=path,
                var_type=var_type,
                example=val if not isinstance(val, (dict, list)) else None,
                source=VarSource.TRACE,
                confidence=1.0,
                availability=availability,
            )

            # Recurse into nested objects
            if isinstance(val, dict) and depth < max_depth:
                nested = self._infer_fields_from_value(
                    val,
                    path,
                    depth + 1,
                    max_depth,
                    availability,
                )
                for nested_key, nested_info in nested.items():
                    result[f"{key}.{nested_key}"] = nested_info

        return result


# =============================================================================
# Factory Functions
# =============================================================================

def build_catalog(
    workflow: Dict[str, Any],
    node_id: str,
    mode: IntrospectionMode = IntrospectionMode.EDIT,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> VarCatalog:
    """
    Build VarCatalog for a node in a workflow.

    Args:
        workflow: Workflow definition with nodes and edges
        node_id: Target node ID
        mode: Introspection mode
        context_snapshot: Optional runtime context snapshot

    Returns:
        VarCatalog with available variables
    """
    nodes = workflow.get("nodes", [])
    edges = workflow.get("edges", [])
    params = workflow.get("params", {})

    # Handle steps format (linear workflows)
    if not nodes and workflow.get("steps"):
        nodes, edges = _convert_steps_to_graph(workflow.get("steps", []))

    builder = CatalogBuilder(
        nodes=nodes,
        edges=edges,
        params=params,
        context_snapshot=context_snapshot,
    )

    return builder.build(node_id, mode)


def _convert_steps_to_graph(
    steps: List[Dict[str, Any]],
) -> tuple:
    """Convert steps format to nodes/edges"""
    nodes = []
    edges = []

    for i, step in enumerate(steps):
        node_id = step.get("id", f"step_{i}")
        nodes.append({
            "id": node_id,
            "data": step,
        })

        if i < len(steps) - 1:
            next_id = steps[i + 1].get("id", f"step_{i + 1}")
            edges.append({
                "id": f"edge_{i}",
                "source": node_id,
                "target": next_id,
            })

    return nodes, edges
