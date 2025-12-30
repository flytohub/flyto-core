"""
Evidence Store

Stores execution evidence to filesystem.
"""

import json
import logging
from pathlib import Path
from typing import Any, List, Optional

from .models import StepEvidence

logger = logging.getLogger(__name__)


class EvidenceStore:
    """
    Stores execution evidence to filesystem.

    Directory structure:
        evidence/
        ├── exec_abc123/
        │   ├── evidence.jsonl    # All step metadata
        │   ├── step_1.png        # Screenshot
        │   ├── step_1.html       # DOM snapshot
        │   └── ...
        └── exec_def456/
            └── ...
    """

    def __init__(
        self,
        base_path: Path,
        capture_context: bool = True,
        max_context_depth: int = 5,
    ):
        """
        Initialize evidence store.

        Args:
            base_path: Base directory for evidence storage
            capture_context: Whether to capture context snapshots
            max_context_depth: Max nesting depth for context serialization
        """
        self.base_path = Path(base_path)
        self.capture_context = capture_context
        self.max_context_depth = max_context_depth

    def get_execution_dir(self, execution_id: str) -> Path:
        """Get/create directory for execution evidence"""
        path = self.base_path / execution_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_evidence(self, evidence: StepEvidence) -> None:
        """
        Save evidence metadata to JSONL file.

        Appends to evidence.jsonl in the execution directory.
        """
        try:
            exec_dir = self.get_execution_dir(evidence.execution_id)
            jsonl_path = exec_dir / "evidence.jsonl"

            # Serialize to JSON
            data = evidence.to_dict()
            # Truncate large context if needed
            data = self._truncate_large_values(data)
            line = json.dumps(data, default=str, ensure_ascii=False) + '\n'

            # Append to JSONL file
            with open(jsonl_path, 'a', encoding='utf-8') as f:
                f.write(line)

            logger.debug(f"Saved evidence for step {evidence.step_id}")

        except Exception as e:
            logger.warning(f"Failed to save evidence for {evidence.step_id}: {e}")

    async def save_screenshot(
        self,
        execution_id: str,
        step_id: str,
        screenshot_bytes: bytes,
    ) -> str:
        """
        Save screenshot and return relative path.

        Args:
            execution_id: Execution ID
            step_id: Step ID (used as filename)
            screenshot_bytes: PNG image data

        Returns:
            Relative filename (e.g., "step_1.png")
        """
        try:
            exec_dir = self.get_execution_dir(execution_id)
            filename = f"{step_id}.png"
            path = exec_dir / filename

            with open(path, 'wb') as f:
                f.write(screenshot_bytes)

            logger.debug(f"Saved screenshot: {path}")
            return filename

        except Exception as e:
            logger.warning(f"Failed to save screenshot for {step_id}: {e}")
            return ""

    async def save_dom_snapshot(
        self,
        execution_id: str,
        step_id: str,
        dom_html: str,
    ) -> str:
        """
        Save DOM snapshot and return relative path.

        Args:
            execution_id: Execution ID
            step_id: Step ID (used as filename)
            dom_html: HTML content

        Returns:
            Relative filename (e.g., "step_1.html")
        """
        try:
            exec_dir = self.get_execution_dir(execution_id)
            filename = f"{step_id}.html"
            path = exec_dir / filename

            with open(path, 'w', encoding='utf-8') as f:
                f.write(dom_html)

            logger.debug(f"Saved DOM snapshot: {path}")
            return filename

        except Exception as e:
            logger.warning(f"Failed to save DOM snapshot for {step_id}: {e}")
            return ""

    async def load_evidence(self, execution_id: str) -> List[StepEvidence]:
        """
        Load all evidence for an execution.

        Args:
            execution_id: Execution ID to load

        Returns:
            List of StepEvidence records in execution order
        """
        exec_dir = self.base_path / execution_id
        jsonl_path = exec_dir / "evidence.jsonl"

        if not jsonl_path.exists():
            return []

        evidence_list = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        evidence_list.append(StepEvidence.from_dict(data))
        except Exception as e:
            logger.warning(f"Failed to load evidence for {execution_id}: {e}")

        return evidence_list

    async def load_step_evidence(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[StepEvidence]:
        """
        Load evidence for a specific step.

        Args:
            execution_id: Execution ID
            step_id: Step ID to find

        Returns:
            StepEvidence if found, None otherwise
        """
        all_evidence = await self.load_evidence(execution_id)
        for evidence in all_evidence:
            if evidence.step_id == step_id:
                return evidence
        return None

    async def get_screenshot_path(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[Path]:
        """Get full path to screenshot file if it exists"""
        path = self.base_path / execution_id / f"{step_id}.png"
        return path if path.exists() else None

    async def get_dom_snapshot_path(
        self,
        execution_id: str,
        step_id: str,
    ) -> Optional[Path]:
        """Get full path to DOM snapshot file if it exists"""
        path = self.base_path / execution_id / f"{step_id}.html"
        return path if path.exists() else None

    async def list_executions(self) -> List[str]:
        """List all execution IDs with evidence"""
        if not self.base_path.exists():
            return []

        return [
            d.name for d in self.base_path.iterdir()
            if d.is_dir() and (d / "evidence.jsonl").exists()
        ]

    async def delete_execution(self, execution_id: str) -> bool:
        """
        Delete all evidence for an execution.

        Args:
            execution_id: Execution ID to delete

        Returns:
            True if deleted, False if not found
        """
        import shutil
        exec_dir = self.base_path / execution_id
        if exec_dir.exists():
            shutil.rmtree(exec_dir)
            return True
        return False

    def _truncate_large_values(
        self,
        data: Any,
        max_str_length: int = 10000,
        current_depth: int = 0,
    ) -> Any:
        """Truncate large string values to prevent huge JSONL files"""
        if current_depth > self.max_context_depth:
            return "[truncated: max depth]"

        if isinstance(data, dict):
            return {
                k: self._truncate_large_values(v, max_str_length, current_depth + 1)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            if len(data) > 100:
                return data[:100] + ["[truncated: list too long]"]
            return [
                self._truncate_large_values(v, max_str_length, current_depth + 1)
                for v in data
            ]
        elif isinstance(data, str) and len(data) > max_str_length:
            return data[:max_str_length] + f"... [truncated: {len(data)} chars]"
        elif isinstance(data, bytes):
            return f"[binary data: {len(data)} bytes]"
        return data
