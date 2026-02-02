"""
String Presets - Text processing field configurations
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
    placeholder: str = "Enter text to process...",
    multiline: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Input text string field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='The text string to process',
        format="multiline" if multiline else None,
        group=FieldGroup.BASIC,
    )


def SEARCH_STRING(
    *,
    key: str = "search",
    required: bool = True,
    label: str = "Search For",
    label_key: str = "schema.field.search_string",
) -> Dict[str, Dict[str, Any]]:
    """Substring to search for."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Enter text to find...",
        description='The substring to search for in the input text',
        group=FieldGroup.BASIC,
    )


def REPLACE_STRING(
    *,
    key: str = "replace",
    required: bool = False,
    default: str = "",
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
        default=default,
        placeholder="Enter replacement text (empty to delete)",
        description='Text to replace matches with (leave empty to remove matches)',
        group=FieldGroup.BASIC,
    )


def STRING_DELIMITER(
    *,
    key: str = "delimiter",
    default: str = ",",
    label: str = "Delimiter",
    label_key: str = "schema.field.string_delimiter",
) -> Dict[str, Dict[str, Any]]:
    """Delimiter for string split operations."""
    common_delimiters = [
        {"value": ",", "label": ", (Comma)"},
        {"value": ";", "label": "; (Semicolon)"},
        {"value": "\t", "label": "Tab"},
        {"value": " ", "label": "Space"},
        {"value": "\n", "label": "Newline"},
        {"value": "|", "label": "| (Pipe)"},
        {"value": "-", "label": "- (Dash)"},
        {"value": "_", "label": "_ (Underscore)"},
    ]
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=common_delimiters,
        description='Character(s) to split the string on',
        ui={'allowCustomValue': True},
        group=FieldGroup.OPTIONS,
    )


def REGEX_PATTERN(
    *,
    key: str = "pattern",
    required: bool = True,
    label: str = "Regex Pattern",
    label_key: str = "schema.field.regex_pattern",
) -> Dict[str, Dict[str, Any]]:
    """Regular expression pattern."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=r"\d+|\w+@\w+\.\w+",
        description='Regular expression pattern (e.g., \\d+ for numbers, \\w+ for words)',
        group=FieldGroup.BASIC,
    )


def CASE_TYPE(
    *,
    key: str = "case_type",
    default: str = "lower",
    label: str = "Case Type",
    label_key: str = "schema.field.case_type",
) -> Dict[str, Dict[str, Any]]:
    """String case conversion type."""
    case_options = [
        {"value": "lower", "label": "lowercase"},
        {"value": "upper", "label": "UPPERCASE"},
        {"value": "title", "label": "Title Case"},
        {"value": "sentence", "label": "Sentence case"},
        {"value": "camel", "label": "camelCase"},
        {"value": "pascal", "label": "PascalCase"},
        {"value": "snake", "label": "snake_case"},
        {"value": "kebab", "label": "kebab-case"},
        {"value": "constant", "label": "CONSTANT_CASE"},
    ]
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=case_options,
        description='Target case format for conversion',
        group=FieldGroup.BASIC,
    )


def PADDING_SIDE(
    *,
    key: str = "side",
    default: str = "left",
    label: str = "Padding Side",
    label_key: str = "schema.field.padding_side",
) -> Dict[str, Dict[str, Any]]:
    """Which side to pad."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "left", "label": "Left (add to start)"},
            {"value": "right", "label": "Right (add to end)"},
            {"value": "both", "label": "Both (center)"},
        ],
        description='Which side of the string to add padding',
        group=FieldGroup.OPTIONS,
    )


def PADDING_CHAR(
    *,
    key: str = "pad_char",
    default: str = " ",
    label: str = "Padding Character",
    label_key: str = "schema.field.padding_char",
) -> Dict[str, Dict[str, Any]]:
    """Character to use for padding."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        placeholder=" ",
        options=[
            {"value": " ", "label": "Space"},
            {"value": "0", "label": "Zero (0)"},
            {"value": "-", "label": "Dash (-)"},
            {"value": "_", "label": "Underscore (_)"},
            {"value": ".", "label": "Dot (.)"},
        ],
        description='Character used for padding',
        ui={'allowCustomValue': True},
        group=FieldGroup.OPTIONS,
    )


def TARGET_LENGTH(
    *,
    key: str = "length",
    default: int = 10,
    label: str = "Target Length",
    label_key: str = "schema.field.target_length",
) -> Dict[str, Dict[str, Any]]:
    """Target string length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=1,
        max=10000,
        placeholder="10",
        description='Target length for the output string',
        group=FieldGroup.BASIC,
    )


def TRIM_TYPE(
    *,
    key: str = "trim_type",
    default: str = "both",
    label: str = "Trim",
    label_key: str = "schema.field.trim_type",
) -> Dict[str, Dict[str, Any]]:
    """Which whitespace to trim."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "both", "label": "Both sides"},
            {"value": "left", "label": "Left (start) only"},
            {"value": "right", "label": "Right (end) only"},
        ],
        description='Which whitespace to remove',
        group=FieldGroup.OPTIONS,
    )
