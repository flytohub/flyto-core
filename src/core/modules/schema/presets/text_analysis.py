"""
Text Analysis Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def ANALYSIS_TEXT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.analysis_text",
) -> Dict[str, Dict[str, Any]]:
    """Text to analyze."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Enter text to analyze",
        description='Text to analyze',
        group=FieldGroup.BASIC,
    )


def UNIQUE_ONLY(
    *,
    key: str = "unique",
    default: bool = True,
    label: str = "Unique Only",
    label_key: str = "schema.field.unique_only",
) -> Dict[str, Dict[str, Any]]:
    """Return only unique results."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Return only unique results',
        group=FieldGroup.OPTIONS,
    )


def CASE_SENSITIVE(
    *,
    key: str = "case_sensitive",
    default: bool = True,
    label: str = "Case Sensitive",
    label_key: str = "schema.field.case_sensitive",
) -> Dict[str, Dict[str, Any]]:
    """Case sensitive matching."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Case sensitive matching',
        group=FieldGroup.OPTIONS,
    )
