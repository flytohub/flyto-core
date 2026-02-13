"""
Simple Task Planner

Decomposes a task description into a flyto-core workflow.
This is a minimal demo — a real planner would use an LLM.
"""

from pathlib import Path
from typing import Dict, Any, Optional

import yaml


WORKFLOW_DIR = Path(__file__).parent / "workflows"


class SimplePlanner:
    """Decomposes a task description into a flyto-core workflow."""

    # Map keywords to pre-built workflow files
    TEMPLATES = {
        "research": "browser_research.yaml",
        "browse": "browser_research.yaml",
        "scrape": "browser_research.yaml",
        "news": "browser_research.yaml",
    }

    def plan(self, task: str) -> Optional[Dict[str, Any]]:
        """
        Returns a workflow dict for the given task.

        Args:
            task: Natural language task description

        Returns:
            Parsed workflow dict, or None if no match
        """
        task_lower = task.lower()
        for keyword, filename in self.TEMPLATES.items():
            if keyword in task_lower:
                workflow_path = WORKFLOW_DIR / filename
                if workflow_path.exists():
                    with open(workflow_path, "r") as f:
                        return yaml.safe_load(f)
        return None

    def list_capabilities(self) -> list:
        """List available pre-built workflows."""
        capabilities = []
        for path in WORKFLOW_DIR.glob("*.yaml"):
            with open(path, "r") as f:
                wf = yaml.safe_load(f)
            capabilities.append({
                "file": path.name,
                "name": wf.get("name", path.stem),
                "description": wf.get("description", ""),
                "steps": len(wf.get("steps", [])),
            })
        return capabilities
