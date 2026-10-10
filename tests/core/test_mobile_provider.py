"""Standalone Core validator; no Cloud or physical equipment needed."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.mobile_provider import execute

REQ = {
    "schema": "flyto2.execution.v1",
    "invocation_id": "core-validation-123",
    "operation_id": "core-operation-123",
    "capability": "core.workflow.validate",
    "revision": 1,
    "requested_at": "2026-10-10T00:00:00Z",
    "input": {
        "nodes": [{"id": "n1", "module_id": "http.get", "params": {}}],
        "edges": [],
    },
}


def test_actual_core_validator_and_graph_fingerprint():
    result = execute(REQ)
    assert result["status"] == "success"
    assert isinstance(result["output"]["valid"], bool)
    assert result["output"]["node_count"] == 1
    assert result["evidence"][0]["kind"] == "workflow_graph_sha256"
    assert result["evidence"][0]["ref"].startswith("sha256:")
    assert "mission_complete" not in result["output"]


def test_unknown_modules_are_not_fabricated():
    data = {**REQ, "input": {
        "nodes": [{"id": "n1", "module_id": "unknown.fake", "params": {}}],
        "edges": [],
    }}
    result = execute(data)
    assert result["status"] == "success"  # Validation ran, NOT workflow.
    assert result["output"]["valid"] is False
    assert len(result["output"]["errors"]) >= 1


@pytest.mark.parametrize("input_", [
    {"nodes": [], "edges": []},
    {"nodes": [{"id": "n1", "module_id": "http.get", "params": {}}] * 41,
     "edges": []},
    {"nodes": [{"id": "../escape", "module_id": "http.get", "params": {}}],
     "edges": []},
    {"nodes": [{"id": "n1", "module_id": "http.get"}],
     "edges": [{"id": "edge", "source": "n1", "target": "n2"}]},
])
def test_bounded_graph_and_dangling_edges_fail_closed(input_):
    with pytest.raises(ValueError):
        execute({**REQ, "input": input_})


def test_cli_consumes_real_wire_contract_without_cloud():
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "core.mobile_provider"],
        input=json.dumps(REQ), text=True, capture_output=True,
        timeout=15, check=False, env=env,
    )
    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["invocation_id"] == REQ["invocation_id"]
    assert record["status"] == "success"
