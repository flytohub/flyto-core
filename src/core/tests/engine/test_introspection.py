"""
Unit Tests for Introspection

Tests VarCatalog building for workflow variable introspection.
"""

import pytest
from typing import Any, Dict, List

from core.engine.sdk.models import (
    IntrospectionMode,
    VarAvailability,
    VarSource,
    VarCatalog,
    VarInfo,
    PortVarInfo,
    NodeVarInfo,
)
from core.engine.introspection.catalog import (
    build_catalog,
)


# =============================================================================
# Test Fixtures
# =============================================================================

def create_simple_workflow() -> Dict[str, Any]:
    """Create a simple linear workflow for testing"""
    return {
        "id": "test-workflow",
        "nodes": [
            {
                "id": "trigger",
                "module_id": "core.trigger.webhook",
                "params": {},
            },
            {
                "id": "process",
                "module_id": "data.transform.map",
                "params": {"expression": "{{input}}"},
            },
            {
                "id": "output",
                "module_id": "core.output.json",
                "params": {},
            },
        ],
        "edges": [
            {"source": "trigger", "target": "process"},
            {"source": "process", "target": "output"},
        ],
    }


def create_branching_workflow() -> Dict[str, Any]:
    """Create a workflow with branches"""
    return {
        "id": "branching-workflow",
        "nodes": [
            {
                "id": "start",
                "module_id": "core.trigger.manual",
                "params": {},
            },
            {
                "id": "condition",
                "module_id": "flow.condition",
                "params": {"condition": "{{input.status}} == 'active'"},
            },
            {
                "id": "branch_a",
                "module_id": "data.transform.map",
                "params": {},
            },
            {
                "id": "branch_b",
                "module_id": "data.transform.map",
                "params": {},
            },
            {
                "id": "merge",
                "module_id": "flow.merge",
                "params": {},
            },
        ],
        "edges": [
            {"source": "start", "target": "condition"},
            {"source": "condition", "target": "branch_a", "sourceHandle": "true"},
            {"source": "condition", "target": "branch_b", "sourceHandle": "false"},
            {"source": "branch_a", "target": "merge"},
            {"source": "branch_b", "target": "merge"},
        ],
    }


# =============================================================================
# CatalogBuilder Tests
# =============================================================================

class TestCatalogBuilder:
    """Tests for build_catalog function"""

    def test_build_catalog_edit_mode(self):
        workflow = create_simple_workflow()
        catalog = build_catalog(
            workflow=workflow,
            node_id="process",
            mode=IntrospectionMode.EDIT,
        )

        assert isinstance(catalog, VarCatalog)
        assert catalog.mode == IntrospectionMode.EDIT

    def test_build_catalog_runtime_mode(self):
        workflow = create_simple_workflow()
        context = {
            "trigger": {"ok": True, "data": {"message": "hello"}},
        }
        catalog = build_catalog(
            workflow=workflow,
            node_id="process",
            mode=IntrospectionMode.RUNTIME,
            context_snapshot=context,
        )

        assert catalog.mode == IntrospectionMode.RUNTIME

    def test_catalog_contains_upstream_nodes(self):
        workflow = create_simple_workflow()
        catalog = build_catalog(
            workflow=workflow,
            node_id="output",
            mode=IntrospectionMode.EDIT,
        )

        # Should have outputs from trigger and process
        assert "trigger" in catalog.nodes
        assert "process" in catalog.nodes

    def test_catalog_excludes_downstream_nodes(self):
        workflow = create_simple_workflow()
        catalog = build_catalog(
            workflow=workflow,
            node_id="trigger",
            mode=IntrospectionMode.EDIT,
        )

        # Should NOT have process or output (they're downstream)
        assert "process" not in catalog.nodes
        assert "output" not in catalog.nodes


# =============================================================================
# VarCatalog Model Tests
# =============================================================================

class TestVarCatalogModel:
    """Tests for VarCatalog data model"""

    def test_var_info_creation(self):
        var = VarInfo(
            path="input.data",
            var_type="object",
        )

        assert var.path == "input.data"
        assert var.var_type == "object"

    def test_port_var_info_creation(self):
        port = PortVarInfo(
            port_id="output",
            var_type="object",
            description="Output port",
        )

        assert port.port_id == "output"
        assert port.var_type == "object"

    def test_node_var_info_creation(self):
        node = NodeVarInfo(
            node_id="fetch",
            node_type="http.request",
        )

        assert node.node_id == "fetch"
        assert node.node_type == "http.request"

    def test_var_catalog_creation(self):
        catalog = VarCatalog(
            node_id="process",
            mode=IntrospectionMode.EDIT,
        )

        assert catalog.node_id == "process"
        assert catalog.mode == IntrospectionMode.EDIT


# =============================================================================
# Build Catalog Integration Tests
# =============================================================================

class TestBuildCatalogIntegration:
    """Integration tests for build_catalog function"""

    def test_build_catalog_steps_format(self):
        """Test catalog building from steps format (alternative to nodes/edges)"""
        workflow = {
            "id": "test",
            "steps": [
                {
                    "id": "step1",
                    "module_id": "http.request",
                    "params": {"url": "https://example.com"},
                },
                {
                    "id": "step2",
                    "module_id": "data.transform.map",
                    "params": {"expression": "{{step1.data}}"},
                },
            ],
        }

        catalog = build_catalog(
            workflow=workflow,
            node_id="step2",
            mode=IntrospectionMode.EDIT,
        )

        # Should have step1 as upstream
        assert "step1" in catalog.nodes

    def test_build_catalog_empty_workflow(self):
        """Test with empty workflow"""
        workflow = {"id": "empty", "nodes": [], "edges": []}

        # Should not crash
        catalog = build_catalog(
            workflow=workflow,
            node_id="nonexistent",
            mode=IntrospectionMode.EDIT,
        )
        assert isinstance(catalog, VarCatalog)
