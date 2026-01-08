"""
Security Rules (CORE-SEC-*)

Rules for security validation: secrets, sensitive data, credentials.
"""
import re
from typing import Any, Dict, List, Optional
import ast

from ..types import Severity, ValidationIssue
from ..constants import SECRET_PATTERNS, SENSITIVE_PARAM_PATTERNS
from . import register_rule
from .base import MetadataRule, ASTRule


@register_rule
class NoSecretsInCode(ASTRule):
    """CORE-SEC-001: No API keys or secrets in defaults or examples."""

    rule_id = "CORE-SEC-001"
    description = "No secrets in code"
    category = "security"
    default_severity = Severity.BLOCKER
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

        # Check source code for secret patterns
        if source_code:
            for pattern, secret_type in SECRET_PATTERNS:
                matches = re.findall(pattern, source_code)
                if matches:
                    issues.append(cls.create_issue(
                        message=f"Potential {secret_type} found in source code",
                        module_id=module_id,
                        suggestion="Remove hardcoded secrets. Use environment variables or context.",
                    ))
                    break  # One issue per module is enough

        # Check metadata for secrets in defaults
        params_schema = metadata.get("params_schema", {})
        if isinstance(params_schema, dict):
            properties = params_schema.get("properties", {})
            if isinstance(properties, dict):
                for prop_name, prop_def in properties.items():
                    if isinstance(prop_def, dict):
                        default = prop_def.get("default")
                        if default and isinstance(default, str):
                            for pattern, secret_type in SECRET_PATTERNS:
                                if re.search(pattern, default):
                                    issues.append(cls.create_issue(
                                        message=f"Potential {secret_type} in default value for '{prop_name}'",
                                        module_id=module_id,
                                        suggestion="Remove secret from default value",
                                    ))
                                    break

        # Check examples
        examples = metadata.get("examples", [])
        if isinstance(examples, list):
            for idx, example in enumerate(examples):
                if isinstance(example, dict):
                    params = example.get("params", {})
                    if isinstance(params, dict):
                        for param_name, param_value in params.items():
                            if isinstance(param_value, str):
                                for pattern, secret_type in SECRET_PATTERNS:
                                    if re.search(pattern, param_value):
                                        issues.append(cls.create_issue(
                                            message=f"Potential {secret_type} in example[{idx}].params.{param_name}",
                                            module_id=module_id,
                                            suggestion="Use placeholder like 'YOUR_API_KEY' in examples",
                                        ))
                                        break

        return issues


@register_rule
class SensitiveDataFlag(MetadataRule):
    """CORE-SEC-002: Modules with sensitive params should set handles_sensitive_data=True."""

    rule_id = "CORE-SEC-002"
    description = "Sensitive params require handles_sensitive_data flag"
    category = "security"
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

        handles_sensitive = metadata.get("handles_sensitive_data", False)
        stability = metadata.get("stability", "stable")
        severity = cls.get_severity(stability)

        params_schema = metadata.get("params_schema", {})
        if not isinstance(params_schema, dict):
            return issues

        properties = params_schema.get("properties", {})
        if not isinstance(properties, dict):
            return issues

        # Find sensitive params
        sensitive_params = []
        for param_name in properties.keys():
            param_lower = param_name.lower()
            for pattern in SENSITIVE_PARAM_PATTERNS:
                if pattern in param_lower:
                    sensitive_params.append(param_name)
                    break

        if sensitive_params and not handles_sensitive:
            issues.append(cls.create_issue(
                message=f"Module has sensitive params ({', '.join(sensitive_params[:3])}) but handles_sensitive_data=False",
                module_id=module_id,
                severity=severity,
                suggestion="Set handles_sensitive_data=True",
            ))

        return issues


@register_rule
class RequiresCredentialsConsistency(MetadataRule):
    """CORE-SEC-003: If module has API key params, requires_credentials should be True."""

    rule_id = "CORE-SEC-003"
    description = "API modules should require credentials"
    category = "security"
    default_severity = Severity.WARN
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

        requires_credentials = metadata.get("requires_credentials", False)
        permissions = metadata.get("required_permissions", [])

        # Check if module needs external API access
        api_permissions = {"ai.api", "ai.openai", "ai.anthropic", "ai.google", "network.access"}
        has_api_access = any(p in api_permissions for p in permissions)

        if has_api_access and not requires_credentials:
            issues.append(cls.create_issue(
                message="Module has API access permissions but requires_credentials=False",
                module_id=module_id,
                suggestion="Consider setting requires_credentials=True",
            ))

        return issues


@register_rule
class NoDirectEnvAccess(ASTRule):
    """CORE-SEC-004: Do not use os.getenv() directly. Use context.secrets."""

    rule_id = "CORE-SEC-004"
    description = "No direct os.getenv() - use context"
    category = "security"
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

        if source_code is None:
            return issues

        if ast_tree is None:
            try:
                ast_tree = ast.parse(source_code)
            except SyntaxError:
                return issues

        for node in ast.walk(ast_tree):
            # Check for os.getenv()
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and
                        node.func.value.id == "os" and
                        node.func.attr == "getenv"):
                        issues.append(cls.create_issue(
                            message="Direct os.getenv() call detected",
                            module_id=module_id,
                            line=node.lineno,
                            suggestion="Use context.get_secret() or params instead of os.getenv()",
                        ))

            # Check for os.environ access
            if isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Attribute):
                    if (isinstance(node.value.value, ast.Name) and
                        node.value.value.id == "os" and
                        node.value.attr == "environ"):
                        issues.append(cls.create_issue(
                            message="Direct os.environ access detected",
                            module_id=module_id,
                            line=node.lineno,
                            suggestion="Use context.get_secret() or params instead of os.environ",
                        ))

        return issues
