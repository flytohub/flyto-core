"""
Regex Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def REGEX_TEXT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.regex_text",
) -> Dict[str, Dict[str, Any]]:
    """Text to process."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Hello World 123",
        description='Text to process',
        group=FieldGroup.BASIC,
    )


def REGEX_PATTERN(
    *,
    key: str = "pattern",
    required: bool = True,
    label: str = "Pattern",
    label_key: str = "schema.field.regex_pattern",
) -> Dict[str, Dict[str, Any]]:
    """Regular expression pattern."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="\\d+",
        description='Regular expression pattern',
        group=FieldGroup.BASIC,
    )


def REGEX_REPLACEMENT(
    *,
    key: str = "replacement",
    required: bool = True,
    label: str = "Replacement",
    label_key: str = "schema.field.regex_replacement",
) -> Dict[str, Dict[str, Any]]:
    """Replacement text."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="[REPLACED]",
        description='Replacement text (supports backreferences)',
        group=FieldGroup.BASIC,
    )


def REGEX_IGNORE_CASE(
    *,
    key: str = "ignore_case",
    default: bool = False,
    label: str = "Ignore Case",
    label_key: str = "schema.field.regex_ignore_case",
) -> Dict[str, Dict[str, Any]]:
    """Case-insensitive matching."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Case-insensitive matching',
        group=FieldGroup.OPTIONS,
    )


def REGEX_MULTILINE(
    *,
    key: str = "multiline",
    default: bool = False,
    label: str = "Multiline",
    label_key: str = "schema.field.regex_multiline",
) -> Dict[str, Dict[str, Any]]:
    """Multiline mode."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='^ and $ match line boundaries',
        group=FieldGroup.OPTIONS,
    )


def REGEX_MAX_COUNT(
    *,
    key: str = "count",
    default: int = 0,
    label: str = "Max Count",
    label_key: str = "schema.field.regex_max_count",
) -> Dict[str, Dict[str, Any]]:
    """Maximum number of matches."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=0,
        description='Maximum matches (0 = unlimited)',
        group=FieldGroup.OPTIONS,
    )
