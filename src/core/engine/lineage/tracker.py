"""
Run Tracker for AI Testing Lineage

Provides a high-level API for tracking workflow executions with:
- Step categorization (observe/evaluate/decide/act/verify)
- Artifact production and consumption
- AI decision recording with evidence
- JSON serialization for visualization
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import (
    Run,
    Step,
    StepCategory,
    Artifact,
    ArtifactType,
    Decision,
    Edge,
    EdgeType,
)

logger = logging.getLogger(__name__)


class RunTracker:
    """
    Tracks a complete workflow run with lineage information.

    Usage:
        tracker = RunTracker(workflow_name="AI UI Review")

        # Start a step
        step_id = tracker.start_step(
            module_id="browser.screenshot",
            category=StepCategory.OBSERVE,
            inputs={"url": "http://localhost:3000"}
        )

        # Add artifact
        artifact_id = tracker.add_artifact(
            step_id=step_id,
            artifact_type=ArtifactType.SCREENSHOT,
            name="homepage.png",
            path="./screenshots/homepage.png"
        )

        # End step
        tracker.end_step(step_id, outputs={"path": "./screenshots/homepage.png"})

        # Record decision
        tracker.record_decision(
            step_id=decision_step_id,
            decision="need_fix",
            reason="Accessibility score 65 < threshold 80",
            confidence=0.91,
            evidence=[artifact_id]
        )

        # Save lineage
        tracker.save("./lineage.json")
    """

    def __init__(
        self,
        run_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize a new run tracker.

        Args:
            run_id: Unique run identifier (auto-generated if not provided)
            workflow_id: Workflow definition ID
            workflow_name: Human-readable workflow name
            metadata: Additional metadata for the run
        """
        self.run = Run(
            id=run_id or f"run_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            started_at=datetime.now(),
            status="running",
            metadata=metadata or {},
        )
        self._current_steps: Dict[str, Step] = {}
        self._step_stack: List[str] = []  # For nested steps

    # =========================================================================
    # Step Management
    # =========================================================================

    def start_step(
        self,
        module_id: str,
        category: Union[StepCategory, str],
        name: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        step_id: Optional[str] = None,
        parent_step_id: Optional[str] = None,
        iteration: Optional[int] = None,
    ) -> str:
        """
        Start tracking a new step.

        Args:
            module_id: The module being executed
            category: Step category for swimlane placement
            name: Human-readable step name
            inputs: Step input parameters
            step_id: Custom step ID (auto-generated if not provided)
            parent_step_id: Parent step ID for nested execution
            iteration: Loop iteration index

        Returns:
            Step ID
        """
        if isinstance(category, str):
            category = StepCategory(category)

        step = Step(
            id=step_id or f"step_{uuid.uuid4().hex[:8]}",
            module_id=module_id,
            category=category,
            name=name or module_id,
            inputs=inputs or {},
            started_at=datetime.now(),
            status="running",
            parent_step_id=parent_step_id or (self._step_stack[-1] if self._step_stack else None),
            iteration=iteration,
        )

        self._current_steps[step.id] = step
        self._step_stack.append(step.id)
        self.run.steps.append(step)

        logger.debug(f"Started step: {step.id} ({step.module_id}) [{category.value}]")
        return step.id

    def end_step(
        self,
        step_id: str,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Mark a step as completed.

        Args:
            step_id: The step ID to complete
            outputs: Step output values
            error: Error message if step failed
        """
        step = self._current_steps.get(step_id)
        if not step:
            logger.warning(f"Step not found: {step_id}")
            return

        step.ended_at = datetime.now()
        step.outputs = outputs or {}
        step.status = "failed" if error else "completed"
        step.error = error

        # Remove from stack
        if step_id in self._step_stack:
            self._step_stack.remove(step_id)

        del self._current_steps[step_id]

        logger.debug(f"Ended step: {step_id} ({step.status})")

    def fail_step(self, step_id: str, error: str) -> None:
        """Mark a step as failed with error message"""
        self.end_step(step_id, error=error)

    def get_current_step(self) -> Optional[Step]:
        """Get the currently running step (top of stack)"""
        if self._step_stack:
            step_id = self._step_stack[-1]
            return self._current_steps.get(step_id)
        return None

    # =========================================================================
    # Artifact Management
    # =========================================================================

    def add_artifact(
        self,
        step_id: str,
        artifact_type: Union[ArtifactType, str],
        name: str,
        path: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        mime_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> str:
        """
        Add an artifact produced by a step.

        Args:
            step_id: The step that produced this artifact
            artifact_type: Type of artifact
            name: Human-readable name
            path: File path if stored externally
            data: Inline data if not stored externally
            mime_type: MIME type of the artifact
            artifact_id: Custom artifact ID

        Returns:
            Artifact ID
        """
        if isinstance(artifact_type, str):
            artifact_type = ArtifactType(artifact_type)

        artifact = Artifact(
            id=artifact_id or f"artifact_{uuid.uuid4().hex[:8]}",
            type=artifact_type,
            name=name,
            produced_by=step_id,
            path=path,
            data=data,
            mime_type=mime_type,
        )

        self.run.artifacts[artifact.id] = artifact

        # Add edge: step produces artifact
        self.run.edges.append(Edge(
            source=step_id,
            target=artifact.id,
            edge_type=EdgeType.PRODUCES,
        ))

        # Update step's artifact list
        for step in self.run.steps:
            if step.id == step_id:
                step.artifacts.append(artifact.id)
                break

        logger.debug(f"Added artifact: {artifact.id} ({artifact_type.value})")
        return artifact.id

    def consume_artifact(self, step_id: str, artifact_id: str) -> None:
        """
        Record that a step consumes an artifact.

        Args:
            step_id: The step consuming the artifact
            artifact_id: The artifact being consumed
        """
        self.run.edges.append(Edge(
            source=artifact_id,
            target=step_id,
            edge_type=EdgeType.CONSUMES,
        ))

    # =========================================================================
    # Decision Management
    # =========================================================================

    def record_decision(
        self,
        step_id: str,
        decision: str,
        reason: str,
        confidence: float,
        evidence: Optional[List[str]] = None,
        alternatives: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record an AI decision for a step.

        Args:
            step_id: The decision step
            decision: Decision value (e.g., "need_fix", "pass", "fail")
            reason: Human-readable explanation
            confidence: Confidence score 0.0-1.0
            evidence: List of artifact IDs supporting the decision
            alternatives: Other considered options
            metadata: Additional decision metadata

        Returns:
            Decision artifact ID
        """
        decision_obj = Decision(
            decision=decision,
            reason=reason,
            confidence=confidence,
            evidence=evidence or [],
            alternatives=alternatives,
            metadata=metadata,
        )

        # Attach decision to step
        for step in self.run.steps:
            if step.id == step_id:
                step.decision = decision_obj
                break

        # Also create decision artifact
        artifact_id = self.add_artifact(
            step_id=step_id,
            artifact_type=ArtifactType.DECISION,
            name=f"Decision: {decision}",
            data=decision_obj.to_dict(),
        )

        logger.debug(f"Recorded decision: {decision} (confidence: {confidence})")
        return artifact_id

    # =========================================================================
    # Run Management
    # =========================================================================

    def complete(self, status: str = "completed") -> None:
        """Mark the run as complete"""
        self.run.ended_at = datetime.now()
        self.run.status = status

        # Fail any still-running steps
        for step_id in list(self._current_steps.keys()):
            self.fail_step(step_id, "Run ended while step was running")

        logger.info(f"Run completed: {self.run.id} ({status})")

    def fail(self, error: Optional[str] = None) -> None:
        """Mark the run as failed"""
        self.run.metadata["error"] = error
        self.complete(status="failed")

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> Dict[str, Any]:
        """Convert run to dictionary"""
        return self.run.to_dict()

    def to_json(self, indent: int = 2) -> str:
        """Convert run to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: Union[str, Path]) -> None:
        """
        Save lineage to JSON file.

        Args:
            path: Output file path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

        logger.info(f"Saved lineage to: {path}")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "RunTracker":
        """
        Load lineage from JSON file.

        Args:
            path: Input file path

        Returns:
            RunTracker with loaded run
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        run = Run.from_dict(data)
        tracker = cls(run_id=run.id)
        tracker.run = run
        return tracker

    # =========================================================================
    # Analysis Helpers
    # =========================================================================

    def get_steps_by_category(self, category: StepCategory) -> List[Step]:
        """Get all steps of a specific category"""
        return self.run.get_steps_by_category(category)

    def get_decision_steps(self) -> List[Step]:
        """Get all steps with decisions"""
        return self.run.get_decision_steps()

    def get_failed_decisions(self) -> List[Step]:
        """Get steps where decision indicates failure"""
        failed = []
        for step in self.get_decision_steps():
            if step.decision and step.decision.decision in ("fail", "need_fix"):
                failed.append(step)
        return failed

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the run"""
        steps_by_category = {
            cat.value: len(self.get_steps_by_category(cat))
            for cat in StepCategory
        }

        decisions = self.get_decision_steps()
        decision_summary = {}
        for step in decisions:
            if step.decision:
                d = step.decision.decision
                decision_summary[d] = decision_summary.get(d, 0) + 1

        return {
            "run_id": self.run.id,
            "workflow_name": self.run.workflow_name,
            "status": self.run.status,
            "duration_ms": self.run.duration_ms,
            "total_steps": len(self.run.steps),
            "steps_by_category": steps_by_category,
            "total_artifacts": len(self.run.artifacts),
            "total_decisions": len(decisions),
            "decision_summary": decision_summary,
        }

    def __repr__(self) -> str:
        return f"RunTracker({self.run.id}, steps={len(self.run.steps)}, status={self.run.status})"
