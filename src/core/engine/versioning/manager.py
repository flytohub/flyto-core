# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Workflow Versioning Manager.

Pro feature gated behind FeatureFlag.WORKFLOW_EVOLUTION.
Provides semantic versioning, diffing, rollback, and publish
capabilities for workflow definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.licensing import FeatureFlag, LicenseError, LicenseManager


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class WorkflowVersion:
    """A single versioned snapshot of a workflow definition."""

    version_id: str
    workflow_id: str
    version: str  # semver like "1.0.0"
    name: str
    description: str
    definition: Dict[str, Any]  # The full workflow definition (steps, etc.)
    created_at: datetime
    created_by: str = ""
    parent_version: Optional[str] = None  # Previous version_id
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_published: bool = False


@dataclass
class VersionDiff:
    """Diff result between two workflow versions."""

    version_from: str
    version_to: str
    steps_added: List[str]
    steps_removed: List[str]
    steps_modified: List[str]
    params_changed: Dict[str, Dict[str, Any]]  # step_id -> {field: {old, new}}
    summary: str


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class WorkflowVersionManager:
    """
    Version control for workflows.

    Pro feature — requires FeatureFlag.WORKFLOW_EVOLUTION.
    Provides semantic versioning, diffing, and rollback.
    """

    def __init__(self) -> None:
        # workflow_id -> ordered list of WorkflowVersion (oldest first)
        self._store: Dict[str, List[WorkflowVersion]] = {}
        # version_id -> WorkflowVersion (fast lookup)
        self._index: Dict[str, WorkflowVersion] = {}

    # ------------------------------------------------------------------
    # Feature gate
    # ------------------------------------------------------------------

    def _require_feature(self) -> None:
        """Check that the current licence permits workflow evolution."""
        manager = LicenseManager.get_instance()
        if not manager.has_feature(FeatureFlag.WORKFLOW_EVOLUTION):
            raise LicenseError(
                "Workflow versioning requires the WORKFLOW_EVOLUTION feature. "
                "Please upgrade your licence."
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save_version(
        self,
        workflow_id: str,
        name: str,
        definition: Dict[str, Any],
        description: str = "",
        version: str = "0.1.0",
        created_by: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkflowVersion:
        """Save a new version, automatically linking it to the previous one."""
        self._require_feature()

        existing = self._store.get(workflow_id, [])
        parent_version: Optional[str] = None
        if existing:
            parent_version = existing[-1].version_id

        ver = WorkflowVersion(
            version_id=str(uuid4()),
            workflow_id=workflow_id,
            version=version,
            name=name,
            description=description,
            definition=definition,
            created_at=datetime.now(timezone.utc),
            created_by=created_by,
            parent_version=parent_version,
            tags=tags if tags is not None else [],
            metadata=metadata if metadata is not None else {},
            is_published=False,
        )

        self._store.setdefault(workflow_id, []).append(ver)
        self._index[ver.version_id] = ver
        return ver

    def get_version(self, version_id: str) -> Optional[WorkflowVersion]:
        """Get a version by its unique version_id."""
        self._require_feature()
        return self._index.get(version_id)

    def get_latest(self, workflow_id: str) -> Optional[WorkflowVersion]:
        """Get the most recent version of a workflow."""
        self._require_feature()
        versions = self._store.get(workflow_id, [])
        if not versions:
            return None
        return versions[-1]

    def list_versions(self, workflow_id: str) -> List[WorkflowVersion]:
        """List all versions of a workflow, sorted newest first."""
        self._require_feature()
        versions = self._store.get(workflow_id, [])
        return list(reversed(versions))

    # ------------------------------------------------------------------
    # Diffing
    # ------------------------------------------------------------------

    @staticmethod
    def _steps_by_id(definition: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract a mapping of step_id -> step dict from a definition."""
        steps = definition.get("steps", [])
        result: Dict[str, Dict[str, Any]] = {}
        for step in steps:
            step_id = step.get("id", step.get("step_id", ""))
            if step_id:
                result[step_id] = step
        return result

    def diff(self, version_id_a: str, version_id_b: str) -> VersionDiff:
        """Compute a diff between two versions."""
        self._require_feature()

        ver_a = self._index.get(version_id_a)
        ver_b = self._index.get(version_id_b)
        if ver_a is None:
            raise ValueError("Version not found: %s" % version_id_a)
        if ver_b is None:
            raise ValueError("Version not found: %s" % version_id_b)

        steps_a = self._steps_by_id(ver_a.definition)
        steps_b = self._steps_by_id(ver_b.definition)

        ids_a = set(steps_a.keys())
        ids_b = set(steps_b.keys())

        steps_added = sorted(ids_b - ids_a)
        steps_removed = sorted(ids_a - ids_b)

        steps_modified: List[str] = []
        params_changed: Dict[str, Dict[str, Any]] = {}

        for sid in sorted(ids_a & ids_b):
            step_old = steps_a[sid]
            step_new = steps_b[sid]
            if step_old != step_new:
                steps_modified.append(sid)
                changes: Dict[str, Any] = {}
                all_keys = set(step_old.keys()) | set(step_new.keys())
                for key in sorted(all_keys):
                    old_val = step_old.get(key)
                    new_val = step_new.get(key)
                    if old_val != new_val:
                        changes[key] = {"old": old_val, "new": new_val}
                if changes:
                    params_changed[sid] = changes

        # Build summary
        parts: List[str] = []
        if steps_added:
            parts.append("%d step(s) added" % len(steps_added))
        if steps_removed:
            parts.append("%d step(s) removed" % len(steps_removed))
        if steps_modified:
            parts.append("%d step(s) modified" % len(steps_modified))
        summary = ", ".join(parts) if parts else "No changes"

        return VersionDiff(
            version_from=version_id_a,
            version_to=version_id_b,
            steps_added=steps_added,
            steps_removed=steps_removed,
            steps_modified=steps_modified,
            params_changed=params_changed,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Rollback & publish
    # ------------------------------------------------------------------

    def rollback(
        self,
        workflow_id: str,
        target_version_id: str,
    ) -> WorkflowVersion:
        """Create a new version by copying the definition from a previous one."""
        self._require_feature()

        target = self._index.get(target_version_id)
        if target is None:
            raise ValueError("Version not found: %s" % target_version_id)
        if target.workflow_id != workflow_id:
            raise ValueError(
                "Version %s does not belong to workflow %s"
                % (target_version_id, workflow_id)
            )

        latest = self.get_latest(workflow_id)
        if latest is None:
            raise ValueError("Workflow has no versions: %s" % workflow_id)

        # Parse the latest semver and bump the patch number
        parts = latest.version.split(".")
        try:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        except (IndexError, ValueError):
            major, minor, patch = 0, 1, 0
        next_version = "%d.%d.%d" % (major, minor, patch + 1)

        rollback_desc = "Rollback to version %s (%s)" % (
            target.version,
            target_version_id,
        )

        return self.save_version(
            workflow_id=workflow_id,
            name=target.name,
            definition=dict(target.definition),
            description=rollback_desc,
            version=next_version,
            created_by=target.created_by,
            tags=list(target.tags),
            metadata={"rollback_from": target_version_id},
        )

    def publish(self, version_id: str) -> WorkflowVersion:
        """Mark a version as published."""
        self._require_feature()

        ver = self._index.get(version_id)
        if ver is None:
            raise ValueError("Version not found: %s" % version_id)
        ver.is_published = True
        return ver

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_version(self, version_id: str) -> bool:
        """Delete a version. Only unpublished versions can be deleted."""
        self._require_feature()

        ver = self._index.get(version_id)
        if ver is None:
            return False
        if ver.is_published:
            raise ValueError(
                "Cannot delete published version: %s" % version_id
            )

        # Remove from the ordered list
        versions = self._store.get(ver.workflow_id, [])
        self._store[ver.workflow_id] = [
            v for v in versions if v.version_id != version_id
        ]
        # Clean up empty entries
        if not self._store[ver.workflow_id]:
            del self._store[ver.workflow_id]

        del self._index[version_id]
        return True

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Return a summarised version history for a workflow (newest first)."""
        self._require_feature()

        versions = self._store.get(workflow_id, [])
        history: List[Dict[str, Any]] = []
        for ver in reversed(versions):
            step_count = len(ver.definition.get("steps", []))
            history.append(
                {
                    "version_id": ver.version_id,
                    "version": ver.version,
                    "name": ver.name,
                    "description": ver.description,
                    "created_at": ver.created_at.isoformat(),
                    "created_by": ver.created_by,
                    "parent_version": ver.parent_version,
                    "tags": ver.tags,
                    "is_published": ver.is_published,
                    "step_count": step_count,
                }
            )
        return history
