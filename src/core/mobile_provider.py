"""Read-only Core workflow-validation capability for locally paired devices.

This module runs independently from hosted Flyto2 Cloud, from the separate
cybersecurity Engine, and from device drivers. It does not execute a workflow.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

from core.validation.workflow import validate_workflow

CAPABILITY = "core.workflow.validate"
SCHEMA = "flyto2.execution.v1"
MAX_REQUEST_BYTES = 12000
MAX_NODES = 40
MAX_EDGES = 100
ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _clock() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validated(request: Any) -> tuple[str, list[dict], list[dict]]:
    if not isinstance(request, dict) or request.get("schema") != SCHEMA:
        raise ValueError("invalid_invocation")
    if request.get("capability") != CAPABILITY or request.get("revision") != 1:
        raise ValueError("unsupported_capability")
    for field in ("invocation_id", "operation_id"):
        value = request.get(field)
        if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
            raise ValueError("invalid_" + field)
    arguments = request.get("input")
    if not isinstance(arguments, dict) or set(arguments) != {"nodes", "edges"}:
        raise ValueError("invalid_workflow_arguments")
    nodes, edges = arguments["nodes"], arguments["edges"]
    if (not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES or
            not isinstance(edges, list) or len(edges) > MAX_EDGES):
        raise ValueError("invalid_workflow_size")
    seen = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("invalid_workflow_node")
        name, module_id = node.get("id"), node.get("module_id")
        if (not isinstance(name, str) or not ID_PATTERN.fullmatch(name) or
                name in seen or not isinstance(module_id, str) or
                not ID_PATTERN.fullmatch(module_id) or
                not isinstance(node.get("params", {}), dict)):
            raise ValueError("invalid_workflow_node")
        seen.add(name)
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("invalid_workflow_edge")
        if any(not isinstance(edge.get(field), str) or
               not ID_PATTERN.fullmatch(edge[field])
               for field in ("id", "source", "target")):
            raise ValueError("invalid_workflow_edge")
        if edge["source"] not in seen or edge["target"] not in seen:
            raise ValueError("workflow_dangling_edge")
    return request["invocation_id"], nodes, edges


def execute(request: Any) -> dict[str, Any]:
    """Validate a user-supplied graph using the real Core module registry."""
    invocation_id, nodes, edges = _validated(request)
    started_at = _clock()
    try:
        result = validate_workflow(nodes, edges, validate_params=True)
    except Exception:
        return {
            "schema": SCHEMA,
            "invocation_id": invocation_id,
            "capability": CAPABILITY,
            "revision": 1,
            "status": "failed",
            "started_at": started_at,
            "completed_at": _clock(),
            "output": {},
            "evidence": [],
            "failure": {"code": "core_workflow_validation_unavailable",
                        "retryable": False},
        }

    graph = json.dumps({"nodes": nodes, "edges": edges},
                       sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(graph.encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "invocation_id": invocation_id,
        "capability": CAPABILITY,
        "revision": 1,
        "status": "success",
        "started_at": started_at,
        "completed_at": _clock(),
        "output": {
            "valid": result.valid,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "errors": [
                {"code": str(e.code), "path": e.path, "message": e.message[:300]}
                for e in result.errors[:40]
            ],
            "warnings": [
                {"code": str(w.code), "path": w.path, "message": w.message[:300]}
                for w in result.warnings[:40]
            ],
        },
        # Digest binds the preview result to the reviewed graph. It is NOT
        # evidence of robot motion or completion of this workflow.
        "evidence": [{"kind": "workflow_graph_sha256",
                      "ref": "sha256:" + fingerprint}],
    }


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        print('{"error":"request_oversized"}')
        return 2
    try:
        document = json.loads(raw)
        result = execute(document)
    except (ValueError, TypeError, json.JSONDecodeError):
        print('{"error":"invalid_workflow_invocation"}')
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
