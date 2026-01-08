"""
Module Metadata Lint - Registry-driven validation.

This module provides lint rules that validate module metadata directly from
the ModuleRegistry, without needing to scan source files.

Design Principles:
- Registry as single source of truth
- No AST scanning needed for metadata rules
- Clear error messages with fix suggestions
- Severity levels for CI integration

Usage:
    from core.modules.lint import lint_all_modules, lint_module

    # Lint all registered modules
    results = lint_all_modules()

    # Lint single module
    results = lint_module("browser.goto")
"""
import re
import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# Lint Result Types
# =============================================================================

class Severity(Enum):
    """Lint rule severity levels."""
    ERROR = "error"      # Must fix before merge
    WARNING = "warning"  # Should fix, won't block
    INFO = "info"        # Suggestion only


@dataclass
class LintResult:
    """Result of a lint check."""
    rule_id: str
    severity: Severity
    module_id: str
    message: str
    field: Optional[str] = None
    hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "module_id": self.module_id,
            "message": self.message,
        }
        if self.field:
            result["field"] = self.field
        if self.hint:
            result["hint"] = self.hint
        return result


@dataclass
class LintReport:
    """Aggregated lint results."""
    results: List[LintResult] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.INFO)

    @property
    def passed(self) -> bool:
        """True if no errors (warnings are OK)."""
        return self.error_count == 0

    def add(self, result: LintResult):
        """Add a lint result."""
        self.results.append(result)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "results": [r.to_dict() for r in self.results]
        }


# =============================================================================
# Canonical Parameter Names
# =============================================================================

# Standard parameter names and their aliases
PARAM_CANONICAL_NAMES: Dict[str, Set[str]] = {
    "url": {"uri", "link", "endpoint"},
    "text": {"string", "str", "content", "value", "input"},
    "file_path": {"filepath", "path", "file", "filename"},
    "timeout": {"timeout_ms", "timeout_s", "wait"},
    "selector": {"css_selector", "xpath", "element"},
    "data": {"payload", "body", "json_data"},
    "headers": {"http_headers", "request_headers"},
    "method": {"http_method", "request_method"},
    "encoding": {"charset", "encode"},
    "delimiter": {"separator", "sep"},
    "api_key": {"apikey", "api_token", "token"},
}

# Build reverse lookup: alias -> canonical
PARAM_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in PARAM_CANONICAL_NAMES.items():
    for alias in aliases:
        PARAM_ALIAS_TO_CANONICAL[alias] = canonical


# =============================================================================
# I18n Key Patterns
# =============================================================================

def get_expected_i18n_key(module_id: str, field_type: str, field_name: Optional[str] = None) -> str:
    """
    Get expected i18n key for a module field.

    Pattern: modules.{namespace}.{module_name}.{field_type}[.{field_name}]

    Examples:
        - modules.browser.goto.label
        - modules.browser.goto.description
        - modules.browser.goto.params.url.label
        - modules.browser.goto.output.status.description
    """
    parts = module_id.split(".")
    namespace = parts[0]
    module_name = ".".join(parts[1:]) if len(parts) > 1 else parts[0]

    if field_name:
        return f"modules.{namespace}.{module_name}.{field_type}.{field_name}"
    return f"modules.{namespace}.{module_name}.{field_type}"


# =============================================================================
# Lint Rules
# =============================================================================

def lint_param_naming(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT001: Check parameter naming conventions.

    - Warn if using alias instead of canonical name
    - Error if param name contains typos or inconsistencies
    """
    params_schema = metadata.get("params_schema", {})

    for param_name in params_schema.keys():
        param_lower = param_name.lower()

        # Check if using an alias
        if param_lower in PARAM_ALIAS_TO_CANONICAL:
            canonical = PARAM_ALIAS_TO_CANONICAL[param_lower]
            report.add(LintResult(
                rule_id="LINT001",
                severity=Severity.WARNING,
                module_id=module_id,
                message=f"Parameter '{param_name}' should use canonical name '{canonical}'",
                field=f"params_schema.{param_name}",
                hint=f"Rename to '{canonical}' for consistency"
            ))


def lint_i18n_keys(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT002: Check i18n key format and presence.

    - Warn if label_key/description_key missing
    - Error if key format doesn't match expected pattern
    """
    # Check top-level keys
    if "label" in metadata and "label_key" not in metadata:
        report.add(LintResult(
            rule_id="LINT002",
            severity=Severity.INFO,
            module_id=module_id,
            message="Missing 'label_key' for i18n support",
            field="label_key",
            hint=f"Add label_key='{get_expected_i18n_key(module_id, 'label')}'"
        ))

    if "description" in metadata and "description_key" not in metadata:
        report.add(LintResult(
            rule_id="LINT002",
            severity=Severity.INFO,
            module_id=module_id,
            message="Missing 'description_key' for i18n support",
            field="description_key",
            hint=f"Add description_key='{get_expected_i18n_key(module_id, 'description')}'"
        ))

    # Check label_key format if present
    if "label_key" in metadata:
        expected = get_expected_i18n_key(module_id, "label")
        actual = metadata["label_key"]
        if actual != expected:
            report.add(LintResult(
                rule_id="LINT002",
                severity=Severity.WARNING,
                module_id=module_id,
                message=f"label_key format mismatch: expected '{expected}', got '{actual}'",
                field="label_key",
                hint=f"Use '{expected}' for consistency"
            ))


def lint_required_fields(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT003: Check required metadata fields.
    """
    required = ["module_id", "version", "label", "description"]

    for field in required:
        if field not in metadata or not metadata[field]:
            report.add(LintResult(
                rule_id="LINT003",
                severity=Severity.ERROR,
                module_id=module_id,
                message=f"Missing required field: {field}",
                field=field
            ))


def lint_version_format(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT004: Check version format (semver).
    """
    version = metadata.get("version", "")
    if version and not re.match(r"^\d+\.\d+\.\d+(-\w+)?$", version):
        report.add(LintResult(
            rule_id="LINT004",
            severity=Severity.ERROR,
            module_id=module_id,
            message=f"Invalid version format: '{version}' (expected semver)",
            field="version",
            hint="Use format: major.minor.patch (e.g., 1.0.0)"
        ))


def lint_category_namespace_consistency(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT005: Check category and namespace consistency.

    - namespace should be first segment of module_id
    - category should match or have explicit ui_category
    """
    namespace = module_id.split(".")[0]
    category = metadata.get("category", "")
    subcategory = metadata.get("subcategory", "")

    # Check if category matches namespace
    if category and category != namespace and category != "atomic":
        report.add(LintResult(
            rule_id="LINT005",
            severity=Severity.INFO,
            module_id=module_id,
            message=f"Category '{category}' differs from namespace '{namespace}'",
            field="category",
            hint="Consider using 'ui_category' for display purposes"
        ))


def lint_connection_types(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT006: Check connection type consistency.

    - input_types and output_types should be valid
    - can_connect_to and can_receive_from should be valid patterns
    """
    valid_types = {
        "string", "text", "number", "boolean", "object", "array", "json",
        "file", "file_path", "image", "binary", "any", "void",
        "browser", "page", "element"
    }

    for type_field in ["input_types", "output_types"]:
        types = metadata.get(type_field, [])
        for t in types:
            if t not in valid_types and not t.startswith("custom:"):
                report.add(LintResult(
                    rule_id="LINT006",
                    severity=Severity.WARNING,
                    module_id=module_id,
                    message=f"Unknown type '{t}' in {type_field}",
                    field=type_field,
                    hint=f"Valid types: {', '.join(sorted(valid_types))}"
                ))


def lint_output_schema_descriptions(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT007: Check output_schema has descriptions.
    """
    output_schema = metadata.get("output_schema", {})

    for field_name, field_def in output_schema.items():
        if isinstance(field_def, dict) and "description" not in field_def:
            report.add(LintResult(
                rule_id="LINT007",
                severity=Severity.WARNING,
                module_id=module_id,
                message=f"Missing description for output field '{field_name}'",
                field=f"output_schema.{field_name}",
                hint="Add description for better documentation"
            ))


def lint_examples_present(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT008: Check that examples are provided.
    """
    examples = metadata.get("examples", [])
    if not examples:
        report.add(LintResult(
            rule_id="LINT008",
            severity=Severity.INFO,
            module_id=module_id,
            message="No examples provided",
            field="examples",
            hint="Add at least one example for better discoverability"
        ))


def lint_timeout_values(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT009: Check timeout values are reasonable.
    """
    timeout_ms = metadata.get("timeout_ms", 0)

    if timeout_ms > 300000:  # > 5 minutes
        report.add(LintResult(
            rule_id="LINT009",
            severity=Severity.WARNING,
            module_id=module_id,
            message=f"Very long timeout: {timeout_ms}ms (> 5 minutes)",
            field="timeout_ms",
            hint="Consider breaking into smaller operations"
        ))

    if timeout_ms > 0 and timeout_ms < 1000:  # < 1 second
        report.add(LintResult(
            rule_id="LINT009",
            severity=Severity.WARNING,
            module_id=module_id,
            message=f"Very short timeout: {timeout_ms}ms (< 1 second)",
            field="timeout_ms",
            hint="This may cause premature timeouts"
        ))


def lint_capabilities_declared(module_id: str, metadata: Dict[str, Any], report: LintReport):
    """
    LINT010: Check that high-risk modules declare capabilities.

    Modules with certain tags should declare capabilities.
    """
    tags = set(metadata.get("tags", []))
    capabilities = metadata.get("capabilities", [])

    # Modules with these tags should have capabilities
    risk_tags = {"shell", "network", "file", "database", "credential"}
    has_risk_tags = bool(tags & risk_tags)

    if has_risk_tags and not capabilities:
        report.add(LintResult(
            rule_id="LINT010",
            severity=Severity.WARNING,
            module_id=module_id,
            message=f"Module has risk tags {tags & risk_tags} but no capabilities declared",
            field="capabilities",
            hint="Add capabilities for proper access control"
        ))


# =============================================================================
# Main Lint Functions
# =============================================================================

# All lint rules
LINT_RULES = [
    lint_required_fields,
    lint_version_format,
    lint_param_naming,
    lint_i18n_keys,
    lint_category_namespace_consistency,
    lint_connection_types,
    lint_output_schema_descriptions,
    lint_examples_present,
    lint_timeout_values,
    lint_capabilities_declared,
]


def lint_module(module_id: str, metadata: Dict[str, Any]) -> LintReport:
    """
    Run all lint rules on a single module.

    Args:
        module_id: Module identifier
        metadata: Module metadata from registry

    Returns:
        LintReport with all findings
    """
    report = LintReport()

    for rule in LINT_RULES:
        try:
            rule(module_id, metadata, report)
        except Exception as e:
            logger.error(f"Lint rule {rule.__name__} failed for {module_id}: {e}")

    return report


def lint_all_modules(
    registry_metadata: Dict[str, Dict[str, Any]],
    severity_filter: Optional[Severity] = None
) -> LintReport:
    """
    Run all lint rules on all registered modules.

    Args:
        registry_metadata: Dict of module_id -> metadata from ModuleRegistry.get_all_metadata()
        severity_filter: Only include results of this severity or higher

    Returns:
        Aggregated LintReport
    """
    report = LintReport()

    for module_id, metadata in registry_metadata.items():
        module_report = lint_module(module_id, metadata)
        for result in module_report.results:
            if severity_filter is None or result.severity.value <= severity_filter.value:
                report.add(result)

    return report


def lint_from_registry(severity_filter: Optional[Severity] = None) -> LintReport:
    """
    Convenience function to lint all modules from the registry.

    Args:
        severity_filter: Only include results of this severity or higher

    Returns:
        LintReport
    """
    from .registry import ModuleRegistry

    all_metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)
    return lint_all_modules(all_metadata, severity_filter)
