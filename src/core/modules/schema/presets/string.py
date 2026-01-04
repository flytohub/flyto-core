"""
String Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def INPUT_TEXT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.input_text",
    placeholder: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Input text string field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='The string to process',
        group=FieldGroup.BASIC,
    )


def SEARCH_STRING(
    *,
    key: str = "search",
    required: bool = True,
    label: str = "Search",
    label_key: str = "schema.field.search_string",
) -> Dict[str, Dict[str, Any]]:
    """Substring to search for."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='The substring to search for',
        group=FieldGroup.BASIC,
    )


def REPLACE_STRING(
    *,
    key: str = "replace",
    required: bool = True,
    label: str = "Replace With",
    label_key: str = "schema.field.replace_string",
) -> Dict[str, Dict[str, Any]]:
    """Replacement string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='The replacement string',
        group=FieldGroup.BASIC,
    )


def STRING_DELIMITER(
    *,
    key: str = "delimiter",
    default: str = " ",
    label: str = "Delimiter",
    label_key: str = "schema.field.string_delimiter",
) -> Dict[str, Dict[str, Any]]:
    """Delimiter for string split operations."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='The delimiter to split on',
        group=FieldGroup.OPTIONS,
    )
