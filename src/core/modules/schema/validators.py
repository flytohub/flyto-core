"""
Schema Validators - Centralized validation patterns and rules

Usage:
    from core.modules.schema import validators

    validation = validators.URL_HTTP
    validation = validators.regex(r"^\\d+$", message="Must be digits only")
"""
from __future__ import annotations
from typing import Any, Dict, Optional


# ============================================
# Regex Patterns
# ============================================

URL_HTTP_PATTERN = r"^https?://.+"
URL_ANY_PATTERN = r"^(https?|file|data)://.+"
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
NON_EMPTY_PATTERN = r"^.+$"
ALPHANUMERIC_PATTERN = r"^[a-zA-Z0-9]+$"
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SELECTOR_PATTERN = r"^(#|\.|\[|//|xpath=|css=|text=).+"
JSON_PATH_PATTERN = r"^\$(\..+|\[.+\])+"


# ============================================
# Validation Rule Builders
# ============================================

def regex(
    pattern: str,
    *,
    message: Optional[str] = None,
    message_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a regex validation rule.

    Args:
        pattern: Regex pattern string
        message: Error message if validation fails
        message_key: i18n key for error message

    Returns:
        Validation dict for use in field schema
    """
    v: Dict[str, Any] = {"pattern": pattern}
    if message_key:
        v["message_key"] = message_key
    if message:
        v["message"] = message
    return v


def range(
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    *,
    message: Optional[str] = None,
    message_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a numeric range validation rule.

    Args:
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        message: Error message if validation fails
        message_key: i18n key for error message

    Returns:
        Validation dict for use in field schema
    """
    v: Dict[str, Any] = {}
    if min_val is not None:
        v["min"] = min_val
    if max_val is not None:
        v["max"] = max_val
    if message_key:
        v["message_key"] = message_key
    if message:
        v["message"] = message
    return v


def length(
    min_len: Optional[int] = None,
    max_len: Optional[int] = None,
    *,
    message: Optional[str] = None,
    message_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a string/array length validation rule.

    Args:
        min_len: Minimum length
        max_len: Maximum length
        message: Error message if validation fails
        message_key: i18n key for error message

    Returns:
        Validation dict for use in field schema
    """
    v: Dict[str, Any] = {}
    if min_len is not None:
        v["min_length"] = min_len
    if max_len is not None:
        v["max_length"] = max_len
    if message_key:
        v["message_key"] = message_key
    if message:
        v["message"] = message
    return v


def combine(*rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combine multiple validation rules into one.

    Args:
        *rules: Validation dicts to combine

    Returns:
        Combined validation dict
    """
    result: Dict[str, Any] = {}
    for rule in rules:
        result.update(rule)
    return result


# ============================================
# Pre-built Validation Rules
# ============================================

# URL validations
URL_HTTP = regex(
    URL_HTTP_PATTERN,
    message_key="schema.validation.url_http",
    message="Must start with http:// or https://",
)

URL_ANY = regex(
    URL_ANY_PATTERN,
    message_key="schema.validation.url_any",
    message="Must be a valid URL (http, https, file, or data)",
)

# Text validations
NON_EMPTY = regex(
    NON_EMPTY_PATTERN,
    message_key="schema.validation.non_empty",
    message="Cannot be empty",
)

ALPHANUMERIC = regex(
    ALPHANUMERIC_PATTERN,
    message_key="schema.validation.alphanumeric",
    message="Only letters and numbers allowed",
)

SLUG = regex(
    SLUG_PATTERN,
    message_key="schema.validation.slug",
    message="Must be lowercase with hyphens only (e.g., my-slug-name)",
)

EMAIL = regex(
    EMAIL_PATTERN,
    message_key="schema.validation.email",
    message="Must be a valid email address",
)

# Selector validation
SELECTOR = regex(
    SELECTOR_PATTERN,
    message_key="schema.validation.selector",
    message="Must be a valid selector (#id, .class, xpath=, css=, text=)",
)

# JSON Path validation
JSON_PATH = regex(
    JSON_PATH_PATTERN,
    message_key="schema.validation.json_path",
    message="Must be a valid JSON path (e.g., $.data.items[0])",
)

# Common numeric ranges
PERCENTAGE = range(0, 100, message="Must be between 0 and 100")
POSITIVE = range(0, None, message="Must be positive")
PORT = range(1, 65535, message="Must be a valid port (1-65535)")
OPACITY = range(0, 1, message="Must be between 0 and 1")

# Timeout ranges (in milliseconds)
TIMEOUT_MS = range(0, 300000, message="Timeout must be 0-300000ms")
TIMEOUT_S = range(0, 300, message="Timeout must be 0-300 seconds")
