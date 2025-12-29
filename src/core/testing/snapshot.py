"""
Snapshot Testing

Captures and compares execution snapshots for regression testing.
Detects when workflow behavior changes unexpectedly.

Design principles:
- Automatic: Snapshots created on first run
- Diffable: Shows exact differences
- Configurable: Choose what to snapshot
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SnapshotStatus(str, Enum):
    """Snapshot comparison status"""
    MATCH = "match"
    MISMATCH = "mismatch"
    NEW = "new"
    OBSOLETE = "obsolete"


@dataclass
class SnapshotDiff:
    """
    Difference between snapshots.

    Attributes:
        path: JSON path to difference
        expected: Expected value
        actual: Actual value
        diff_type: Type of difference
    """
    path: str
    expected: Any
    actual: Any
    diff_type: str  # added, removed, changed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "path": self.path,
            "expected": self._serialize(self.expected),
            "actual": self._serialize(self.actual),
            "diff_type": self.diff_type,
        }

    def _serialize(self, value: Any) -> Any:
        """Serialize value"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return value
        return str(value)


@dataclass
class SnapshotResult:
    """
    Result of snapshot comparison.

    Attributes:
        status: Comparison status
        snapshot_name: Name of the snapshot
        differences: List of differences
        snapshot_path: Path to snapshot file
    """
    status: SnapshotStatus
    snapshot_name: str
    differences: List[SnapshotDiff] = field(default_factory=list)
    snapshot_path: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def passed(self) -> bool:
        """Check if snapshot matches"""
        return self.status == SnapshotStatus.MATCH

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "status": self.status.value,
            "snapshot_name": self.snapshot_name,
            "passed": self.passed,
            "differences": [d.to_dict() for d in self.differences],
            "snapshot_path": self.snapshot_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SnapshotManager:
    """
    Manages execution snapshots for testing.

    Usage:
        manager = SnapshotManager(Path("./snapshots"))

        # Compare against snapshot
        result = manager.match("test_workflow", execution_result)

        if not result.passed:
            print(f"Differences: {result.differences}")

        # Update snapshot
        manager.update("test_workflow", execution_result)
    """

    def __init__(
        self,
        snapshot_dir: Path,
        ignore_paths: Optional[Set[str]] = None,
        ignore_timestamps: bool = True,
        ignore_ids: bool = True,
    ):
        """
        Initialize snapshot manager.

        Args:
            snapshot_dir: Directory for snapshot storage
            ignore_paths: Paths to ignore in comparison
            ignore_timestamps: Ignore timestamp fields
            ignore_ids: Ignore ID fields
        """
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self.ignore_paths = ignore_paths or set()
        self.ignore_timestamps = ignore_timestamps
        self.ignore_ids = ignore_ids

        # Default ignored patterns
        self._default_ignore = {
            "timestamp",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
            "execution_id",
            "id",
            "uuid",
        }

    def _get_snapshot_path(self, name: str) -> Path:
        """Get path to snapshot file"""
        safe_name = name.replace("/", "_").replace("\\", "_")
        return self.snapshot_dir / f"{safe_name}.snapshot.json"

    def _should_ignore(self, path: str, key: str) -> bool:
        """Check if path/key should be ignored"""
        if path in self.ignore_paths:
            return True

        if self.ignore_timestamps and key in (
            "timestamp", "created_at", "updated_at",
            "started_at", "finished_at", "elapsed_ms"
        ):
            return True

        if self.ignore_ids and key in (
            "id", "execution_id", "uuid", "step_id"
        ):
            return True

        return False

    def _normalize(
        self,
        data: Any,
        path: str = "",
    ) -> Any:
        """Normalize data for comparison"""
        if isinstance(data, dict):
            result = {}
            for key, value in sorted(data.items()):
                current_path = f"{path}.{key}" if path else key
                if not self._should_ignore(current_path, key):
                    result[key] = self._normalize(value, current_path)
            return result

        if isinstance(data, list):
            return [
                self._normalize(item, f"{path}[{i}]")
                for i, item in enumerate(data)
            ]

        if isinstance(data, datetime):
            return data.isoformat()

        return data

    def _compare(
        self,
        expected: Any,
        actual: Any,
        path: str = "",
    ) -> List[SnapshotDiff]:
        """Compare two values and return differences"""
        differences = []

        if type(expected) != type(actual):
            differences.append(SnapshotDiff(
                path=path or "root",
                expected=expected,
                actual=actual,
                diff_type="type_changed",
            ))
            return differences

        if isinstance(expected, dict):
            all_keys = set(expected.keys()) | set(actual.keys())

            for key in sorted(all_keys):
                current_path = f"{path}.{key}" if path else key

                if key not in expected:
                    differences.append(SnapshotDiff(
                        path=current_path,
                        expected=None,
                        actual=actual[key],
                        diff_type="added",
                    ))
                elif key not in actual:
                    differences.append(SnapshotDiff(
                        path=current_path,
                        expected=expected[key],
                        actual=None,
                        diff_type="removed",
                    ))
                else:
                    differences.extend(
                        self._compare(expected[key], actual[key], current_path)
                    )

        elif isinstance(expected, list):
            if len(expected) != len(actual):
                differences.append(SnapshotDiff(
                    path=path,
                    expected=f"array length {len(expected)}",
                    actual=f"array length {len(actual)}",
                    diff_type="changed",
                ))
            else:
                for i, (exp_item, act_item) in enumerate(zip(expected, actual)):
                    differences.extend(
                        self._compare(exp_item, act_item, f"{path}[{i}]")
                    )

        elif expected != actual:
            differences.append(SnapshotDiff(
                path=path or "root",
                expected=expected,
                actual=actual,
                diff_type="changed",
            ))

        return differences

    def exists(self, name: str) -> bool:
        """Check if snapshot exists"""
        return self._get_snapshot_path(name).exists()

    def load(self, name: str) -> Optional[Dict[str, Any]]:
        """Load snapshot data"""
        path = self._get_snapshot_path(name)

        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load snapshot {name}: {e}")
            return None

    def save(self, name: str, data: Dict[str, Any]) -> str:
        """
        Save snapshot.

        Args:
            name: Snapshot name
            data: Data to snapshot

        Returns:
            Path to saved snapshot
        """
        path = self._get_snapshot_path(name)
        normalized = self._normalize(data)

        snapshot_data = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "data": normalized,
            "hash": hashlib.sha256(
                json.dumps(normalized, sort_keys=True).encode()
            ).hexdigest()[:16],
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved snapshot: {path}")
        return str(path)

    def match(
        self,
        name: str,
        actual: Dict[str, Any],
    ) -> SnapshotResult:
        """
        Compare actual result against snapshot.

        Args:
            name: Snapshot name
            actual: Actual execution result

        Returns:
            Comparison result
        """
        snapshot_path = self._get_snapshot_path(name)

        if not snapshot_path.exists():
            return SnapshotResult(
                status=SnapshotStatus.NEW,
                snapshot_name=name,
                snapshot_path=str(snapshot_path),
            )

        expected_data = self.load(name)
        if not expected_data:
            return SnapshotResult(
                status=SnapshotStatus.NEW,
                snapshot_name=name,
                snapshot_path=str(snapshot_path),
            )

        expected = expected_data.get('data', {})
        normalized_actual = self._normalize(actual)

        differences = self._compare(expected, normalized_actual)

        if differences:
            return SnapshotResult(
                status=SnapshotStatus.MISMATCH,
                snapshot_name=name,
                differences=differences,
                snapshot_path=str(snapshot_path),
                created_at=datetime.fromisoformat(expected_data.get('created_at', '')),
            )

        return SnapshotResult(
            status=SnapshotStatus.MATCH,
            snapshot_name=name,
            snapshot_path=str(snapshot_path),
            created_at=datetime.fromisoformat(expected_data.get('created_at', '')),
        )

    def update(
        self,
        name: str,
        data: Dict[str, Any],
    ) -> str:
        """
        Update snapshot with new data.

        Args:
            name: Snapshot name
            data: New data

        Returns:
            Path to updated snapshot
        """
        return self.save(name, data)

    def delete(self, name: str) -> bool:
        """
        Delete a snapshot.

        Args:
            name: Snapshot name

        Returns:
            True if deleted, False if not found
        """
        path = self._get_snapshot_path(name)

        if path.exists():
            path.unlink()
            return True

        return False

    def list_snapshots(self) -> List[str]:
        """List all snapshot names"""
        snapshots = []

        for path in self.snapshot_dir.glob("*.snapshot.json"):
            name = path.stem.replace(".snapshot", "")
            snapshots.append(name)

        return sorted(snapshots)

    def find_obsolete(
        self,
        active_tests: List[str],
    ) -> List[str]:
        """
        Find snapshots without corresponding tests.

        Args:
            active_tests: List of active test names

        Returns:
            List of obsolete snapshot names
        """
        all_snapshots = set(self.list_snapshots())
        active_set = set(active_tests)

        return sorted(all_snapshots - active_set)

    def cleanup_obsolete(
        self,
        active_tests: List[str],
    ) -> int:
        """
        Delete obsolete snapshots.

        Args:
            active_tests: List of active test names

        Returns:
            Number of snapshots deleted
        """
        obsolete = self.find_obsolete(active_tests)

        for name in obsolete:
            self.delete(name)

        return len(obsolete)


# =============================================================================
# Factory Functions
# =============================================================================

def create_snapshot_manager(
    snapshot_dir: Optional[Path] = None,
    ignore_timestamps: bool = True,
) -> SnapshotManager:
    """
    Create a snapshot manager.

    Args:
        snapshot_dir: Directory for snapshots
        ignore_timestamps: Whether to ignore timestamp fields

    Returns:
        Configured SnapshotManager
    """
    if snapshot_dir is None:
        snapshot_dir = Path("./snapshots")

    return SnapshotManager(
        snapshot_dir=snapshot_dir,
        ignore_timestamps=ignore_timestamps,
    )
