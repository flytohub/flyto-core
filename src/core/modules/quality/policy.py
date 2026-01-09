"""
Severity Policy

Defines severity policies for different CI/CD gate levels.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from .types import GateLevel, Severity


@dataclass
class SeverityPolicy:
    """
    Severity policy for a specific gate level.

    Determines which severity levels block validation based on the gate.
    """
    gate: GateLevel
    blocking_severities: Set[Severity] = field(default_factory=set)
    upgrade_severities: Dict[Severity, Severity] = field(default_factory=dict)
    stable_only_strict: bool = False

    def should_block(self, severity: Severity, stability: str = "stable") -> bool:
        """
        Check if an issue should block based on severity and module stability.

        Args:
            severity: The issue severity
            stability: The module stability level (stable, beta, alpha, etc.)

        Returns:
            True if the issue should block validation
        """
        # Apply severity upgrade if configured
        effective_severity = self.upgrade_severities.get(severity, severity)

        # For stable_only_strict, non-stable modules are less strict
        if self.stable_only_strict and stability != "stable":
            # Only BLOCKER and FATAL block for non-stable modules
            return effective_severity in (Severity.BLOCKER, Severity.FATAL)

        return effective_severity in self.blocking_severities

    def get_effective_severity(self, severity: Severity) -> Severity:
        """Get the effective severity after applying upgrades."""
        return self.upgrade_severities.get(severity, severity)


# Predefined policies for each gate level

DEV_POLICY = SeverityPolicy(
    gate=GateLevel.DEV,
    blocking_severities={Severity.FATAL},
    upgrade_severities={},
    stable_only_strict=False,
)

CI_POLICY = SeverityPolicy(
    gate=GateLevel.CI,
    blocking_severities={Severity.ERROR, Severity.BLOCKER, Severity.FATAL},
    upgrade_severities={},
    stable_only_strict=True,
)

RELEASE_POLICY = SeverityPolicy(
    gate=GateLevel.RELEASE,
    blocking_severities={Severity.ERROR, Severity.BLOCKER, Severity.FATAL},
    upgrade_severities={},
    stable_only_strict=False,
)

STRICT_POLICY = SeverityPolicy(
    gate=GateLevel.STRICT,
    blocking_severities={Severity.INFO, Severity.WARN, Severity.ERROR, Severity.BLOCKER, Severity.FATAL},
    upgrade_severities={
        Severity.INFO: Severity.WARN,
        Severity.WARN: Severity.ERROR,
    },
    stable_only_strict=False,
)


def get_policy(gate: GateLevel) -> SeverityPolicy:
    """Get the predefined policy for a gate level."""
    policies = {
        GateLevel.DEV: DEV_POLICY,
        GateLevel.CI: CI_POLICY,
        GateLevel.RELEASE: RELEASE_POLICY,
        GateLevel.STRICT: STRICT_POLICY,
    }
    return policies.get(gate, CI_POLICY)
