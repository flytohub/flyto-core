"""
flyto-core Module Quality System

A comprehensive quality validation framework for flyto modules.
Validates code quality, security, permissions, and metadata compliance.

Features:
- 3-stage execution: Metadata -> AST -> Security
- 28+ validation rules across 6 categories
- Stability-aware severity adjustment
- AST-based code analysis
- SeverityPolicy for CI gate control
- Baseline exemptions support
- Auto-fix infrastructure

Categories:
- Identity (CORE-ID): module_id, stability, version
- Execution (CORE-EX): timeout_ms, retryable, max_retries
- Schema (CORE-SCH): params_schema, output_schema
- Capability (CORE-CAP): permissions, capability detection
- Security (CORE-SEC): secrets, credentials, sensitive data
- AST (CORE-AST): syntax, async, print statements

Usage:
    from core.modules.quality import ValidationEngine, StrictLevel

    engine = ValidationEngine(strict_level=StrictLevel.STABLE)
    report = engine.validate_module(
        module_id="browser.click",
        metadata=module_metadata,
        source_code=source_code,
    )

    if not report.passed:
        for issue in report.issues:
            print(f"[{issue.severity}] {issue.rule_id}: {issue.message}")
"""

from .types import (
    Severity,
    StrictLevel,
    RuleStage,
    GateLevel,
    ValidationIssue,
    ValidationReport,
    AggregateReport,
)
from .engine import (
    ValidationEngine,
    discover_modules,
    validate_single_file,
    run_validation,
)
from .constants import (
    VALID_PERMISSIONS,
    IMPORT_CAPABILITY_MAP,
    SECRET_PATTERNS,
    SENSITIVE_PARAM_PATTERNS,
)
from .policy import (
    SeverityPolicy,
    get_policy,
    DEV_POLICY,
    CI_POLICY,
    RELEASE_POLICY,
    STRICT_POLICY,
)
from .baseline import Baseline, create_baseline
from .report import ReportGenerator, generate_report
from .fixer import FixRunner, FixResult, FixableRule

__all__ = [
    # Types
    "Severity",
    "StrictLevel",
    "RuleStage",
    "GateLevel",
    "ValidationIssue",
    "ValidationReport",
    "AggregateReport",
    # Engine
    "ValidationEngine",
    "discover_modules",
    "validate_single_file",
    "run_validation",
    # Policy
    "SeverityPolicy",
    "get_policy",
    "DEV_POLICY",
    "CI_POLICY",
    "RELEASE_POLICY",
    "STRICT_POLICY",
    # Baseline
    "Baseline",
    "create_baseline",
    # Report
    "ReportGenerator",
    "generate_report",
    # Fixer
    "FixRunner",
    "FixResult",
    "FixableRule",
    # Constants
    "VALID_PERMISSIONS",
    "IMPORT_CAPABILITY_MAP",
    "SECRET_PATTERNS",
    "SENSITIVE_PARAM_PATTERNS",
]

__version__ = "1.1.0"
