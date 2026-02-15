"""
Replay Routes

POST /v1/workflow/{id}/replay/{step_id}  — Replay from step
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..models import ReplayRequest, ReplayResponse
from ..security import require_auth

router = APIRouter(tags=["replay"])
logger = logging.getLogger(__name__)


@router.post("/workflow/{execution_id}/replay/{step_id}", response_model=ReplayResponse, dependencies=[Depends(require_auth)])
async def replay_from_step(
    execution_id: str,
    step_id: str,
    body: ReplayRequest,
    request: Request,
):
    """Replay workflow execution from a specific step."""
    state = request.app.state.server
    manager = state.replay_manager

    # Validate
    validation = await manager.validate_replay(execution_id, step_id)
    if not validation.get("valid"):
        return ReplayResponse(
            ok=False,
            execution_id="",
            original_execution_id=execution_id,
            start_step=step_id,
            error=f"Validation failed: {validation.get('issues', [])}",
        )

    if body.dry_run:
        return ReplayResponse(
            ok=True,
            execution_id="dry_run",
            original_execution_id=execution_id,
            start_step=step_id,
        )

    # Build executor callback
    async def workflow_executor(workflow, context, start_step, end_step, **kwargs):
        from core.engine import WorkflowEngine

        # Find start_step index
        steps = workflow.get("steps", [])
        start_idx = None
        for i, s in enumerate(steps):
            if s.get("id") == start_step:
                start_idx = i
                break

        end_idx = None
        if end_step:
            for i, s in enumerate(steps):
                if s.get("id") == end_step:
                    end_idx = i
                    break

        engine = WorkflowEngine(
            workflow=workflow,
            start_step=start_idx,
            end_step=end_idx,
            initial_context=context,
            enable_trace=True,
        )

        try:
            result = await engine.execute()
            return {
                "ok": True,
                "steps_executed": len(engine.execution_log),
                "context": engine.context,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "steps_executed": len(engine.execution_log),
                "context": engine.context,
            }

    from core.engine.replay import ReplayConfig
    config = ReplayConfig(
        start_step_id=step_id,
        modified_context=body.modified_context or {},
        dry_run=False,
    )

    result = await manager.replay_from_step(
        execution_id=execution_id,
        step_id=step_id,
        workflow_executor=workflow_executor,
        config=config,
    )

    return ReplayResponse(
        ok=result.ok,
        execution_id=result.execution_id,
        original_execution_id=result.original_execution_id,
        start_step=result.start_step,
        steps_executed=result.steps_executed,
        duration_ms=result.duration_ms,
        error=result.error,
    )
