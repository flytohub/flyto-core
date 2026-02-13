#!/usr/bin/env python3
"""
flyto-core Quickstart — see workflow + evidence + replay in 30 seconds.

Usage:
    pip install flyto-core[api]
    python -m core.quickstart
"""

import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

os.environ["FLYTO_VALIDATION_MODE"] = "dev"

# ── Helpers ──────────────────────────────────────────────────────────

G = "\033[32m"  # green
R = "\033[31m"  # red
Y = "\033[33m"  # yellow
C = "\033[36m"  # cyan
D = "\033[90m"  # dim
B = "\033[1m"   # bold
X = "\033[0m"   # reset


def header(title):
    w = 64
    print(f"\n{'─' * w}")
    print(f"  {B}{title}{X}")
    print(f"{'─' * w}")


def ok(msg):
    print(f"  {G}✓{X} {msg}")


def fail(msg):
    print(f"  {R}✗{X} {msg}")


def info(msg):
    print(f"  {D}{msg}{X}")


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    from core.engine import WorkflowEngine
    from core.engine.evidence import create_evidence_store
    from core.api.evidence_hooks import APIEvidenceHooks

    evidence_path = Path("./_quickstart_evidence")
    evidence_store = create_evidence_store(evidence_path)

    # ── 1. Run a 5-step workflow ─────────────────────────────────

    header("1. Execute 5-Step Workflow")

    workflow = {
        "name": "quickstart-demo",
        "steps": [
            {"id": "normalize", "module": "string.uppercase", "params": {"text": "raw input data"}},
            {"id": "clean", "module": "string.trim", "params": {"text": "  messy whitespace  "}},
            {"id": "transform", "module": "string.reverse", "params": {"text": "transform-this"}},
            {"id": "validate", "module": "string.replace",
             "params": {"text": "status:pending", "search": "pending", "replace": "valid"}},
            {"id": "finalize", "module": "string.lowercase", "params": {"text": "FINAL RESULT"}},
        ],
    }

    execution_id = f"exec_{int(time.time())}"
    hooks = APIEvidenceHooks(evidence_store, execution_id)

    engine = WorkflowEngine(
        workflow=workflow,
        params={},
        hooks=hooks,
        enable_trace=True,
    )

    t0 = time.time()
    await engine.execute()
    elapsed = int((time.time() - t0) * 1000)

    trace = engine.get_execution_trace_dict()
    for step in trace.get("steps", []):
        items = step.get("output", {}).get("items", [[]])
        first = items[0][0] if items and items[0] else {}
        result = str(first.get("result", ""))[:30]
        ok(f"{step['stepId']:14s} → {B}{result}{X}")

    print(f"\n  {G}Completed{X} in {Y}{elapsed}ms{X} · {C}{execution_id}{X}")

    # Save workflow for replay
    exec_dir = evidence_store.get_execution_dir(execution_id)
    with open(exec_dir / "workflow.json", "w") as f:
        json.dump(workflow, f, indent=2)

    # ── 2. Show execution trace ──────────────────────────────────

    header("2. Execution Trace")

    fmt = "  {:<4s} {:<14s} {:<20s} {:<9s} {:<s}"
    print(fmt.format("#", "Step", "Module", "Status", "Output"))
    print(f"  {'─' * 58}")
    for i, step in enumerate(trace.get("steps", [])):
        items = step.get("output", {}).get("items", [[]])
        first = items[0][0] if items and items[0] else {}
        result = str(first.get("result", ""))[:24]
        color = G if step["status"] == "success" else R
        print(fmt.format(
            str(i + 1),
            step["stepId"],
            step["moduleId"],
            f"{color}{step['status']}{X}",
            result,
        ))

    # ── 3. Show evidence (state snapshots) ───────────────────────

    header("3. Evidence — Context Snapshots")

    await asyncio.sleep(0.2)  # let async evidence writes flush
    evidence_list = await evidence_store.load_evidence(execution_id)

    for ev in evidence_list:
        before = list(ev.context_before.keys()) if ev.context_before else []
        after = list(ev.context_after.keys()) if ev.context_after else []
        new_keys = [k for k in after if k not in before]

        print(f"\n  {B}{ev.step_id}{X} {D}· {ev.module_id}{X}")
        print(f"    context_before: {D}{{ {', '.join(before) if before else ''} }}{X}")
        print(f"    context_after:  {{ {', '.join(after)} }}")
        if new_keys:
            print(f"    {G}+ {', '.join(new_keys)}{X}")

    info(f"\n  Evidence on disk: {evidence_path / execution_id}/")

    # ── 4. Replay from step 3 ────────────────────────────────────

    header("4. Replay From Step 3")

    from core.engine.replay import create_replay_manager

    replay_manager = create_replay_manager(evidence_path)

    async def workflow_executor(workflow, context, start_step, end_step=None, skip_steps=None, breakpoints=None):
        # start_step is a step ID string — convert to index
        steps = workflow.get("steps", [])
        start_idx = None
        for i, s in enumerate(steps):
            if s.get("id") == start_step:
                start_idx = i
                break

        replay_id = f"replay_{int(time.time())}"
        replay_hooks = APIEvidenceHooks(evidence_store, replay_id)
        replay_engine = WorkflowEngine(
            workflow=workflow,
            params={},
            hooks=replay_hooks,
            enable_trace=True,
            start_step=start_idx,
            initial_context=context,
        )
        await replay_engine.execute()
        return {
            "ok": True,
            "execution_id": replay_id,
            "steps_executed": len(replay_engine.execution_log),
        }

    result = await replay_manager.replay_from_step(
        execution_id=execution_id,
        step_id="transform",
        workflow_executor=workflow_executor,
    )

    if result.ok:
        ok(f"Replay from {B}transform{X} (step 3)")
        ok(f"Re-ran {Y}{result.steps_executed}{X} steps")
        ok(f"Replay ID: {C}{result.execution_id}{X}")
        info(f"Steps 1-2 skipped. Context loaded from evidence.")
    else:
        fail(f"Replay failed: {result.error}")

    # ── Done ─────────────────────────────────────────────────────

    header("Done")

    print(f"""
  {B}What just happened:{X}

  {G}✓{X} 5-step workflow executed with full trace
  {G}✓{X} Evidence (context_before/after) captured per step
  {G}✓{X} Replayed from step 3 without re-running steps 1-2
  {G}✓{X} All evidence stored to disk

  {B}Next:{X}
    {D}# Start the HTTP API server:{X}
    flyto serve
    {D}# Then:{X}
    curl -X POST localhost:8333/v1/workflow/run -H 'Content-Type: application/json' \\
      -d '{{"workflow": ...}}'

  {C}github.com/flytohub/flyto-core{X}
""")

    # Cleanup
    if evidence_path.exists():
        shutil.rmtree(evidence_path)


if __name__ == "__main__":
    asyncio.run(main())
