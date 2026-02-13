#!/usr/bin/env python3
"""
flyto-core Agent Demo: Deterministic Browser Research

Demonstrates:
1. Task planning → workflow selection
2. 10-step browser workflow execution
3. Full evidence collection (context snapshots per step)
4. Execution trace with timing
5. Replay from any failed step

Usage:
    # Direct execution (no server needed):
    python examples/agent_demo/run.py

    # Or via HTTP API:
    flyto serve &
    curl -X POST http://localhost:8333/v1/workflow/run \
      -H 'Content-Type: application/json' \
      -d @examples/agent_demo/workflows/browser_research.yaml
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

# Ensure src/ is on path
SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def print_header(text: str):
    width = 60
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def print_step(index: int, step_id: str, module_id: str, status: str, duration_ms: int):
    icon = "OK" if status == "success" else "FAIL"
    print(f"  [{icon}] Step {index+1:2d}: {step_id:20s} ({module_id}) — {duration_ms}ms")


async def main():
    import yaml
    from core.engine import WorkflowEngine
    from core.engine.evidence import EvidenceStore, create_evidence_store
    from core.api.evidence_hooks import APIEvidenceHooks

    # ── 1. Plan ──────────────────────────────────────────────────────
    print_header("flyto-core Agent Demo")
    print("  Task: 'Research top Hacker News articles'")

    from planner import SimplePlanner
    planner = SimplePlanner()
    workflow = planner.plan("research top news articles")

    if not workflow:
        print("  ERROR: No matching workflow found.")
        sys.exit(1)

    print(f"  Workflow: {workflow.get('name')}")
    print(f"  Steps: {len(workflow.get('steps', []))}")

    # ── 2. Execute ───────────────────────────────────────────────────
    print_header("Executing Workflow")

    execution_id = f"exec_{uuid.uuid4().hex[:12]}"
    evidence_path = Path("./evidence")
    evidence_store = create_evidence_store(evidence_path)
    hooks = APIEvidenceHooks(evidence_store, execution_id)

    engine = WorkflowEngine(
        workflow=workflow,
        params={},
        hooks=hooks,
        enable_trace=True,
    )

    try:
        result = await engine.execute()
        print(f"\n  Status: COMPLETED")
    except Exception as e:
        print(f"\n  Status: FAILED — {e}")
        result = None

    # ── 3. Trace Summary ─────────────────────────────────────────────
    print_header("Execution Trace")

    trace = engine.get_execution_trace_dict()
    if trace:
        print(f"  Execution ID: {execution_id}")
        print(f"  Duration: {trace.get('durationMs', 0)}ms")
        print(f"  Status: {trace.get('status', 'unknown')}")
        print()
        for i, step in enumerate(trace.get("steps", [])):
            print_step(
                i,
                step.get("stepId", "?"),
                step.get("moduleId", "?"),
                step.get("status", "?"),
                step.get("durationMs", 0),
            )

    # ── 4. Evidence Summary ──────────────────────────────────────────
    print_header("Evidence")

    evidence_list = await evidence_store.load_evidence(execution_id)
    print(f"  Evidence records: {len(evidence_list)}")
    print(f"  Evidence path: {evidence_path / execution_id}")

    if evidence_list:
        print()
        for ev in evidence_list:
            ctx_keys = len(ev.context_after)
            print(f"  {ev.step_id:20s} — {ev.status:7s} — "
                  f"context keys after: {ctx_keys} — {ev.duration_ms}ms")

    # ── 5. Save workflow for replay ──────────────────────────────────
    exec_dir = evidence_store.get_execution_dir(execution_id)
    wf_path = exec_dir / "workflow.json"
    with open(wf_path, "w") as f:
        json.dump(workflow, f, indent=2)
    print(f"\n  Workflow saved to: {wf_path}")

    # ── Done ─────────────────────────────────────────────────────────
    print_header("Done")
    print(f"  To replay a failed step:")
    print(f"    curl -X POST http://localhost:8333/v1/workflow/{execution_id}/replay/{{step_id}}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
