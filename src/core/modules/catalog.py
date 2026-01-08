"""
Module Catalog - Public view sanitization and catalog utilities.

This module provides functions to:
1. Scrub sensitive data from module metadata before exposing to frontend
2. Generate public catalog views for API responses
3. Filter modules based on visibility rules

Design Principles:
- Security first: Never expose secrets, credentials, or internal config
- Single responsibility: Only handles catalog data transformation
- Atomic: Independent of specific module implementations
"""
import re
import logging
from typing import Any, Dict, List, Optional, Set
from copy import deepcopy

logger = logging.getLogger(__name__)


# =============================================================================
# Sensitive Field Detection
# =============================================================================

# Fields that should never appear in public catalog
FORBIDDEN_FIELDS: Set[str] = {
    "internal_config",
    "connector_details",
    "default_credentials",
    "private_key",
    "secret_key",
    "internal_notes",
}

# Schema field keys that indicate sensitive data
SENSITIVE_KEY_PATTERNS: List[str] = [
    r"password",
    r"secret",
    r"token",
    r"api[_-]?key",
    r"auth[_-]?token",
    r"access[_-]?key",
    r"private[_-]?key",
    r"credential",
]

# Schema field formats that indicate sensitive data
SENSITIVE_FORMATS: Set[str] = {
    "password",
    "secret",
    "credential",
}

# Placeholder for redacted values
REDACTED_VALUE = "***REDACTED***"


def _is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates sensitive data."""
    key_lower = key.lower()
    for pattern in SENSITIVE_KEY_PATTERNS:
        if re.search(pattern, key_lower):
            return True
    return False


def _is_sensitive_field(field_def: Dict[str, Any]) -> bool:
    """Check if a schema field definition indicates sensitive data."""
    # Check format
    field_format = field_def.get("format", "")
    if field_format in SENSITIVE_FORMATS:
        return True

    # Check type hints
    field_type = field_def.get("type", "")
    if field_type == "password":
        return True

    return False


# =============================================================================
# Schema Scrubbing
# =============================================================================

def scrub_schema_defaults(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove sensitive default values from params_schema.

    Rules:
    - If field name matches SENSITIVE_KEY_PATTERNS: remove default
    - If field format is in SENSITIVE_FORMATS: remove default
    - If field has format=password: remove default

    Args:
        schema: params_schema dictionary

    Returns:
        Scrubbed schema with sensitive defaults removed
    """
    if not schema:
        return schema

    result = {}
    for key, field_def in schema.items():
        if not isinstance(field_def, dict):
            result[key] = field_def
            continue

        field_copy = field_def.copy()

        # Check if this field is sensitive
        is_sensitive = _is_sensitive_key(key) or _is_sensitive_field(field_def)

        if is_sensitive:
            # Remove default value
            if "default" in field_copy:
                del field_copy["default"]
            # Remove any example values
            if "example" in field_copy:
                del field_copy["example"]

        result[key] = field_copy

    return result


def _scrub_dict_values(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively scrub sensitive values in a dictionary.

    Args:
        d: Dictionary to scrub

    Returns:
        Dictionary with sensitive values redacted
    """
    result = {}
    for key, value in d.items():
        if _is_sensitive_key(key):
            # Redact sensitive key values
            if isinstance(value, str):
                result[key] = REDACTED_VALUE
            elif isinstance(value, dict):
                # Keep structure but redact nested sensitive strings
                result[key] = _scrub_dict_values(value)
            else:
                result[key] = value
        elif isinstance(value, dict):
            # Recurse into nested dicts
            result[key] = _scrub_dict_values(value)
        elif isinstance(value, list):
            # Handle list of dicts
            result[key] = [
                _scrub_dict_values(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def scrub_examples(examples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Redact sensitive values in example params.

    Args:
        examples: List of example dictionaries

    Returns:
        Examples with sensitive values redacted
    """
    if not examples:
        return examples

    result = []
    for example in examples:
        example_copy = deepcopy(example)

        if "params" in example_copy and isinstance(example_copy["params"], dict):
            example_copy["params"] = _scrub_dict_values(example_copy["params"])

        result.append(example_copy)

    return result


# =============================================================================
# Metadata Scrubbing
# =============================================================================

def scrub_catalog_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrub sensitive data from module metadata for public API response.

    This is the main entry point for catalog sanitization.

    Security measures:
    1. Remove forbidden fields entirely
    2. Remove sensitive defaults from params_schema
    3. Redact sensitive values in examples
    4. Remove internal configuration

    Args:
        metadata: Raw module metadata from registry

    Returns:
        Sanitized metadata safe for public API response
    """
    if not metadata:
        return metadata

    result = deepcopy(metadata)

    # 1. Remove forbidden fields
    for field in FORBIDDEN_FIELDS:
        result.pop(field, None)

    # 2. Scrub params_schema defaults
    if "params_schema" in result:
        result["params_schema"] = scrub_schema_defaults(result["params_schema"])

    # 3. Scrub examples
    if "examples" in result:
        result["examples"] = scrub_examples(result["examples"])

    # 4. Remove any additional internal fields
    # (fields starting with underscore)
    keys_to_remove = [k for k in result.keys() if k.startswith("_")]
    for key in keys_to_remove:
        del result[key]

    return result


def scrub_all_metadata(
    all_metadata: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Scrub all module metadata in a catalog.

    Args:
        all_metadata: Dict of module_id -> metadata

    Returns:
        Dict of module_id -> scrubbed metadata
    """
    return {
        module_id: scrub_catalog_metadata(metadata)
        for module_id, metadata in all_metadata.items()
    }


# =============================================================================
# Public Catalog View
# =============================================================================

# Fields to include in public view (allowlist approach)
PUBLIC_FIELDS: Set[str] = {
    "module_id",
    "version",
    "category",
    "subcategory",
    "tags",
    "label",
    "label_key",
    "description",
    "description_key",
    "icon",
    "color",
    "input_types",
    "output_types",
    "can_connect_to",
    "can_receive_from",
    "params_schema",
    "output_schema",
    "examples",
    "author",
    "license",
    "stability",
    "timeout_ms",
    "retryable",
    "max_retries",
    "capabilities",  # Expose capabilities so UI can show warnings
}


def get_public_catalog_view(
    metadata: Dict[str, Any],
    include_schema: bool = True
) -> Dict[str, Any]:
    """
    Get public view of module metadata.

    Uses allowlist approach - only includes explicitly allowed fields.

    Args:
        metadata: Raw or scrubbed metadata
        include_schema: Whether to include params_schema and output_schema

    Returns:
        Public view with only allowed fields
    """
    # First scrub sensitive data
    scrubbed = scrub_catalog_metadata(metadata)

    # Then filter to only public fields
    result = {}
    for field in PUBLIC_FIELDS:
        if field in scrubbed:
            # Skip schema if not requested
            if not include_schema and field in ("params_schema", "output_schema"):
                continue
            result[field] = scrubbed[field]

    return result


def get_public_catalog(
    all_metadata: Dict[str, Dict[str, Any]],
    include_schema: bool = True
) -> Dict[str, Dict[str, Any]]:
    """
    Get public catalog with all metadata scrubbed and filtered.

    Args:
        all_metadata: Dict of module_id -> metadata
        include_schema: Whether to include params_schema and output_schema

    Returns:
        Public catalog safe for API response
    """
    return {
        module_id: get_public_catalog_view(metadata, include_schema)
        for module_id, metadata in all_metadata.items()
    }
