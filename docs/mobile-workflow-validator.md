# Standalone Core workflow validation as a local mobile capability

An optional low-risk capability projects the **real** Flyto2 Core workflow
validator through flyto2.execution.v1. It requires no hosted Flyto2 Cloud,
no Firebase account and no cybersecurity Engine.

The host operator installs flyto-core in an explicit Python environment,
then registers this capability in the Runtime host's installed-adapter
manifest (which the phone cannot modify):

    {
      "schema": "flyto2.local-adapters.v1",
      "adapters": [{
        "capability": {
          "id": "core.workflow.validate",
          "revision": 1,
          "risk_level": "low",
          "approval": "policy",
          "evidence": ["workflow_graph_sha256"]
        },
        "executable": "/absolute/path/to/installed/python3.11",
        "argv": ["-m", "core.mobile_provider"],
        "timeout_ms": 15000
      }]
    }

The host must separately allowlist core.workflow.validate. The local
Flutter App discovers the capability from the actual host manifest, not
from a predefined menu.

Invoke with capability=core.workflow.validate, revision=1, and a payload
containing nodes and edges:

    {
      "nodes": [{"id": "n1", "module_id": "http.get", "params": {}}],
      "edges": []
    }

Input is bounded to 12 KB, 1–40 nodes and 100 edges, with unique bounded
node IDs. Malformed request shapes fail closed. Core validates edges,
module references and node parameters and returns the real valid/errors/
warnings, plus a content SHA-256 reference of the graph submitted.

A successful result only means **validation ran**. It does not guarantee
output.valid=true, and it does not execute a workflow, approve a robot
capability or prove physical mission completion.

Full local AI Space parity requires independent task proposals, planning,
approvals, execution lifecycle, robotic/vehicle adapters and independent
device-observed evidence. This is one reusable Core building block.
