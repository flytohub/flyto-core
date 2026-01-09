"""
Baseline

Manages exemptions for lint rules, allowing time-limited or module-specific bypasses.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set


@dataclass
class Baseline:
    """
    Baseline for lint rule exemptions.

    Allows exempting specific rules globally or for specific modules,
    with optional expiration dates.
    """
    exempt_rules: Set[str] = field(default_factory=set)
    module_exemptions: Dict[str, Set[str]] = field(default_factory=dict)
    expires_at: Optional[datetime] = None
    reason: str = ""
    created_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if this baseline has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def is_exempt(self, module_id: str, rule_id: str) -> bool:
        """
        Check if a specific module/rule combination is exempt.

        Args:
            module_id: The module identifier
            rule_id: The rule identifier (e.g., "CORE-AST-001")

        Returns:
            True if this combination is exempt from validation
        """
        if self.is_expired():
            return False

        # Check global exemptions
        if rule_id in self.exempt_rules:
            return True

        # Check module-specific exemptions
        if module_id in self.module_exemptions:
            if rule_id in self.module_exemptions[module_id]:
                return True

        return False

    def add_global_exemption(self, rule_id: str) -> None:
        """Add a global rule exemption."""
        self.exempt_rules.add(rule_id)

    def add_module_exemption(self, module_id: str, rule_id: str) -> None:
        """Add a module-specific rule exemption."""
        if module_id not in self.module_exemptions:
            self.module_exemptions[module_id] = set()
        self.module_exemptions[module_id].add(rule_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert baseline to dictionary for JSON serialization."""
        return {
            "exempt_rules": sorted(self.exempt_rules),
            "module_exemptions": {
                k: sorted(v) for k, v in self.module_exemptions.items()
            },
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Baseline":
        """Create baseline from dictionary."""
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])

        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            exempt_rules=set(data.get("exempt_rules", [])),
            module_exemptions={
                k: set(v) for k, v in data.get("module_exemptions", {}).items()
            },
            expires_at=expires_at,
            reason=data.get("reason", ""),
            created_at=created_at,
        )

    @classmethod
    def from_file(cls, path: Path) -> "Baseline":
        """Load baseline from a JSON file."""
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls.from_dict(data)

    def save_to_file(self, path: Path) -> None:
        """Save baseline to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def create_baseline(
    exempt_rules: Optional[Set[str]] = None,
    module_exemptions: Optional[Dict[str, Set[str]]] = None,
    expires_in_days: Optional[int] = None,
    reason: str = "",
) -> Baseline:
    """
    Create a new baseline with optional expiration.

    Args:
        exempt_rules: Set of rule IDs to exempt globally
        module_exemptions: Dict of module_id -> set of rule IDs
        expires_in_days: Number of days until expiration (None = never)
        reason: Reason for the baseline

    Returns:
        A new Baseline instance
    """
    from datetime import timedelta

    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.now() + timedelta(days=expires_in_days)

    return Baseline(
        exempt_rules=exempt_rules or set(),
        module_exemptions=module_exemptions or {},
        expires_at=expires_at,
        reason=reason,
        created_at=datetime.now(),
    )
