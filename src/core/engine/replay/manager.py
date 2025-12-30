"""
Replay Manager

Manages workflow replay operations.
"""

import copy
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import ReplayConfig, ReplayResult

logger = logging.getLogger(__name__)


class ReplayManager:
    """
    Manages workflow replay operations.

    Loads evidence from previous executions and enables re-execution
    from any point with optional context modifications.

    Usage:
        manager = ReplayManager(evidence_store)

        # Replay from specific step
        result = await manager.replay_from_step(
            execution_id="exec_123",
            step_id="step_5",
            modified_context={"user_id": "new_user"},
            workflow_executor=executor_func,
        )

        # Validate replay without executing
        validation = await manager.validate_replay(
            execution_id="exec_123",
            step_id="step_5",
        )
    """

    def __init__(
        self,
        evidence_path: Path,
        max_replay_history: int = 100,
    ):
        """
        Initialize replay manager.

        Args:
            evidence_path: Path to evidence storage
            max_replay_history: Maximum replay history to maintain
        """
        self.evidence_path = Path(evidence_path)
        self.max_replay_history = max_replay_history
        self._replay_history: List[ReplayResult] = []

    async def load_execution_state(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load execution state at a specific step.

        Args:
            execution_id: Original execution ID
            step_id: Step to load state at

        Returns:
            Context state at that step, or None if not found
        """
        jsonl_path = self.evidence_path / execution_id / "evidence.jsonl"

        if not jsonl_path.exists():
            logger.warning(f"Evidence not found for {execution_id}")
            return None

        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)
                    if data.get('step_id') == step_id:
                        return {
                            "context_before": data.get('context_before', {}),
                            "context_after": data.get('context_after', {}),
                            "step_index": data.get('step_index'),
                            "module_id": data.get('module_id'),
                            "status": data.get('status'),
                            "output": data.get('output', {}),
                        }

        except Exception as e:
            logger.error(f"Failed to load state for {execution_id}/{step_id}: {e}")

        return None

    async def load_execution_steps(
        self,
        execution_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Load all steps from an execution.

        Args:
            execution_id: Execution ID

        Returns:
            List of step data in execution order
        """
        jsonl_path = self.evidence_path / execution_id / "evidence.jsonl"

        if not jsonl_path.exists():
            return []

        steps = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        steps.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to load steps for {execution_id}: {e}")

        return steps

    async def validate_replay(
        self,
        execution_id: str,
        step_id: str,
        config: Optional[ReplayConfig] = None,
    ) -> Dict[str, Any]:
        """
        Validate that a replay is possible.

        Args:
            execution_id: Execution to replay from
            step_id: Step to start from
            config: Optional replay configuration

        Returns:
            Validation result with issues if any
        """
        config = config or ReplayConfig(start_step_id=step_id)
        issues = []
        warnings = []

        # Check evidence exists
        exec_dir = self.evidence_path / execution_id
        if not exec_dir.exists():
            issues.append(f"Execution {execution_id} not found")
            return {
                "valid": False,
                "issues": issues,
                "warnings": warnings,
            }

        # Load steps
        steps = await self.load_execution_steps(execution_id)
        if not steps:
            issues.append("No step evidence found")
            return {
                "valid": False,
                "issues": issues,
                "warnings": warnings,
            }

        # Check start step exists
        step_ids = [s.get('step_id') for s in steps]
        if step_id not in step_ids:
            issues.append(f"Step {step_id} not found in execution")
            return {
                "valid": False,
                "issues": issues,
                "warnings": warnings,
            }

        # Check end step if specified
        if config.end_step_id and config.end_step_id not in step_ids:
            issues.append(f"End step {config.end_step_id} not found")

        # Check skip steps exist
        for skip_id in config.skip_steps:
            if skip_id not in step_ids:
                warnings.append(f"Skip step {skip_id} not found")

        # Load state at start step
        state = await self.load_execution_state(execution_id, step_id)
        if not state:
            issues.append(f"Could not load state at step {step_id}")

        # Validate modified context keys
        if state and config.modified_context:
            original_keys = set(state.get('context_before', {}).keys())
            for key in config.modified_context:
                if key not in original_keys:
                    warnings.append(f"Modified key '{key}' not in original context")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "step_count": len(steps),
            "start_step_index": step_ids.index(step_id) if step_id in step_ids else None,
            "available_steps": step_ids,
        }

    async def prepare_replay_context(
        self,
        execution_id: str,
        step_id: str,
        modified_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare context for replay execution.

        Loads the context_before from the target step and applies
        any modifications.

        Args:
            execution_id: Original execution ID
            step_id: Step to start from
            modified_context: Context modifications to apply

        Returns:
            Prepared context for replay
        """
        state = await self.load_execution_state(execution_id, step_id)

        if not state:
            raise ValueError(f"Cannot load state for {execution_id}/{step_id}")

        # Start with context before the step
        context = copy.deepcopy(state.get('context_before', {}))

        # Apply modifications
        if modified_context:
            context.update(modified_context)

        return context

    async def replay_from_step(
        self,
        execution_id: str,
        step_id: str,
        workflow_executor: Callable,
        config: Optional[ReplayConfig] = None,
    ) -> ReplayResult:
        """
        Execute replay from a specific step.

        Args:
            execution_id: Original execution ID
            step_id: Step to start from
            workflow_executor: Async function to execute workflow
                Signature: async def executor(workflow, context, start_step, end_step) -> result
            config: Replay configuration

        Returns:
            ReplayResult with execution outcome
        """
        config = config or ReplayConfig(start_step_id=step_id)
        start_time = datetime.now()
        new_execution_id = f"replay_{uuid.uuid4().hex[:12]}"

        # Validate first
        validation = await self.validate_replay(execution_id, step_id, config)
        if not validation.get('valid'):
            return ReplayResult(
                ok=False,
                execution_id=new_execution_id,
                original_execution_id=execution_id,
                start_step=step_id,
                error=f"Validation failed: {validation.get('issues')}",
            )

        if config.dry_run:
            return ReplayResult(
                ok=True,
                execution_id=new_execution_id,
                original_execution_id=execution_id,
                start_step=step_id,
                context={"dry_run": True, "validation": validation},
            )

        try:
            # Prepare context
            context = await self.prepare_replay_context(
                execution_id,
                step_id,
                config.modified_context,
            )

            # Get workflow definition (stored in evidence metadata)
            workflow = await self._load_workflow_definition(execution_id)
            if not workflow:
                return ReplayResult(
                    ok=False,
                    execution_id=new_execution_id,
                    original_execution_id=execution_id,
                    start_step=step_id,
                    error="Workflow definition not found in evidence",
                )

            # Execute workflow from step
            result = await workflow_executor(
                workflow=workflow,
                context=context,
                start_step=step_id,
                end_step=config.end_step_id,
                skip_steps=config.skip_steps,
                breakpoints=config.breakpoints,
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            replay_result = ReplayResult(
                ok=result.get('ok', False),
                execution_id=new_execution_id,
                original_execution_id=execution_id,
                start_step=step_id,
                end_step=config.end_step_id,
                steps_executed=result.get('steps_executed', 0),
                steps_skipped=len(config.skip_steps),
                context=result.get('context', {}),
                error=result.get('error'),
                duration_ms=duration_ms,
            )

            # Record in history
            self._add_to_history(replay_result)

            return replay_result

        except Exception as e:
            logger.error(f"Replay failed: {e}")
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return ReplayResult(
                ok=False,
                execution_id=new_execution_id,
                original_execution_id=execution_id,
                start_step=step_id,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def replay_single_step(
        self,
        execution_id: str,
        step_id: str,
        step_executor: Callable,
        modified_params: Optional[Dict[str, Any]] = None,
        modified_context: Optional[Dict[str, Any]] = None,
    ) -> ReplayResult:
        """
        Re-execute a single step.

        Useful for testing individual step behavior with different inputs.

        Args:
            execution_id: Original execution ID
            step_id: Step to re-execute
            step_executor: Async function to execute single step
                Signature: async def executor(module_id, params, context) -> result
            modified_params: Parameter modifications
            modified_context: Context modifications

        Returns:
            ReplayResult with step outcome
        """
        start_time = datetime.now()
        new_execution_id = f"replay_step_{uuid.uuid4().hex[:12]}"

        try:
            # Load step state
            state = await self.load_execution_state(execution_id, step_id)
            if not state:
                return ReplayResult(
                    ok=False,
                    execution_id=new_execution_id,
                    original_execution_id=execution_id,
                    start_step=step_id,
                    error=f"Step {step_id} not found",
                )

            # Prepare context
            context = copy.deepcopy(state.get('context_before', {}))
            if modified_context:
                context.update(modified_context)

            # Get step configuration from workflow
            workflow = await self._load_workflow_definition(execution_id)
            step_config = self._find_step_config(workflow, step_id)

            if not step_config:
                return ReplayResult(
                    ok=False,
                    execution_id=new_execution_id,
                    original_execution_id=execution_id,
                    start_step=step_id,
                    error=f"Step configuration not found for {step_id}",
                )

            # Merge parameters
            params = copy.deepcopy(step_config.get('params', {}))
            if modified_params:
                params.update(modified_params)

            # Execute step
            result = await step_executor(
                module_id=step_config.get('module'),
                params=params,
                context=context,
            )

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return ReplayResult(
                ok=result.get('ok', True),
                execution_id=new_execution_id,
                original_execution_id=execution_id,
                start_step=step_id,
                end_step=step_id,
                steps_executed=1,
                context=result.get('context', context),
                error=result.get('error'),
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Single step replay failed: {e}")
            return ReplayResult(
                ok=False,
                execution_id=new_execution_id,
                original_execution_id=execution_id,
                start_step=step_id,
                error=str(e),
            )

    async def compare_replay(
        self,
        original_execution_id: str,
        replay_execution_id: str,
    ) -> Dict[str, Any]:
        """
        Compare original and replay execution results.

        Args:
            original_execution_id: Original execution ID
            replay_execution_id: Replay execution ID

        Returns:
            Comparison results
        """
        original_steps = await self.load_execution_steps(original_execution_id)
        replay_steps = await self.load_execution_steps(replay_execution_id)

        original_by_id = {s['step_id']: s for s in original_steps}
        replay_by_id = {s['step_id']: s for s in replay_steps}

        differences = []
        for step_id in set(original_by_id.keys()) | set(replay_by_id.keys()):
            orig = original_by_id.get(step_id)
            repl = replay_by_id.get(step_id)

            if not orig:
                differences.append({
                    "step_id": step_id,
                    "type": "added_in_replay",
                })
            elif not repl:
                differences.append({
                    "step_id": step_id,
                    "type": "not_in_replay",
                })
            else:
                # Compare outcomes
                if orig.get('status') != repl.get('status'):
                    differences.append({
                        "step_id": step_id,
                        "type": "status_changed",
                        "original": orig.get('status'),
                        "replay": repl.get('status'),
                    })

                if orig.get('output') != repl.get('output'):
                    differences.append({
                        "step_id": step_id,
                        "type": "output_changed",
                        "original_keys": list(orig.get('output', {}).keys()),
                        "replay_keys": list(repl.get('output', {}).keys()),
                    })

        return {
            "original_execution_id": original_execution_id,
            "replay_execution_id": replay_execution_id,
            "original_step_count": len(original_steps),
            "replay_step_count": len(replay_steps),
            "differences": differences,
            "identical": len(differences) == 0,
        }

    async def _load_workflow_definition(
        self,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load workflow definition from execution metadata"""
        meta_path = self.evidence_path / execution_id / "workflow.json"

        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load workflow definition: {e}")

        return None

    def _find_step_config(
        self,
        workflow: Optional[Dict[str, Any]],
        step_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Find step configuration by ID"""
        if not workflow:
            return None

        for step in workflow.get('steps', []):
            if step.get('id') == step_id:
                return step

        return None

    def _add_to_history(self, result: ReplayResult) -> None:
        """Add replay result to history"""
        self._replay_history.append(result)

        # Trim history if needed
        if len(self._replay_history) > self.max_replay_history:
            self._replay_history = self._replay_history[-self.max_replay_history:]

    def get_replay_history(
        self,
        execution_id: Optional[str] = None,
    ) -> List[ReplayResult]:
        """Get replay history, optionally filtered by original execution"""
        if execution_id:
            return [
                r for r in self._replay_history
                if r.original_execution_id == execution_id
            ]
        return list(self._replay_history)


# =============================================================================
# Factory Functions
# =============================================================================

def create_replay_manager(
    evidence_path: Optional[Path] = None,
) -> ReplayManager:
    """
    Create a replay manager.

    Args:
        evidence_path: Path to evidence storage

    Returns:
        Configured ReplayManager
    """
    if evidence_path is None:
        evidence_path = Path("./evidence")
    return ReplayManager(evidence_path=evidence_path)
