# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Workflow Routes

POST /v1/workflow/run           — Run multi-step workflow
GET  /v1/workflow/{id}          — Get execution info + trace
GET  /v1/workflow/{id}/evidence — Get step-by-step evidence
"""

import contextlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..evidence_hooks import APIEvidenceHooks
from ..host_capability import HostCapabilityProxy, validate_host_capability_endpoint
from ..models import RunWorkflowRequest, StepEvidenceResponse, WorkflowRunResponse
from ..security import module_filter, require_auth

router = APIRouter(tags=["workflows"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /v1/workflow/run
# ---------------------------------------------------------------------------

@router.post("/workflow/run", response_model=WorkflowRunResponse, dependencies=[Depends(require_auth)])
async def run_workflow(body: RunWorkflowRequest, request: Request):
    """Run a multi-step workflow with optional evidence collection and tracing."""
    # Module filter check — validate all steps before execution
    blocked = [
        s.get("module", s.get("module_id", ""))
        for s in (body.workflow.get("steps") or [])
        if not module_filter.is_allowed(s.get("module", s.get("module_id", "")))
    ]
    if blocked:
        return WorkflowRunResponse(
            ok=False,
            execution_id="",
            status="blocked",
            error=f"Modules blocked by security policy: {blocked}",
        )

    state = request.app.state.server
    execution_id = f"exec_{uuid.uuid4().hex[:12]}"
    t0 = time.time()

    try:
        from core.engine import WorkflowEngine

        # Build hooks
        hooks = None
        if body.enable_evidence:
            hooks = APIEvidenceHooks(state.evidence_store, execution_id)

        initial_context = None
        host_endpoint = request.headers.get("X-Flyto-Host-Capability-Endpoint")
        host_token = request.headers.get("X-Flyto-Host-Capability-Token")
        host_timeout = request.headers.get("X-Flyto-Host-Capability-Timeout")
        if host_endpoint is not None or host_token is not None or host_timeout is not None:
            if not host_endpoint or not host_token:
                raise ValueError(
                    "host capability dispatch requires endpoint and token headers"
                )
            endpoint = validate_host_capability_endpoint(host_endpoint)
            if not 32 <= len(host_token) <= 512:
                raise ValueError("host capability token length is invalid")
            timeout_seconds = 65.0
            if host_timeout:
                timeout_seconds = float(host_timeout)
                if not 1.0 <= timeout_seconds <= 300.0:
                    raise ValueError("host capability timeout is out of bounds")
            from core.modules.atomic.capability.invoke import (
                RUNTIME_DISPATCHER_CONTEXT_KEY,
            )

            initial_context = {
                RUNTIME_DISPATCHER_CONTEXT_KEY: HostCapabilityProxy(
                    endpoint=endpoint,
                    token=host_token,
                    timeout_seconds=timeout_seconds,
                )
            }

        engine = WorkflowEngine(
            workflow=body.workflow,
            params=body.params or {},
            hooks=hooks,
            enable_trace=body.enable_trace,
            initial_context=initial_context,
        )

        state.running_workflows[execution_id] = engine

        # Persist workflow definition early so replay works even if execution fails
        if body.enable_evidence:
            _save_workflow_definition(state, execution_id, body.workflow)

        try:
            result = await engine.execute()
        finally:
            state.running_workflows.pop(execution_id, None)

        duration_ms = int((time.time() - t0) * 1000)

        trace = engine.get_execution_trace_dict() if body.enable_trace else None

        evidence_path = None
        if body.enable_evidence:
            evidence_path = str(state.evidence_store.get_execution_dir(execution_id))

        return WorkflowRunResponse(
            ok=True,
            execution_id=execution_id,
            status="completed",
            result=result if isinstance(result, dict) else {"output": result},
            trace=trace,
            evidence_path=evidence_path,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        logger.error("Workflow %s failed: %s", execution_id, e)

        evidence_path = None
        if body.enable_evidence:
            evidence_path = str(state.evidence_store.get_execution_dir(execution_id))

        return WorkflowRunResponse(
            ok=False,
            execution_id=execution_id,
            status="failed",
            error=str(e),
            evidence_path=evidence_path,
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# GET /v1/workflow/{execution_id}
# ---------------------------------------------------------------------------

@router.get("/workflow/{execution_id}", dependencies=[Depends(require_auth)])
async def get_execution_info(execution_id: str, request: Request):
    """Get execution info: steps, status, evidence summary."""
    state = request.app.state.server

    # Check running
    engine = state.running_workflows.get(execution_id)
    if engine:
        return {
            "execution_id": execution_id,
            "status": "running",
            "current_step": engine.current_step,
        }

    # Load from evidence
    evidence_list = await state.evidence_store.load_evidence(execution_id)
    if not evidence_list:
        return JSONResponse(
            {"error": f"Execution not found: {execution_id}"}, status_code=404
        )

    steps = []
    for ev in evidence_list:
        steps.append({
            "step_id": ev.step_id,
            "module_id": ev.module_id,
            "status": ev.status,
            "duration_ms": ev.duration_ms,
            "error_message": ev.error_message,
        })

    last = evidence_list[-1]
    overall_status = "completed" if last.status == "success" else "failed"

    return {
        "execution_id": execution_id,
        "status": overall_status,
        "step_count": len(steps),
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# GET /v1/workflow/{execution_id}/evidence
# ---------------------------------------------------------------------------

@router.get(
    "/workflow/{execution_id}/evidence",
    dependencies=[Depends(require_auth)],
)
async def get_execution_evidence(execution_id: str, request: Request):
    """Get step-by-step evidence for an execution."""
    state = request.app.state.server

    evidence_list = await state.evidence_store.load_evidence(execution_id)
    if not evidence_list:
        return JSONResponse(
            {"error": f"No evidence found for execution: {execution_id}"}, status_code=404
        )

    items = []
    for ev in evidence_list:
        items.append(StepEvidenceResponse(
            step_id=ev.step_id,
            module_id=ev.module_id,
            status=ev.status,
            duration_ms=ev.duration_ms,
            context_before=ev.context_before,
            context_after=ev.context_after,
            output=ev.output,
            error_message=ev.error_message,
        ).model_dump())

    return {
        "execution_id": execution_id,
        "step_count": len(items),
        "evidence": items,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_workflow_definition(state, execution_id: str, workflow: dict):
    """Persist workflow.json for replay."""
    try:
        import os as _os

        from core.engine.redaction import redact_for_persistence
        exec_dir = state.evidence_store.get_execution_dir(execution_id)
        path = exec_dir / "workflow.json"
        # SECURITY: redact inline credentials (DSNs/tokens in step headers/params)
        # before the definition lands on disk, and lock the file to the owner.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(redact_for_persistence(workflow), f, ensure_ascii=False, indent=2)
        with contextlib.suppress(OSError):
            _os.chmod(path, 0o600)
    except Exception as e:
        logger.warning("Failed to save workflow definition: %s", e)
