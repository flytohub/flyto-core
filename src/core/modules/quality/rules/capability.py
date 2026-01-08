"""
Capability Rules (CORE-CAP-*)

Rules for permission and capability validation.
"""
from typing import Any, Dict, List, Optional, Set
import ast

from ..types import Severity, ValidationIssue
from ..constants import VALID_PERMISSIONS, SIDE_EFFECT_CAPABILITIES, IMPORT_CAPABILITY_MAP
from . import register_rule
from .base import MetadataRule, ASTRule


@register_rule
class SideEffectRequiresPermissions(MetadataRule):
    """CORE-CAP-001: Modules with side-effect capabilities must declare required_permissions."""

    rule_id = "CORE-CAP-001"
    description = "Side-effect modules need required_permissions"
    category = "capability"
    default_severity = Severity.ERROR
    stability_aware = True

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        permissions = metadata.get("required_permissions", [])
        stability = metadata.get("stability", "stable")

        severity = cls.get_severity(stability)

        # Check if module has side-effect indicators
        has_side_effects = False

        # Check category-based side effects
        category = module_id.split(".")[0] if "." in module_id else ""
        side_effect_categories = {"browser", "file", "database", "api", "shell", "email", "sms"}
        if category in side_effect_categories:
            has_side_effects = True

        # Check metadata flags
        if metadata.get("requires_credentials"):
            has_side_effects = True

        # If has side effects but no permissions
        if has_side_effects and not permissions:
            issues.append(cls.create_issue(
                message="Module appears to have side effects but required_permissions is empty",
                module_id=module_id,
                severity=severity,
                suggestion="Add appropriate permissions from the whitelist",
            ))

        return issues


@register_rule
class PermissionsInWhitelist(MetadataRule):
    """CORE-CAP-002: All declared permissions must be from the valid permissions whitelist."""

    rule_id = "CORE-CAP-002"
    description = "Permissions must be valid"
    category = "capability"
    default_severity = Severity.ERROR
    stability_aware = False

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        permissions = metadata.get("required_permissions", [])

        if not isinstance(permissions, list):
            issues.append(cls.create_issue(
                message=f"required_permissions must be a list, got {type(permissions).__name__}",
                module_id=module_id,
            ))
            return issues

        invalid = []
        for perm in permissions:
            if perm not in VALID_PERMISSIONS:
                invalid.append(perm)

        if invalid:
            issues.append(cls.create_issue(
                message=f"Invalid permissions: {', '.join(invalid)}",
                module_id=module_id,
                suggestion=f"Use valid permissions from whitelist",
            ))

        return issues


@register_rule
class ObservedCapabilityMismatch(ASTRule):
    """CORE-CAP-003: Capabilities detected from imports should be in required_permissions."""

    rule_id = "CORE-CAP-003"
    description = "Detected capabilities must match declared permissions"
    category = "capability"
    default_severity = Severity.ERROR
    stability_aware = True

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        if source_code is None:
            return issues

        stability = metadata.get("stability", "stable")
        severity = cls.get_severity(stability)

        declared_permissions = set(metadata.get("required_permissions", []))

        # Detect capabilities from imports
        detected = cls._detect_capabilities(source_code, ast_tree)

        # Check for undeclared capabilities
        for cap, source in detected.items():
            # Map capability to expected permission
            expected_permission = cls._capability_to_permission(cap)
            if expected_permission and expected_permission not in declared_permissions:
                issues.append(cls.create_issue(
                    message=f"Code imports '{source}' (capability: {cap}) but '{expected_permission}' not in required_permissions",
                    module_id=module_id,
                    severity=severity,
                    suggestion=f"Add '{expected_permission}' to required_permissions",
                ))

        return issues

    @classmethod
    def _detect_capabilities(cls, source_code: str, ast_tree: Optional[ast.AST]) -> Dict[str, str]:
        """Detect capabilities from source code imports."""
        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return {}

        detected = {}

        for node in ast.walk(ast_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    if module_name in IMPORT_CAPABILITY_MAP:
                        cap = IMPORT_CAPABILITY_MAP[module_name]
                        detected[cap] = module_name

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split(".")[0]
                    if module_name in IMPORT_CAPABILITY_MAP:
                        cap = IMPORT_CAPABILITY_MAP[module_name]
                        detected[cap] = module_name

        return detected

    @classmethod
    def _capability_to_permission(cls, capability: str) -> Optional[str]:
        """Map a detected capability to expected permission."""
        # Direct mapping for most
        if capability in VALID_PERMISSIONS:
            return capability

        # Special mappings
        mapping = {
            "shell.execute": "shell.execute",
            "ai.openai": "ai.api",
            "ai.anthropic": "ai.api",
            "ai.google": "ai.api",
            "browser.automation": "browser.read",
        }
        return mapping.get(capability)


@register_rule
class CredentialsWithApiParams(MetadataRule):
    """CORE-CAP-004: If module has api_key/token params, requires_credentials should be True."""

    rule_id = "CORE-CAP-004"
    description = "API key params imply requires_credentials"
    category = "capability"
    default_severity = Severity.WARN
    stability_aware = False

    CREDENTIAL_PARAMS = {"api_key", "apikey", "api-key", "token", "access_token", "secret_key"}

    @classmethod
    def validate(
        cls,
        module_id: str,
        metadata: Dict[str, Any],
        source_code: Optional[str] = None,
        ast_tree: Optional[ast.AST] = None,
    ) -> List[ValidationIssue]:
        issues = []

        requires_credentials = metadata.get("requires_credentials", False)

        params_schema = metadata.get("params_schema", {})
        if not isinstance(params_schema, dict):
            return issues

        properties = params_schema.get("properties", {})
        if not isinstance(properties, dict):
            return issues

        # Check for credential-like params
        credential_params = []
        for param_name in properties.keys():
            param_lower = param_name.lower().replace("_", "").replace("-", "")
            for cred in cls.CREDENTIAL_PARAMS:
                if cred.replace("_", "").replace("-", "") in param_lower:
                    credential_params.append(param_name)
                    break

        if credential_params and not requires_credentials:
            issues.append(cls.create_issue(
                message=f"Module has credential-like params ({', '.join(credential_params)}) but requires_credentials=False",
                module_id=module_id,
                suggestion="Set requires_credentials=True",
            ))

        return issues
