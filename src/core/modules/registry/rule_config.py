"""
Validation Rule Configuration

Defines which rules are mandatory (cannot disable) vs optional (user can disable).
This allows users to customize validation strictness while maintaining security.

Categories:
    MANDATORY: Security-critical rules, always enforced
    RECOMMENDED: Best practices, enabled by default, can be disabled
    OPTIONAL: Extra checks, disabled by default, can be enabled

Usage:
    from core.modules.registry.rule_config import RuleConfig, get_active_rules

    # Get rules that should be enforced
    active_rules = get_active_rules(disabled=['Q010', 'Q012'])
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set


class RuleCategory(Enum):
    """Rule enforcement category."""
    MANDATORY = "mandatory"      # Cannot be disabled (security)
    RECOMMENDED = "recommended"  # Default on, can disable
    OPTIONAL = "optional"        # Default off, can enable


@dataclass
class RuleDefinition:
    """Definition of a validation rule."""
    rule_id: str
    name: str
    category: RuleCategory
    description: str
    severity: str = "error"  # error, warning, info


# =============================================================================
# Rule Definitions
# =============================================================================

RULE_DEFINITIONS: Dict[str, RuleDefinition] = {
    # =========================================================================
    # MANDATORY Rules (Cannot be disabled) - Security Critical
    # =========================================================================

    # Security Rules
    "SEC004": RuleDefinition(
        rule_id="SEC004",
        name="Hardcoded Secrets",
        category=RuleCategory.MANDATORY,
        description="Detects hardcoded API keys, passwords, and tokens",
        severity="error",
    ),
    "SEC005": RuleDefinition(
        rule_id="SEC005",
        name="Command Injection",
        category=RuleCategory.MANDATORY,
        description="Detects shell=True with dynamic commands",
        severity="error",
    ),
    "SEC006": RuleDefinition(
        rule_id="SEC006",
        name="SQL Injection",
        category=RuleCategory.MANDATORY,
        description="Detects SQL queries with string interpolation",
        severity="error",
    ),
    "SEC007": RuleDefinition(
        rule_id="SEC007",
        name="Eval/Exec Usage",
        category=RuleCategory.MANDATORY,
        description="Detects dangerous eval() and exec() usage",
        severity="error",
    ),

    # Critical Quality Rules
    "Q001": RuleDefinition(
        rule_id="Q001",
        name="Syntax Errors",
        category=RuleCategory.MANDATORY,
        description="Code must be syntactically valid Python",
        severity="error",
    ),
    "Q003": RuleDefinition(
        rule_id="Q003",
        name="No Chinese Identifiers",
        category=RuleCategory.MANDATORY,
        description="Identifiers must use English characters only",
        severity="error",
    ),

    # Critical Runtime Rules
    "RT001": RuleDefinition(
        rule_id="RT001",
        name="Module Structure",
        category=RuleCategory.MANDATORY,
        description="Module must have async execute() method",
        severity="error",
    ),

    # Critical Metadata Rules
    "M001": RuleDefinition(
        rule_id="M001",
        name="Module ID Format",
        category=RuleCategory.MANDATORY,
        description="Module ID must follow category.action format",
        severity="error",
    ),
    "M005": RuleDefinition(
        rule_id="M005",
        name="Connection Rules",
        category=RuleCategory.MANDATORY,
        description="Must define can_receive_from and can_connect_to",
        severity="error",
    ),

    # =========================================================================
    # RECOMMENDED Rules (Default on, can disable) - Best Practices
    # =========================================================================

    "Q002": RuleDefinition(
        rule_id="Q002",
        name="No print() Statements",
        category=RuleCategory.RECOMMENDED,
        description="Use logging instead of print()",
        severity="error",
    ),
    "Q004": RuleDefinition(
        rule_id="Q004",
        name="Docstrings Required",
        category=RuleCategory.RECOMMENDED,
        description="Classes and functions should have docstrings",
        severity="error",
    ),
    "Q005": RuleDefinition(
        rule_id="Q005",
        name="Async Execute",
        category=RuleCategory.RECOMMENDED,
        description="execute() method must be async",
        severity="error",
    ),
    "Q006": RuleDefinition(
        rule_id="Q006",
        name="Validate Params Method",
        category=RuleCategory.RECOMMENDED,
        description="Module should have validate_params() method",
        severity="error",
    ),
    "Q008": RuleDefinition(
        rule_id="Q008",
        name="Output Schema Required",
        category=RuleCategory.RECOMMENDED,
        description="Module should define output_schema",
        severity="error",
    ),
    "S002": RuleDefinition(
        rule_id="S002",
        name="Output Schema Presence",
        category=RuleCategory.RECOMMENDED,
        description="output_schema must be defined",
        severity="error",
    ),
    "S005": RuleDefinition(
        rule_id="S005",
        name="Default Type Match",
        category=RuleCategory.RECOMMENDED,
        description="Parameter default values must match declared types",
        severity="error",
    ),

    # =========================================================================
    # OPTIONAL Rules (Default off, can enable) - Extra Strictness
    # =========================================================================

    "Q007": RuleDefinition(
        rule_id="Q007",
        name="Params Schema Required",
        category=RuleCategory.OPTIONAL,
        description="Module should define params_schema",
        severity="warning",
    ),
    "Q009": RuleDefinition(
        rule_id="Q009",
        name="Type Hints Required",
        category=RuleCategory.OPTIONAL,
        description="Methods should have return type hints",
        severity="warning",
    ),
    "Q010": RuleDefinition(
        rule_id="Q010",
        name="Complexity Limit",
        category=RuleCategory.OPTIONAL,
        description="Cyclomatic complexity should be < 15",
        severity="warning",
    ),
    "Q011": RuleDefinition(
        rule_id="Q011",
        name="Unused Imports",
        category=RuleCategory.OPTIONAL,
        description="Detect and remove unused imports",
        severity="warning",
    ),
    "Q012": RuleDefinition(
        rule_id="Q012",
        name="Function Length",
        category=RuleCategory.OPTIONAL,
        description="Functions should be < 50 lines",
        severity="warning",
    ),
    "S001": RuleDefinition(
        rule_id="S001",
        name="Params Schema Presence",
        category=RuleCategory.OPTIONAL,
        description="params_schema should be defined",
        severity="warning",
    ),
    "S003": RuleDefinition(
        rule_id="S003",
        name="Schema Field Types",
        category=RuleCategory.OPTIONAL,
        description="Schema fields should have valid types",
        severity="warning",
    ),
    "S004": RuleDefinition(
        rule_id="S004",
        name="Output Descriptions",
        category=RuleCategory.OPTIONAL,
        description="Output fields should have descriptions",
        severity="warning",
    ),
    "S006": RuleDefinition(
        rule_id="S006",
        name="Required Params Validated",
        category=RuleCategory.OPTIONAL,
        description="Required params should be validated in validate_params()",
        severity="warning",
    ),
    "C001": RuleDefinition(
        rule_id="C001",
        name="Retryable Consistency",
        category=RuleCategory.OPTIONAL,
        description="retryable=True requires max_retries >= 1",
        severity="warning",
    ),
    "C002": RuleDefinition(
        rule_id="C002",
        name="Network Timeout",
        category=RuleCategory.OPTIONAL,
        description="Network modules should define timeout",
        severity="warning",
    ),
    "C003": RuleDefinition(
        rule_id="C003",
        name="Credential Source",
        category=RuleCategory.OPTIONAL,
        description="Modules requiring credentials should declare source",
        severity="warning",
    ),
    "C004": RuleDefinition(
        rule_id="C004",
        name="Sensitive Data Permissions",
        category=RuleCategory.OPTIONAL,
        description="Modules handling sensitive data need permissions",
        severity="warning",
    ),
    "C005": RuleDefinition(
        rule_id="C005",
        name="Error Handling",
        category=RuleCategory.OPTIONAL,
        description="Network/file modules should have try-except",
        severity="warning",
    ),
    "C006": RuleDefinition(
        rule_id="C006",
        name="Logging Usage",
        category=RuleCategory.OPTIONAL,
        description="Use logging instead of print()",
        severity="warning",
    ),
    "SEC001": RuleDefinition(
        rule_id="SEC001",
        name="SSRF Protection",
        category=RuleCategory.OPTIONAL,
        description="Network modules should declare SSRF protection",
        severity="warning",
    ),
    "SEC002": RuleDefinition(
        rule_id="SEC002",
        name="Path Scope",
        category=RuleCategory.OPTIONAL,
        description="File modules should declare path scope",
        severity="warning",
    ),
    "SEC003": RuleDefinition(
        rule_id="SEC003",
        name="Capability Declaration",
        category=RuleCategory.OPTIONAL,
        description="Inferred capabilities should match declarations",
        severity="warning",
    ),
    "RT002": RuleDefinition(
        rule_id="RT002",
        name="Output Format",
        category=RuleCategory.OPTIONAL,
        description="execute() should return {'ok': bool, ...}",
        severity="warning",
    ),
    "RT003": RuleDefinition(
        rule_id="RT003",
        name="Error Format",
        category=RuleCategory.OPTIONAL,
        description="Error returns should be dict, not raw string",
        severity="warning",
    ),
    "RT004": RuleDefinition(
        rule_id="RT004",
        name="Instantiable",
        category=RuleCategory.OPTIONAL,
        description="Module should be instantiable with empty params",
        severity="warning",
    ),
    "I001": RuleDefinition(
        rule_id="I001",
        name="Label Fallback",
        category=RuleCategory.OPTIONAL,
        description="label_key should have label fallback",
        severity="warning",
    ),
    "I002": RuleDefinition(
        rule_id="I002",
        name="Description Fallback",
        category=RuleCategory.OPTIONAL,
        description="description_key should have description fallback",
        severity="warning",
    ),
    "M002": RuleDefinition(
        rule_id="M002",
        name="Recommended Fields",
        category=RuleCategory.OPTIONAL,
        description="Module should have category and version",
        severity="warning",
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_mandatory_rules() -> Set[str]:
    """Get rule IDs that cannot be disabled."""
    return {
        rule_id for rule_id, rule in RULE_DEFINITIONS.items()
        if rule.category == RuleCategory.MANDATORY
    }


def get_recommended_rules() -> Set[str]:
    """Get rule IDs that are on by default but can be disabled."""
    return {
        rule_id for rule_id, rule in RULE_DEFINITIONS.items()
        if rule.category == RuleCategory.RECOMMENDED
    }


def get_optional_rules() -> Set[str]:
    """Get rule IDs that are off by default but can be enabled."""
    return {
        rule_id for rule_id, rule in RULE_DEFINITIONS.items()
        if rule.category == RuleCategory.OPTIONAL
    }


def get_default_enabled_rules() -> Set[str]:
    """Get rule IDs that are enabled by default (mandatory + recommended)."""
    return get_mandatory_rules() | get_recommended_rules()


def get_active_rules(
    disabled_rules: Optional[List[str]] = None,
    enabled_rules: Optional[List[str]] = None,
) -> Set[str]:
    """
    Get the set of active rule IDs based on user configuration.

    Args:
        disabled_rules: Rules to disable (only non-mandatory allowed)
        enabled_rules: Optional rules to enable

    Returns:
        Set of active rule IDs
    """
    disabled_rules = set(disabled_rules or [])
    enabled_rules = set(enabled_rules or [])

    # Start with default enabled rules
    active = get_default_enabled_rules()

    # Add any enabled optional rules
    active |= enabled_rules

    # Remove disabled rules (but never mandatory ones)
    mandatory = get_mandatory_rules()
    for rule_id in disabled_rules:
        if rule_id not in mandatory:
            active.discard(rule_id)

    return active


def is_rule_disableable(rule_id: str) -> bool:
    """Check if a rule can be disabled by users."""
    rule = RULE_DEFINITIONS.get(rule_id)
    if not rule:
        return False
    return rule.category != RuleCategory.MANDATORY


def get_rule_info(rule_id: str) -> Optional[RuleDefinition]:
    """Get information about a rule."""
    return RULE_DEFINITIONS.get(rule_id)


def get_all_rules_by_category() -> Dict[str, List[RuleDefinition]]:
    """Get all rules organized by category for UI display."""
    result = {
        "mandatory": [],
        "recommended": [],
        "optional": [],
    }

    for rule in RULE_DEFINITIONS.values():
        result[rule.category.value].append(rule)

    # Sort each category by rule_id
    for category in result:
        result[category].sort(key=lambda r: r.rule_id)

    return result


def get_rules_for_api() -> List[Dict]:
    """Get all rules in API-friendly format for frontend."""
    result = []
    for rule in RULE_DEFINITIONS.values():
        result.append({
            "id": rule.rule_id,
            "name": rule.name,
            "category": rule.category.value,
            "description": rule.description,
            "severity": rule.severity,
            "canDisable": rule.category != RuleCategory.MANDATORY,
            "defaultEnabled": rule.category in (
                RuleCategory.MANDATORY,
                RuleCategory.RECOMMENDED,
            ),
        })
    return sorted(result, key=lambda r: r["id"])
