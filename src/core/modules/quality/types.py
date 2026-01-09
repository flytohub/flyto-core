"""
Validation Types

Core types for the module validation system.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    """Validation issue severity levels."""
    INFO = "INFO"          # Pass, just log
    WARN = "WARN"          # Pass, but warn
    ERROR = "ERROR"        # Fail PR
    BLOCKER = "BLOCKER"    # Fail release
    FATAL = "FATAL"        # Fail immediately (syntax errors)


class StrictLevel(str, Enum):
    """Strict mode levels for validation."""
    DEFAULT = "default"    # Only BLOCKER/FATAL fail
    TIMEOUT = "timeout"    # + timeout_ms required
    STABLE = "stable"      # + stable modules strict
    RELEASE = "release"    # + all ERROR rules enforced
    ALL = "all"            # + WARN becomes ERROR


class RuleStage(str, Enum):
    """3-stage execution stages for lint rules."""
    METADATA = "metadata"  # Stage 1: Registry metadata only (fast)
    AST = "ast"            # Stage 2: AST parsing required
    SECURITY = "security"  # Stage 3: Deep security scan


class GateLevel(str, Enum):
    """CI/CD gate levels for severity policy."""
    DEV = "dev"            # Development: only FATAL blocks
    CI = "ci"              # CI: ERROR and above blocks
    RELEASE = "release"    # Release: BLOCKER and above blocks
    STRICT = "strict"      # Strict: all issues block


@dataclass
class ValidationIssue:
    """A single validation issue."""
    rule_id: str
    severity: Severity
    message: str
    module_id: str = ""
    file: str = ""
    line: int = 0
    col: int = 0
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "module_id": self.module_id,
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "suggestion": self.suggestion,
        }

    def format(self) -> str:
        """Format issue for display."""
        loc = f"{self.file}:{self.line}" if self.file else self.module_id
        msg = f"[{self.rule_id}] {self.severity.value}: {self.message}"
        if loc:
            msg = f"{loc} - {msg}"
        if self.suggestion:
            msg += f" (Suggestion: {self.suggestion})"
        return msg


@dataclass
class ValidationReport:
    """Complete validation report for a module or set of modules."""
    module_id: str = ""
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Check if validation passed (no ERROR/BLOCKER/FATAL)."""
        return not any(
            i.severity in (Severity.ERROR, Severity.BLOCKER, Severity.FATAL)
            for i in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return any(i.severity == Severity.WARN for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARN)

    @property
    def warn_count(self) -> int:
        """Alias for warning_count."""
        return self.warning_count

    @property
    def blocker_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.BLOCKER)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "counts": {
                "error": self.error_count,
                "warning": self.warning_count,
                "blocker": self.blocker_count,
            },
        }


@dataclass
class AggregateReport:
    """Aggregate report for multiple modules."""
    reports: List[ValidationReport] = field(default_factory=list)
    strict_level: StrictLevel = StrictLevel.DEFAULT

    @property
    def total_modules(self) -> int:
        return len(self.reports)

    @property
    def passed_modules(self) -> int:
        return sum(1 for r in self.reports if r.passed)

    @property
    def failed_modules(self) -> int:
        return self.total_modules - self.passed_modules

    @property
    def total_errors(self) -> int:
        return sum(r.error_count for r in self.reports)

    @property
    def total_warnings(self) -> int:
        return sum(r.warning_count for r in self.reports)

    @property
    def total_blockers(self) -> int:
        return sum(r.blocker_count for r in self.reports)

    @property
    def all_issues(self) -> List[ValidationIssue]:
        issues = []
        for r in self.reports:
            issues.extend(r.issues)
        return issues

    @property
    def total_issues(self) -> int:
        return len(self.all_issues)

    @property
    def issues_by_severity(self) -> Dict[str, int]:
        """Count issues by severity level."""
        counts: Dict[str, int] = {}
        for issue in self.all_issues:
            sev = issue.severity.value
            counts[sev] = counts.get(sev, 0) + 1
        return counts

    @property
    def issues_by_category(self) -> Dict[str, int]:
        """Count issues by rule category (extracted from rule_id prefix)."""
        counts: Dict[str, int] = {}
        for issue in self.all_issues:
            # Extract category from rule_id like "CORE-AST-001" -> "ast"
            parts = issue.rule_id.split("-")
            if len(parts) >= 2:
                category = parts[1].lower()
            else:
                category = "unknown"
            counts[category] = counts.get(category, 0) + 1
        return counts

    def passed(self) -> bool:
        """Check if validation passed based on strict level."""
        if self.strict_level == StrictLevel.ALL:
            # All issues are errors
            return len(self.all_issues) == 0

        if self.strict_level == StrictLevel.RELEASE:
            # No errors or blockers allowed
            return self.total_errors == 0 and self.total_blockers == 0

        if self.strict_level == StrictLevel.STABLE:
            # Stable modules must pass
            for r in self.reports:
                stability = r.metadata.get("stability", "stable")
                if stability == "stable" and not r.passed:
                    return False
            return True

        if self.strict_level == StrictLevel.TIMEOUT:
            # Check timeout_ms presence
            for r in self.reports:
                if r.metadata.get("timeout_ms") is None:
                    return False
            return True

        # Default: only blockers fail
        return self.total_blockers == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strict_level": self.strict_level.value,
            "passed": self.passed(),
            "summary": {
                "total_modules": self.total_modules,
                "passed_modules": self.passed_modules,
                "failed_modules": self.failed_modules,
                "total_errors": self.total_errors,
                "total_warnings": self.total_warnings,
                "total_blockers": self.total_blockers,
            },
            "reports": [r.to_dict() for r in self.reports],
        }

    def format_summary(self) -> str:
        """Format summary for CLI output."""
        lines = [
            "=" * 60,
            "Flyto-Core Module Validation Report",
            "=" * 60,
            "",
            f"Strict Level:     {self.strict_level.value}",
            f"Total Modules:    {self.total_modules}",
            f"Passed:           {self.passed_modules}",
            f"Failed:           {self.failed_modules}",
            "",
            f"Errors:           {self.total_errors}",
            f"Warnings:         {self.total_warnings}",
            f"Blockers:         {self.total_blockers}",
            "",
            "=" * 60,
        ]

        if self.passed():
            lines.append("RESULT: PASSED")
        else:
            lines.append("RESULT: FAILED")

        lines.append("=" * 60)
        return "\n".join(lines)
