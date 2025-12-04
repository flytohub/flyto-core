"""
Module Metadata Validator

Enforces strict standards for @register_module to ensure:
- Consistent naming conventions
- UI compatibility
- Professional quality
- Predictable behavior
"""

import re
from typing import Dict, List, Any, Optional
import json


class ValidationError(Exception):
    """Module validation failed"""
    pass


class ModuleValidator:
    """Validates module metadata against specification"""

    # Allowed categories (from MODULE_SPECIFICATION.md)
    ALLOWED_CATEGORIES = {
        # Atomic modules
        'atomic', 'browser', 'data', 'utility', 'file', 'string', 'array', 'math',
        # Third-party integrations
        'ai', 'notification', 'database', 'cloud', 'productivity', 'api', 'developer',
        # Legacy/special
        'element', 'flow',  # Existing modules
        # Future
        'workflow',
    }

    # Standard input/output types
    STANDARD_TYPES = {
        # Data types
        'text', 'json', 'html', 'xml', 'csv', 'binary',
        # Resource types
        'url', 'file_path', 'image', 'screenshot',
        # Browser types
        'browser_instance', 'page_instance', 'element',
        # API types
        'api_response', 'webhook',
        # Special
        'any',
    }

    # Valid Lucide icon names (subset - add more as needed)
    VALID_ICONS = {
        'Braces', 'Code', 'FileText', 'Database', 'Cloud', 'Mail',
        'MessageSquare', 'Bell', 'Search', 'Filter', 'Calculator',
        'Globe', 'Link', 'Image', 'File', 'Folder', 'Hash',
        'Type', 'AlignLeft', 'List', 'Grid', 'Layers', 'Box',
        'Package', 'Archive', 'Download', 'Upload', 'Send', 'Zap',
        'Play', 'Pause', 'Square', 'Circle', 'Triangle', 'Star',
        'Heart', 'Flag', 'Bookmark', 'Tag', 'Clock', 'Calendar',
        'User', 'Users', 'Shield', 'Lock', 'Key', 'Settings',
        'Tool', 'Wrench', 'Sliders', 'ToggleLeft', 'Check', 'X',
        'Plus', 'Minus', 'ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown',
        'ChevronRight', 'ChevronLeft', 'ChevronsRight', 'ChevronsLeft',
        'Eye', 'EyeOff', 'Camera', 'Video', 'Mic', 'Volume2',
        'Cpu', 'HardDrive', 'Server', 'Terminal', 'Code2', 'GitBranch',
        'Smartphone', 'Laptop', 'Monitor', 'Tablet', 'Watch',
    }

    def __init__(self, strict_mode: bool = True):
        """
        Initialize validator

        Args:
            strict_mode: If True, raise errors. If False, return warnings.
        """
        self.strict_mode = strict_mode
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self, metadata: Dict[str, Any]) -> bool:
        """
        Validate module metadata

        Args:
            metadata: Module metadata dictionary

        Returns:
            True if valid, False otherwise

        Raises:
            ValidationError: If strict_mode and validation fails
        """
        self.errors = []
        self.warnings = []

        # Run all validation checks
        self._validate_module_id(metadata)
        self._validate_version(metadata)
        self._validate_category(metadata)
        self._validate_labels(metadata)
        self._validate_visual(metadata)
        self._validate_types(metadata)
        self._validate_schemas(metadata)
        self._validate_i18n(metadata)
        self._validate_examples(metadata)
        self._validate_metadata_fields(metadata)
        # Phase 2 validations
        self._validate_execution_settings(metadata)
        self._validate_security_settings(metadata)

        # Check results
        if self.errors:
            error_msg = '\n'.join([f'  - {e}' for e in self.errors])
            if self.strict_mode:
                raise ValidationError(f'Module validation failed:\n{error_msg}')
            return False

        return True

    def _validate_module_id(self, metadata: Dict[str, Any]):
        """Validate module_id format: accepts 2-part or 3-part naming"""
        module_id = metadata.get('module_id', '')

        # Check format: lowercase with dots (2 or 3 parts)
        if not re.match(r'^[a-z]+(\.[a-z0-9_]+)+$', module_id):
            self.errors.append(
                f"module_id '{module_id}' must be lowercase with dots (e.g., 'file.read' or 'data.json.parse')"
            )

        # Check parts (allow 2 or 3 parts)
        parts = module_id.split('.')
        if len(parts) < 2 or len(parts) > 3:
            self.errors.append(
                f"module_id '{module_id}' must have 2 or 3 parts (e.g., 'file.read' or 'data.json.parse')"
            )

        # Note: Don't enforce that category matches first part - allows core.browser.find with category='browser'

    def _validate_version(self, metadata: Dict[str, Any]):
        """Validate semantic version"""
        version = metadata.get('version', '')

        if not re.match(r'^\d+\.\d+\.\d+$', version):
            self.errors.append(
                f"version '{version}' must be semantic version (e.g., '1.0.0')"
            )

    def _validate_category(self, metadata: Dict[str, Any]):
        """Validate category is in allowed list"""
        category = metadata.get('category', '')

        if category not in self.ALLOWED_CATEGORIES:
            self.errors.append(
                f"category '{category}' not allowed. Must be one of: {', '.join(sorted(self.ALLOWED_CATEGORIES))}"
            )

        # Subcategory must be lowercase (if provided)
        subcategory = metadata.get('subcategory', '')
        if subcategory and not subcategory.islower():
            self.errors.append(
                f"subcategory '{subcategory}' must be lowercase"
            )

    def _validate_labels(self, metadata: Dict[str, Any]):
        """Validate label format and content"""
        label = metadata.get('label', '')

        # Must be Title Case
        if not self._is_title_case(label):
            self.errors.append(
                f"label '{label}' must be Title Case (e.g., 'Send Slack Message')"
            )

        # Must be 2-5 words
        word_count = len(label.split())
        if word_count < 2 or word_count > 5:
            self.warnings.append(
                f"label '{label}' should be 2-5 words (currently {word_count})"
            )

        # Description length
        description = metadata.get('description', '')
        if len(description) < 10:
            self.errors.append(
                f"description must be at least 10 characters (currently {len(description)})"
            )
        elif len(description) > 200:
            self.warnings.append(
                f"description should be under 200 characters (currently {len(description)})"
            )

    def _validate_visual(self, metadata: Dict[str, Any]):
        """Validate icon and color"""
        # Icon must be valid Lucide icon
        icon = metadata.get('icon', '')
        if icon not in self.VALID_ICONS:
            self.warnings.append(
                f"icon '{icon}' may not be a valid Lucide icon. "
                f"Recommended: {', '.join(list(self.VALID_ICONS)[:10])}..."
            )

        # Color must be valid hex
        color = metadata.get('color', '')
        if not re.match(r'^#[0-9A-F]{6}$', color, re.IGNORECASE):
            self.errors.append(
                f"color '{color}' must be valid hex color (e.g., '#FF5733')"
            )

    def _validate_types(self, metadata: Dict[str, Any]):
        """Validate input/output types"""
        input_types = metadata.get('input_types', [])
        output_types = metadata.get('output_types', [])

        # Check if types are valid
        for t in input_types:
            if t not in self.STANDARD_TYPES:
                self.warnings.append(
                    f"input_type '{t}' is not a standard type. "
                    f"Consider using: {', '.join(list(self.STANDARD_TYPES)[:10])}..."
                )

        for t in output_types:
            if t not in self.STANDARD_TYPES:
                self.warnings.append(
                    f"output_type '{t}' is not a standard type."
                )

    def _validate_schemas(self, metadata: Dict[str, Any]):
        """Validate params and output schemas"""
        params_schema = metadata.get('params_schema', {})
        output_schema = metadata.get('output_schema', {})

        # Check params_schema structure
        if not isinstance(params_schema, dict):
            self.errors.append("params_schema must be a dictionary")
        else:
            for param_name, param_def in params_schema.items():
                if not isinstance(param_def, dict):
                    self.errors.append(
                        f"params_schema['{param_name}'] must be a dictionary"
                    )
                else:
                    # Check required fields
                    if 'type' not in param_def:
                        self.errors.append(
                            f"params_schema['{param_name}'] missing 'type' field"
                        )
                    if 'label' not in param_def:
                        self.warnings.append(
                            f"params_schema['{param_name}'] missing 'label' field"
                        )

        # Check output_schema structure
        if not isinstance(output_schema, dict):
            self.errors.append("output_schema must be a dictionary")

    def _validate_i18n(self, metadata: Dict[str, Any]):
        """Validate i18n keys - flexible to match module_id structure"""
        label_key = metadata.get('label_key', '')
        description_key = metadata.get('description_key', '')
        module_id = metadata.get('module_id', '')

        # Build expected key from module_id
        # Examples: file.read → modules.file.read.label
        #           data.json.parse → modules.data.json.parse.label
        #           core.browser.find → modules.browser.find.label
        if module_id:
            # For core.* modules, remove 'core.' prefix
            expected_id = module_id.replace('core.', '')
            expected_label_key = f"modules.{expected_id}.label"
            expected_desc_key = f"modules.{expected_id}.description"

            if label_key and label_key != expected_label_key:
                self.errors.append(
                    f"label_key '{label_key}' should match module_id: '{expected_label_key}'"
                )

            if description_key and description_key != expected_desc_key:
                self.errors.append(
                    f"description_key '{description_key}' should match module_id: '{expected_desc_key}'"
                )

    def _validate_examples(self, metadata: Dict[str, Any]):
        """Validate examples"""
        examples = metadata.get('examples', [])

        if not examples or len(examples) < 1:
            self.errors.append("Must have at least 1 example")

        for i, example in enumerate(examples):
            if not isinstance(example, dict):
                self.errors.append(f"examples[{i}] must be a dictionary")
            else:
                if 'title' not in example:
                    self.warnings.append(f"examples[{i}] missing 'title'")
                if 'params' not in example:
                    self.errors.append(f"examples[{i}] missing 'params'")

    def _validate_metadata_fields(self, metadata: Dict[str, Any]):
        """Validate required metadata fields"""
        required_fields = [
            'module_id', 'version', 'category', 'subcategory', 'tags',
            'label', 'label_key', 'description', 'description_key',
            'icon', 'color', 'params_schema', 'output_schema',
            'examples', 'author', 'license'
        ]

        for field in required_fields:
            if field not in metadata:
                self.errors.append(f"Required field '{field}' is missing")

        # Tags must have 2-5 items
        tags = metadata.get('tags', [])
        if len(tags) < 2:
            self.warnings.append("Should have at least 2 tags")
        elif len(tags) > 5:
            self.warnings.append("Should have at most 5 tags")

    def _validate_execution_settings(self, metadata: Dict[str, Any]):
        """Validate Phase 2 execution settings"""
        timeout = metadata.get('timeout')
        retryable = metadata.get('retryable', False)
        max_retries = metadata.get('max_retries', 3)
        concurrent_safe = metadata.get('concurrent_safe', True)

        # Timeout validation
        if timeout is not None:
            if not isinstance(timeout, int) or timeout <= 0:
                self.errors.append(
                    f"timeout must be a positive integer (got: {timeout})"
                )
            elif timeout > 3600:  # 1 hour max
                self.warnings.append(
                    f"timeout is very long ({timeout}s). Consider if this is intentional."
                )

        # Retry validation
        if retryable:
            if not isinstance(max_retries, int) or max_retries < 1:
                self.errors.append(
                    f"max_retries must be a positive integer when retryable=True (got: {max_retries})"
                )
            elif max_retries > 10:
                self.warnings.append(
                    f"max_retries is very high ({max_retries}). This might cause long delays."
                )

        # Concurrent safety check
        if not isinstance(concurrent_safe, bool):
            self.errors.append(
                f"concurrent_safe must be boolean (got: {type(concurrent_safe).__name__})"
            )

        # Logic warnings
        if not concurrent_safe and retryable:
            self.warnings.append(
                "Module is not concurrent_safe but is retryable. "
                "Consider if retries might cause resource conflicts."
            )

    def _validate_security_settings(self, metadata: Dict[str, Any]):
        """Validate Phase 2 security settings"""
        requires_credentials = metadata.get('requires_credentials', False)
        handles_sensitive_data = metadata.get('handles_sensitive_data', False)
        required_permissions = metadata.get('required_permissions', [])

        # Type checks
        if not isinstance(requires_credentials, bool):
            self.errors.append(
                f"requires_credentials must be boolean (got: {type(requires_credentials).__name__})"
            )

        if not isinstance(handles_sensitive_data, bool):
            self.errors.append(
                f"handles_sensitive_data must be boolean (got: {type(handles_sensitive_data).__name__})"
            )

        if not isinstance(required_permissions, list):
            self.errors.append(
                f"required_permissions must be a list (got: {type(required_permissions).__name__})"
            )
        else:
            # Validate permission format
            for perm in required_permissions:
                if not isinstance(perm, str):
                    self.errors.append(
                        f"Permission must be string (got: {type(perm).__name__})"
                    )
                elif not re.match(r'^[a-z]+(\.[a-z]+)*$', perm):
                    self.warnings.append(
                        f"Permission '{perm}' should follow format: 'resource.action' (e.g., 'file.write')"
                    )

        # Logic checks
        if handles_sensitive_data and not requires_credentials:
            self.warnings.append(
                "Module handles sensitive data but doesn't require credentials. "
                "Consider if authentication is needed."
            )

    def _is_title_case(self, text: str) -> bool:
        """Check if text is in Title Case"""
        if not text:
            return False

        # Allow common exceptions
        exceptions = {'a', 'an', 'the', 'and', 'or', 'but', 'for', 'to', 'in', 'on', 'at'}

        # Remove special characters like parentheses for checking
        # e.g., "Google Search (API)" → ["Google", "Search", "(API)"]
        words = text.split()
        for i, word in enumerate(words):
            # Skip punctuation-only words like "(API)" or words starting with (
            if word.startswith('('):
                continue

            # First word must be capitalized
            if i == 0:
                if not word[0].isupper():
                    return False
            else:
                # Other words: either capitalized or an exception
                if word.lower() not in exceptions and not word[0].isupper():
                    return False

        return True

    def get_report(self) -> str:
        """Get validation report as string"""
        report = []

        if self.errors:
            report.append("Errors:")
            for error in self.errors:
                report.append(f"  ✗ {error}")

        if self.warnings:
            report.append("Warnings:")
            for warning in self.warnings:
                report.append(f"  ⚠ {warning}")

        if not self.errors and not self.warnings:
            report.append("✓ All checks passed")

        return '\n'.join(report)


def validate_module(metadata: Dict[str, Any], strict: bool = True) -> bool:
    """
    Convenience function to validate module metadata

    Args:
        metadata: Module metadata dictionary
        strict: If True, raise on errors. If False, return warnings.

    Returns:
        True if valid, False otherwise
    """
    validator = ModuleValidator(strict_mode=strict)
    return validator.validate(metadata)
