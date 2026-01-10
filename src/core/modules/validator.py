"""
Unified Module Validator - Comprehensive validation for module registration

Validates:
- Metadata (M00x): Required fields, formats, connection rules
- Schema (S00x): params_schema, output_schema completeness
- Consistency (C00x): retryable/timeout/credentials logic
- Security (SEC00x): SSRF protection, path scope, behavior inference
- Advanced Security (SEC004-007): Hardcoded secrets, injection detection
- Runtime (RT00x): Instantiation validation

Environment:
    FLYTO_VALIDATION_MODE: dev|ci|release (default: ci)
"""

import ast
import inspect
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Pattern, Set, Tuple, Type

from .registry.validation_types import (
    ValidationMode,
    Severity,
    ValidationIssue,
    get_validation_mode,
    should_block,
)

logger = logging.getLogger(__name__)


# Valid data types for schemas
VALID_DATA_TYPES: Set[str] = {
    "any", "string", "number", "boolean", "object", "array",
    "json", "table", "file", "image", "binary", "html", "xml",
}

# Categories that imply network access
NETWORK_CATEGORIES: Set[str] = {
    "api", "http", "browser", "notification", "cloud", "database",
    "communication", "payment", "productivity",
}

# Categories that imply filesystem access
FILESYSTEM_CATEGORIES: Set[str] = {
    "file", "document", "image", "pdf", "excel", "word",
}

# Imports that imply network capability
NETWORK_IMPORTS: Set[str] = {
    "aiohttp", "httpx", "requests", "urllib", "socket", "websockets",
    "httplib", "urllib3", "grpc",
}

# Imports that imply shell capability
SHELL_IMPORTS: Set[str] = {
    "subprocess", "os.system", "os.popen", "shutil",
}

# Imports that imply filesystem write capability
FILESYSTEM_WRITE_IMPORTS: Set[str] = {
    "pathlib", "shutil", "tempfile",
}

# =============================================================================
# Advanced Security Patterns (SEC004-007)
# =============================================================================

# Patterns that look like hardcoded secrets
SECRET_PATTERNS: List[re.Pattern] = [
    re.compile(r'["\'](?:sk-|pk-|api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)["\']?\s*[=:]\s*["\'][a-zA-Z0-9_\-]{20,}["\']', re.IGNORECASE),
    re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
    re.compile(r'(?:api_key|apikey|api-key)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{16,}["\']', re.IGNORECASE),
    re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}', re.IGNORECASE),
    re.compile(r'(?:aws_access_key_id|aws_secret_access_key)\s*[=:]\s*["\'][A-Z0-9]{16,}["\']', re.IGNORECASE),
]

# SQL keywords for injection detection
SQL_KEYWORDS: Set[str] = {
    "SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "EXEC", "EXECUTE", "UNION", "WHERE", "FROM", "INTO",
}

# Dangerous functions that should be flagged
DANGEROUS_FUNCTIONS: Set[str] = {
    "eval", "exec", "__import__",
}

# Functions that are dangerous only in certain contexts
CONTEXT_DANGEROUS_FUNCTIONS: Dict[str, str] = {
    "compile": "built-in compile() - if this is re.compile(), it's safe",
}


@dataclass
class InferredCapabilities:
    """Capabilities inferred from source code analysis."""
    network: bool = False
    shell: bool = False
    filesystem_read: bool = False
    filesystem_write: bool = False
    imports: List[str] = field(default_factory=list)


class ModuleValidator:
    """
    Unified module validator.

    Rules:
        M001: module_id format
        M002: required metadata fields
        M005: connection rules presence

        S001: params_schema presence (warning, context-aware)
        S002: output_schema presence (error)
        S003: schema field types valid
        S004: output field descriptions
        S005: parameter default value type matches declared type
        S006: required parameters should be validated in validate_params()

        C001: retryable + max_retries consistency
        C002: timeout for network modules
        C003: requires_credentials should declare credential source
        C004: handles_sensitive_data should have permissions
        C005: network/file modules should have error handling (try-except)
        C006: modules should use logging instead of print()

        SEC001: network modules should declare SSRF protection
        SEC002: file modules should declare path scope
        SEC003: inferred capabilities should match declarations
        SEC004: hardcoded secrets detection (P0 - blocks in all modes)
        SEC005: command injection detection (shell=True + user input)
        SEC006: SQL injection detection (string formatting in SQL)
        SEC007: eval/exec usage detection

        I001: label_key without label fallback
        I002: description_key without description fallback

        RT001: module can be instantiated
        RT002: execute() should return dict with 'ok' field
        RT003: error returns should be consistent (dict, not raw string)
        RT004: module should be instantiable with empty params
    """

    def __init__(
        self,
        mode: Optional[ValidationMode] = None,
        disabled_rules: Optional[List[str]] = None,
    ):
        """
        Initialize validator.

        Args:
            mode: Validation mode (defaults to env FLYTO_VALIDATION_MODE)
            disabled_rules: List of rule IDs to skip (e.g., ['Q010', 'Q012'])
        """
        self.mode = mode or get_validation_mode()
        self.issues: List[ValidationIssue] = []
        # Legacy compatibility
        self.errors: List[str] = []
        self.warnings: List[str] = []

        # Load active rules based on disabled_rules
        from .registry.rule_config import get_active_rules, get_mandatory_rules
        self.active_rules = get_active_rules(disabled_rules=disabled_rules)
        self.mandatory_rules = get_mandatory_rules()

    def reset(self) -> None:
        """Reset state between validations."""
        self.issues = []
        self.errors = []
        self.warnings = []

    def validate(self, metadata: Dict[str, Any], module_class: Optional[Type] = None) -> bool:
        """
        Validate module metadata.

        Args:
            metadata: Module metadata dictionary
            module_class: Optional module class for behavior inference

        Returns:
            True if valid (no blocking issues), False otherwise
        """
        self.reset()
        module_id = metadata.get("module_id", "unknown")
        stability = metadata.get("stability", "stable")
        if hasattr(stability, 'value'):
            stability = stability.value

        # Run all validations
        self._validate_metadata(metadata)
        self._validate_schema(metadata)
        self._validate_consistency(metadata)
        self._validate_security(metadata)

        # Advanced validations - only if we have the module class
        if module_class:
            tags = metadata.get("tags", [])
            self._validate_behavior(metadata, module_class)
            self._validate_advanced_security(module_class, module_id, tags=tags)
            self._validate_runtime(module_class, module_id)
            self._validate_required_params_checked(metadata, module_class)
            self._validate_error_handling(metadata, module_class)
            self._validate_logging_usage(metadata, module_class)
            self._validate_output_format(module_class, module_id)
            self._validate_error_format(module_class, module_id)
            self._validate_instantiable(module_class, module_id)

        # Convert to legacy format and determine blocking
        has_blocking = False
        for issue in self.issues:
            msg = str(issue)
            if should_block(issue.severity, self.mode, stability):
                self.errors.append(msg)
                has_blocking = True
            elif issue.severity == Severity.WARNING:
                self.warnings.append(msg)

        return not has_blocking

    def _add_issue(
        self,
        rule_id: str,
        severity: Severity,
        message: str,
        field: Optional[str] = None,
        hint: Optional[str] = None,
        line: Optional[int] = None,
    ) -> None:
        """Add a validation issue (if rule is active)."""
        # Skip if rule is disabled (but never skip mandatory rules)
        if rule_id not in self.active_rules and rule_id not in self.mandatory_rules:
            return

        self.issues.append(ValidationIssue(
            rule_id=rule_id,
            severity=severity,
            message=message,
            field=field,
            hint=hint,
            line=line,
        ))

    # =========================================================================
    # Metadata Validation (M00x)
    # =========================================================================

    def _validate_metadata(self, metadata: Dict[str, Any]) -> None:
        """Validate basic metadata fields."""
        module_id = metadata.get("module_id")
        stability = metadata.get("stability", "stable")
        if hasattr(stability, 'value'):
            stability = stability.value

        # M001: module_id format
        if not module_id:
            self._add_issue("M001", Severity.ERROR, "Missing module_id")
        elif not re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$', module_id):
            # In RELEASE mode with stable modules, this is an error
            sev = Severity.ERROR if (self.mode == ValidationMode.RELEASE and stability == "stable") else Severity.WARNING
            self._add_issue(
                "M001", sev,
                f"module_id '{module_id}' should follow format: category.action",
                field="module_id",
                hint="Use lowercase with dots, e.g., 'browser.launch'"
            )

        # M002: Recommended fields
        for field_name in ["category", "version"]:
            if not metadata.get(field_name):
                self._add_issue(
                    "M002", Severity.WARNING,
                    f"Missing recommended field: {field_name}",
                    field=field_name
                )

        # M005: Connection rules
        if metadata.get("can_receive_from") is None:
            self._add_issue(
                "M005", Severity.ERROR,
                "Missing can_receive_from",
                field="can_receive_from",
                hint="Add can_receive_from=['start', ...] in @register_module"
            )
        if metadata.get("can_connect_to") is None:
            self._add_issue(
                "M005", Severity.ERROR,
                "Missing can_connect_to",
                field="can_connect_to",
                hint="Add can_connect_to=['*'] in @register_module"
            )

    # =========================================================================
    # Schema Validation (S00x)
    # =========================================================================

    def _validate_schema(self, metadata: Dict[str, Any]) -> None:
        """Validate params_schema and output_schema."""
        # S001: params_schema (context-aware warning)
        # Note: empty dict {} is valid (module has no parameters)
        params_schema = metadata.get("params_schema")
        if params_schema is None:
            category = metadata.get("category", "")
            # Only warn if not a flow/meta/utility module
            if category not in ('flow', 'meta', 'utility', 'internal'):
                self._add_issue(
                    "S001", Severity.WARNING,
                    "Missing params_schema",
                    field="params_schema",
                    hint="Define params_schema for UI parameter display"
                )
        elif params_schema is not None and not isinstance(params_schema, dict):
            self._add_issue(
                "S001", Severity.ERROR,
                f"params_schema must be dict, got {type(params_schema).__name__}",
                field="params_schema"
            )

        # S002: output_schema (required)
        output_schema = metadata.get("output_schema")
        if not output_schema:
            self._add_issue(
                "S002", Severity.ERROR,
                "Missing output_schema",
                field="output_schema",
                hint="Define output_schema for UI connection"
            )
        elif not isinstance(output_schema, dict):
            self._add_issue(
                "S002", Severity.ERROR,
                f"output_schema must be dict, got {type(output_schema).__name__}",
                field="output_schema"
            )
        elif len(output_schema) == 0:
            self._add_issue(
                "S002", Severity.ERROR,
                "output_schema is empty",
                field="output_schema"
            )
        else:
            # S003/S004: Validate each output field in properties
            # output_schema follows JSON Schema format: {"type": "object", "properties": {...}}
            properties = output_schema.get("properties", {})
            if not properties and output_schema.get("type") == "object":
                self._add_issue(
                    "S002", Severity.WARNING,
                    "output_schema has type 'object' but no properties defined",
                    field="output_schema.properties"
                )

            for field_name, field_def in properties.items():
                if not isinstance(field_def, dict):
                    continue

                # For fields that can be any type, description alone is acceptable
                field_type = field_def.get("type")
                has_description = bool(field_def.get("description"))

                if not field_type and not has_description:
                    self._add_issue(
                        "S003", Severity.ERROR,
                        f"Missing type in output_schema.properties.{field_name}",
                        field=f"output_schema.properties.{field_name}.type",
                        hint="Add type or description for 'any' type fields"
                    )
                elif field_type and isinstance(field_type, str) and field_type not in VALID_DATA_TYPES:
                    self._add_issue(
                        "S003", Severity.WARNING,
                        f"Unknown type '{field_type}'",
                        field=f"output_schema.properties.{field_name}.type",
                        hint=f"Valid: {', '.join(sorted(VALID_DATA_TYPES))}"
                    )

                if not has_description:
                    self._add_issue(
                        "S004", Severity.WARNING,
                        f"Missing description",
                        field=f"output_schema.properties.{field_name}.description"
                    )

        # I001: label_key without label fallback
        label_key = metadata.get("label_key") or metadata.get("ui_label_key")
        label = metadata.get("label") or metadata.get("ui_label")
        module_id = metadata.get("module_id", "")

        if label_key and (not label or label == module_id):
            self._add_issue(
                "I001", Severity.WARNING,
                "label_key defined but no label fallback",
                field="label",
                hint="Add label='English Label' for i18n fallback"
            )

        # I002: description_key without description fallback
        desc_key = metadata.get("description_key") or metadata.get("ui_description_key")
        desc = metadata.get("description") or metadata.get("ui_description")

        if desc_key and not desc:
            self._add_issue(
                "I002", Severity.WARNING,
                "description_key defined but no description fallback",
                field="description",
                hint="Add description='English text' for i18n fallback"
            )

        # S005: Parameter default value type consistency
        self._validate_param_defaults(metadata)

    def _validate_param_defaults(self, metadata: Dict[str, Any]) -> None:
        """S005: Parameter default values should match declared types."""
        params_schema = metadata.get('params_schema', {})
        if not isinstance(params_schema, dict):
            return

        properties = params_schema.get('properties', params_schema)
        for field_name, field_spec in properties.items():
            if not isinstance(field_spec, dict):
                continue

            field_type = field_spec.get('type')
            default = field_spec.get('default')

            if default is not None and field_type:
                # Type checking
                type_valid = True
                if field_type == 'string' and not isinstance(default, str):
                    type_valid = False
                elif field_type == 'number' and not isinstance(default, (int, float)):
                    type_valid = False
                elif field_type == 'integer' and not isinstance(default, int):
                    type_valid = False
                elif field_type == 'boolean' and not isinstance(default, bool):
                    type_valid = False
                elif field_type == 'array' and not isinstance(default, list):
                    type_valid = False
                elif field_type == 'object' and not isinstance(default, dict):
                    type_valid = False

                if not type_valid:
                    self._add_issue(
                        "S005", Severity.ERROR,
                        f"Parameter '{field_name}' default value type mismatch: "
                        f"expected {field_type}, got {type(default).__name__}",
                        field=field_name,
                        hint=f"Change default to match type '{field_type}'"
                    )

    def _validate_required_params_checked(
        self, metadata: Dict[str, Any], module_class: Type
    ) -> None:
        """S006: Required parameters should be validated in validate_params()."""
        params_schema = metadata.get('params_schema', {})
        if not isinstance(params_schema, dict):
            return

        required = params_schema.get('required', [])
        if not required:
            return

        # Check if validate_params exists and contains validation logic
        if not hasattr(module_class, 'validate_params'):
            return

        try:
            source = inspect.getsource(module_class.validate_params)
            # Check if required fields are validated
            for field_name in required:
                # Look for the field name in the source code
                if (field_name not in source and
                    f"'{field_name}'" not in source and
                    f'"{field_name}"' not in source):
                    self._add_issue(
                        "S006", Severity.WARNING,
                        f"Required parameter '{field_name}' may not be validated in validate_params()",
                        field=field_name,
                        hint=f"Add validation for '{field_name}' in validate_params()"
                    )
        except (TypeError, OSError):
            pass

    # =========================================================================
    # Consistency Validation (C00x)
    # =========================================================================

    def _validate_consistency(self, metadata: Dict[str, Any]) -> None:
        """Validate field consistency rules."""
        category = metadata.get("category", "")

        # C001: retryable + max_retries
        if metadata.get("retryable") is True:
            max_retries = metadata.get("max_retries", 0)
            if max_retries < 1:
                self._add_issue(
                    "C001", Severity.ERROR,
                    f"retryable=True but max_retries={max_retries}",
                    field="max_retries",
                    hint="Set max_retries >= 1 when retryable=True"
                )

        # C002: timeout for network modules
        if category in NETWORK_CATEGORIES:
            if metadata.get("timeout") is None:
                self._add_issue(
                    "C002", Severity.WARNING,
                    f"Network module ({category}) missing timeout",
                    field="timeout",
                    hint="Add timeout=60 (seconds)"
                )

        # C003: requires_credentials - should declare credential source, NOT param
        if metadata.get("requires_credentials") is True:
            # Check for credential_keys or required_secrets
            has_credential_source = (
                metadata.get("credential_keys") or
                metadata.get("required_secrets") or
                metadata.get("env_vars")
            )
            if not has_credential_source:
                self._add_issue(
                    "C003", Severity.WARNING,
                    "requires_credentials=True but no credential source declared",
                    field="credential_keys",
                    hint="Add credential_keys=['API_KEY_NAME'] or required_secrets"
                )

        # C004: handles_sensitive_data + permissions
        if metadata.get("handles_sensitive_data") is True:
            if not metadata.get("required_permissions"):
                self._add_issue(
                    "C004", Severity.WARNING,
                    "handles_sensitive_data=True but no required_permissions",
                    field="required_permissions"
                )

    def _validate_error_handling(
        self, metadata: Dict[str, Any], module_class: Type
    ) -> None:
        """C005: Network/file modules should have try-except blocks."""
        category = metadata.get('category', '')

        # Only check categories that need error handling
        error_prone_categories = {'api', 'http', 'browser', 'file', 'database', 'cloud'}
        if category not in error_prone_categories:
            return

        try:
            source = inspect.getsource(module_class)
            tree = ast.parse(source)

            has_try_except = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    has_try_except = True
                    break

            if not has_try_except:
                self._add_issue(
                    "C005", Severity.WARNING,
                    f"Module in '{category}' category should have error handling (try-except)",
                    hint="Add try-except to handle network/IO failures gracefully"
                )
        except (TypeError, OSError, SyntaxError):
            pass

    def _validate_logging_usage(
        self, metadata: Dict[str, Any], module_class: Type
    ) -> None:
        """C006: Modules should use logging for debugging."""
        try:
            source = inspect.getsource(module_class)

            # Check if logging is imported or used
            has_logging = (
                'import logging' in source or
                'from logging' in source or
                'logger.' in source or
                'logging.' in source
            )

            # Check for print() usage (should not exist)
            has_print = 'print(' in source

            if has_print and not has_logging:
                self._add_issue(
                    "C006", Severity.WARNING,
                    "Module uses print() but not logging",
                    hint="Import logging and use logger.debug/info/warning/error"
                )
        except (TypeError, OSError):
            pass

    # =========================================================================
    # Security Validation (SEC00x)
    # =========================================================================

    def _validate_security(self, metadata: Dict[str, Any]) -> None:
        """Validate security-related declarations."""
        category = metadata.get("category", "")
        params = metadata.get("params_schema", {})
        tags = metadata.get("tags", [])

        # Check for URL/host params
        has_url_param = any(
            "url" in k.lower() or "endpoint" in k.lower() or "host" in k.lower()
            for k in params.keys()
        )

        # SEC001: SSRF protection (FIXED: include browser)
        if category in NETWORK_CATEGORIES or has_url_param:
            has_ssrf_declaration = (
                "ssrf_protected" in tags or
                "ssrf_checked" in tags or
                metadata.get("ssrf_protection") is not None
            )
            if not has_ssrf_declaration:
                self._add_issue(
                    "SEC001", Severity.WARNING,
                    "Network module should declare SSRF protection status",
                    field="tags",
                    hint="Add 'ssrf_protected' tag or ssrf_protection field"
                )

        # SEC002: Path scope for file modules
        has_path_param = any("path" in k.lower() for k in params.keys())
        if category in FILESYSTEM_CATEGORIES or has_path_param:
            has_path_declaration = (
                "path_restricted" in tags or
                "workdir_only" in tags or
                metadata.get("path_scope") is not None
            )
            if not has_path_declaration:
                self._add_issue(
                    "SEC002", Severity.WARNING,
                    "File module should declare path scope",
                    field="tags",
                    hint="Add 'path_restricted' tag or path_scope field"
                )

    # =========================================================================
    # Behavior Inference (SEC003)
    # =========================================================================

    def _validate_behavior(self, metadata: Dict[str, Any], module_class: Type) -> None:
        """SEC003: Validate inferred behavior matches declarations."""
        stability = metadata.get("stability", "stable")
        if hasattr(stability, 'value'):
            stability = stability.value

        # Infer capabilities from source code
        inferred = self._infer_capabilities(module_class)

        tags = set(metadata.get("tags", []))
        category = metadata.get("category", "")

        # Check network capability
        if inferred.network:
            declared_network = (
                category in NETWORK_CATEGORIES or
                "network" in tags or
                "http" in tags or
                "api" in tags
            )
            if not declared_network:
                sev = Severity.ERROR if stability == "stable" else Severity.WARNING
                self._add_issue(
                    "SEC003", sev,
                    f"Code imports network libraries ({', '.join(inferred.imports[:3])}) but no network capability declared",
                    hint=f"Add category to {NETWORK_CATEGORIES} or add 'network' tag"
                )

        # Check shell capability
        if inferred.shell:
            declared_shell = "shell" in tags or "subprocess" in tags
            if not declared_shell:
                sev = Severity.ERROR if stability == "stable" else Severity.WARNING
                self._add_issue(
                    "SEC003", sev,
                    "Code uses subprocess/shell but no shell capability declared",
                    hint="Add 'shell' or 'subprocess' tag"
                )

        # Check filesystem write capability
        if inferred.filesystem_write:
            declared_fs = (
                category in FILESYSTEM_CATEGORIES or
                "filesystem_write" in tags or
                "file_write" in tags
            )
            if not declared_fs:
                sev = Severity.WARNING  # Less critical
                self._add_issue(
                    "SEC003", sev,
                    "Code may write to filesystem but no write capability declared",
                    hint="Add 'filesystem_write' tag or file category"
                )

    def _infer_capabilities(self, module_class: Type) -> InferredCapabilities:
        """Infer capabilities by analyzing source code imports and calls."""
        caps = InferredCapabilities()

        try:
            source = inspect.getsource(module_class)
            tree = ast.parse(source)
        except (TypeError, OSError, SyntaxError):
            return caps

        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_import(alias.name, caps)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._check_import(node.module, caps)

            # Check function calls for specific patterns
            elif isinstance(node, ast.Call):
                self._check_call(node, caps)

        return caps

    def _check_import(self, module_name: str, caps: InferredCapabilities) -> None:
        """Check if import implies a capability."""
        base_module = module_name.split('.')[0]

        if base_module in NETWORK_IMPORTS or module_name in NETWORK_IMPORTS:
            caps.network = True
            caps.imports.append(base_module)

        if base_module in SHELL_IMPORTS or module_name in SHELL_IMPORTS:
            caps.shell = True
            caps.imports.append(base_module)

        if base_module in FILESYSTEM_WRITE_IMPORTS:
            caps.filesystem_write = True
            caps.imports.append(base_module)

    def _check_call(self, node: ast.Call, caps: InferredCapabilities) -> None:
        """Check function calls for capability indicators."""
        # Check for os.system, os.popen, etc.
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "os" and node.func.attr in ("system", "popen", "spawn"):
                    caps.shell = True
                    caps.imports.append(f"os.{node.func.attr}")

        # Check for subprocess.run, subprocess.Popen, etc.
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "subprocess":
                    caps.shell = True
                    caps.imports.append("subprocess")

        # Check for open() with write mode
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            if len(node.args) >= 2:
                mode_arg = node.args[1]
                if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
                    if "w" in mode_arg.value or "a" in mode_arg.value:
                        caps.filesystem_write = True

    # =========================================================================
    # Advanced Security (SEC004-007)
    # =========================================================================

    def _validate_advanced_security(
        self,
        module_class: Type,
        module_id: str,
        tags: Optional[List[str]] = None
    ) -> None:
        """
        Advanced security checks on source code.

        SEC004: Hardcoded secrets
        SEC005: Command injection
        SEC006: SQL injection
        SEC007: eval/exec usage
        """
        try:
            source = inspect.getsource(module_class)
            tree = ast.parse(source)
        except (TypeError, OSError, SyntaxError):
            return

        # SEC004: Hardcoded secrets (P0 - always ERROR)
        self._check_hardcoded_secrets(source, module_id)

        # SEC006: Source-level SQL injection check (f-strings with SQL keywords)
        self._check_sql_patterns(source)

        # Allow eval for debugger/breakpoint/hitl modules
        tags = tags or []
        allow_eval = any(t in tags for t in ('breakpoint', 'debugger', 'hitl', 'repl'))

        # SEC005-007: AST-based checks
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                self._check_dangerous_calls(node, source, allow_eval=allow_eval)

    def _check_hardcoded_secrets(self, source: str, module_id: str) -> None:
        """SEC004: Detect hardcoded secrets in source code."""
        for pattern in SECRET_PATTERNS:
            matches = pattern.findall(source)
            if matches:
                # Mask the actual secret in the error message
                self._add_issue(
                    "SEC004", Severity.ERROR,
                    "Possible hardcoded secret detected",
                    hint="Use environment variables or credential_keys instead"
                )
                break  # One error is enough

    def _check_sql_patterns(self, source: str) -> None:
        """SEC006: Detect SQL injection patterns in f-strings."""
        # Pattern: f-string that looks like actual SQL query syntax
        # Must have SQL keyword followed by table-like structure
        # Matches: f"SELECT * FROM users WHERE id = {user_id}"
        # Matches: f"INSERT INTO table VALUES ({val})"
        # Does NOT match: f"create issue: {name}"
        fstring_sql_patterns = [
            # SELECT ... FROM ... {var}
            re.compile(r'f["\'].*SELECT\s+.+\s+FROM\s+\w+.*\{[^}]+\}', re.IGNORECASE),
            # INSERT INTO ... {var}
            re.compile(r'f["\'].*INSERT\s+INTO\s+\w+.*\{[^}]+\}', re.IGNORECASE),
            # UPDATE ... SET ... {var}
            re.compile(r'f["\'].*UPDATE\s+\w+\s+SET\s+.*\{[^}]+\}', re.IGNORECASE),
            # DELETE FROM ... {var}
            re.compile(r'f["\'].*DELETE\s+FROM\s+\w+.*\{[^}]+\}', re.IGNORECASE),
            # DROP TABLE/DATABASE {var}
            re.compile(r'f["\'].*DROP\s+(?:TABLE|DATABASE)\s+.*\{[^}]+\}', re.IGNORECASE),
        ]

        for pattern in fstring_sql_patterns:
            if pattern.search(source):
                self._add_issue(
                    "SEC006", Severity.ERROR,
                    "Potential SQL injection: f-string with SQL query and variable interpolation",
                    hint="Use parameterized queries (?, %s) instead of f-strings"
                )
                break

    def _check_dangerous_calls(
        self,
        node: ast.Call,
        source: str,
        allow_eval: bool = False
    ) -> None:
        """Check for dangerous function calls (SEC005-007)."""
        func_name = None

        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if not func_name:
            return

        # SEC007: eval/exec detection
        if func_name in DANGEROUS_FUNCTIONS:
            # Allow eval for debugger/breakpoint modules (they need it for conditions)
            if func_name == "eval" and allow_eval:
                self._add_issue(
                    "SEC007", Severity.WARNING,
                    f"eval() used (allowed for debugger modules)",
                    hint="Ensure eval context is restricted"
                )
            else:
                self._add_issue(
                    "SEC007", Severity.ERROR,
                    f"Dangerous function '{func_name}()' detected",
                    hint="Avoid eval/exec; use safer alternatives"
                )

        # SEC005: Command injection (subprocess with shell=True)
        if func_name in ("run", "Popen", "call", "check_output", "check_call"):
            for keyword in node.keywords:
                if keyword.arg == "shell":
                    if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        # Any shell=True with non-constant command is risky
                        if len(node.args) > 0:
                            cmd_arg = node.args[0]
                            # Flag if dynamic string OR if it's a variable (could be tainted)
                            if self._is_dynamic_string(cmd_arg) or isinstance(cmd_arg, ast.Name):
                                self._add_issue(
                                    "SEC005", Severity.ERROR,
                                    "Potential command injection: shell=True with dynamic/variable command",
                                    hint="Use shell=False and pass args as list, or use shlex.quote()"
                                )

        # SEC006: SQL injection (string formatting in execute)
        if func_name in ("execute", "executemany", "raw"):
            if len(node.args) > 0:
                sql_arg = node.args[0]
                if self._is_dynamic_string(sql_arg) or isinstance(sql_arg, ast.Name):
                    self._add_issue(
                        "SEC006", Severity.ERROR,
                        "Potential SQL injection: dynamic SQL string",
                        hint="Use parameterized queries (?, %s) instead of string formatting"
                    )

    def _is_dynamic_string(self, node: ast.AST) -> bool:
        """Check if a node represents a dynamically constructed string."""
        # f-string
        if isinstance(node, ast.JoinedStr):
            return True
        # String concatenation
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return True
        # % formatting
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            return True
        # .format() call
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
                return True
        return False

    # =========================================================================
    # Runtime Validation (RT001)
    # =========================================================================

    def _validate_runtime(self, module_class: Type, module_id: str) -> None:
        """
        RT001: Validate module structure (non-blocking).

        Checks class structure without instantiation:
        - execute() method exists and is async
        - validate_params() method exists
        """
        # Check class has execute method
        if not hasattr(module_class, 'execute'):
            self._add_issue(
                "RT001", Severity.ERROR,
                "Module class missing execute() method",
                hint="Add async def execute(self) -> Dict[str, Any]"
            )
            return

        # Check execute is async
        execute_method = getattr(module_class, 'execute', None)
        if execute_method and not inspect.iscoroutinefunction(execute_method):
            self._add_issue(
                "RT001", Severity.ERROR,
                "execute() must be async",
                hint="Change to: async def execute(self)"
            )

        # Check validate_params exists (warning only)
        if not hasattr(module_class, 'validate_params'):
            self._add_issue(
                "RT001", Severity.WARNING,
                "Module class missing validate_params() method",
                hint="Add def validate_params(self) -> None"
            )

    def _validate_output_format(self, module_class: Type, module_id: str) -> None:
        """RT002: Execute should return {'ok': bool, 'data'|'error': ...}."""
        try:
            execute_method = getattr(module_class, 'execute', None)
            if not execute_method:
                return

            source = inspect.getsource(execute_method)

            # Check return format
            has_ok = "'ok'" in source or '"ok"' in source
            has_data = "'data'" in source or '"data"' in source
            has_error = "'error'" in source or '"error"' in source

            if not has_ok:
                self._add_issue(
                    "RT002", Severity.WARNING,
                    "execute() should return dict with 'ok' field",
                    hint="Return {'ok': True, 'data': {...}} or {'ok': False, 'error': '...'}"
                )

            if not (has_data or has_error):
                self._add_issue(
                    "RT002", Severity.WARNING,
                    "execute() should return 'data' (success) or 'error' (failure)",
                    hint="Include 'data' for success cases, 'error' for failures"
                )
        except (TypeError, OSError, AttributeError):
            pass

    def _validate_error_format(self, module_class: Type, module_id: str) -> None:
        """RT003: Error returns should be consistent."""
        try:
            source = inspect.getsource(module_class)
            tree = ast.parse(source)

            # Check all return statements
            for node in ast.walk(tree):
                if isinstance(node, ast.Return) and node.value:
                    # Check if returning raw string error (should use dict)
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        self._add_issue(
                            "RT003", Severity.WARNING,
                            "Returning raw string instead of error dict",
                            line=node.lineno,
                            hint="Return {'ok': False, 'error': 'message'} instead"
                        )
        except (TypeError, OSError, SyntaxError):
            pass

    def _validate_instantiable(self, module_class: Type, module_id: str) -> None:
        """RT004: Module should be instantiable with empty params."""
        try:
            # Try to instantiate (without executing)
            instance = module_class({}, {})

            # Check if execute method exists
            if not hasattr(instance, 'execute'):
                self._add_issue(
                    "RT004", Severity.ERROR,
                    "Module instance missing execute() method",
                    hint="Ensure execute() is defined as async method"
                )

            # Check if validate_params method exists
            if not hasattr(instance, 'validate_params'):
                self._add_issue(
                    "RT004", Severity.WARNING,
                    "Module instance missing validate_params() method",
                    hint="Add validate_params() for input validation"
                )
        except Exception as e:
            self._add_issue(
                "RT004", Severity.WARNING,
                f"Module cannot be instantiated with empty params: {type(e).__name__}",
                hint="Ensure __init__ handles empty params gracefully"
            )


@dataclass
class ValidationResult:
    """Result of validating multiple modules."""
    total: int = 0
    passed: int = 0
    warned: int = 0
    failed: int = 0
    import_failures: List[str] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        # Import failures count as failures in CI/RELEASE
        return self.failed == 0 and len(self.import_failures) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "warned": self.warned,
            "failed": self.failed,
            "import_failures": self.import_failures,
            "is_valid": self.is_valid,
            "issues": self.issues,
        }


def validate_all_modules(mode: str = "ci") -> ValidationResult:
    """
    Validate all registered modules.

    Args:
        mode: Validation mode (dev/ci/release)

    Returns:
        ValidationResult with summary
    """
    # Auto-discover and import all modules
    try:
        from . import atomic  # noqa: F401
    except ImportError:
        pass

    try:
        from . import third_party  # noqa: F401
    except ImportError:
        pass

    try:
        from . import composite  # noqa: F401
    except ImportError:
        pass

    try:
        from . import integrations  # noqa: F401
    except ImportError:
        pass

    from .registry import ModuleRegistry

    validator = ModuleValidator(mode=ValidationMode(mode))
    all_metadata = ModuleRegistry.get_all_metadata()
    result = ValidationResult(total=len(all_metadata))

    for module_id, metadata in all_metadata.items():
        # Try to get the module class for behavior inference
        module_class = ModuleRegistry.get(module_id)

        is_valid = validator.validate(metadata, module_class)

        if validator.errors:
            result.failed += 1
            for error in validator.errors:
                result.issues.append({
                    "module_id": module_id,
                    "severity": "error",
                    "message": error,
                })
        elif validator.warnings:
            result.passed += 1
            result.warned += 1
            for warning in validator.warnings:
                result.issues.append({
                    "module_id": module_id,
                    "severity": "warning",
                    "message": warning,
                })
        else:
            result.passed += 1

    return result
