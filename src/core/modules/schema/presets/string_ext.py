"""
String Extension Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def STRING_PAD_LENGTH(
    *,
    key: str = "length",
    required: bool = True,
    label: str = "Length",
    label_key: str = "schema.field.string_pad_length",
) -> Dict[str, Dict[str, Any]]:
    """Target length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=1,
        placeholder="10",
        description='Target length',
        group=FieldGroup.BASIC,
    )


def STRING_PAD_CHAR(
    *,
    key: str = "pad_char",
    default: str = " ",
    label: str = "Pad Character",
    label_key: str = "schema.field.string_pad_char",
) -> Dict[str, Dict[str, Any]]:
    """Character to pad with."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Character to pad with',
        group=FieldGroup.OPTIONS,
    
        placeholder=' ',
)


def STRING_PAD_POSITION(
    *,
    key: str = "position",
    default: str = "end",
    label: str = "Position",
    label_key: str = "schema.field.string_pad_position",
) -> Dict[str, Dict[str, Any]]:
    """Padding position."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Where to add padding',
        group=FieldGroup.OPTIONS,
        options=[
            {'value': 'start', 'label': 'Start (left)'},
            {'value': 'end', 'label': 'End (right)'},
            {'value': 'both', 'label': 'Both (center)'},
        ]
    )


def STRING_MAX_LENGTH(
    *,
    key: str = "length",
    required: bool = True,
    label: str = "Max Length",
    label_key: str = "schema.field.string_max_length",
) -> Dict[str, Dict[str, Any]]:
    """Maximum length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=1,
        placeholder="100",
        description='Maximum length',
        group=FieldGroup.BASIC,
    )


def STRING_SUFFIX(
    *,
    key: str = "suffix",
    default: str = "...",
    label: str = "Suffix",
    label_key: str = "schema.field.string_suffix",
) -> Dict[str, Dict[str, Any]]:
    """Text to append if truncated."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Text to append if truncated',
        group=FieldGroup.OPTIONS,
    
        placeholder='-suffix',
)


def STRING_SEPARATOR(
    *,
    key: str = "separator",
    default: str = "-",
    label: str = "Separator",
    label_key: str = "schema.field.string_separator",
) -> Dict[str, Dict[str, Any]]:
    """Word separator."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Word separator',
        group=FieldGroup.OPTIONS,
    
        placeholder=',',
)


def STRING_TEMPLATE(
    *,
    key: str = "template",
    required: bool = True,
    label: str = "Template",
    label_key: str = "schema.field.string_template",
) -> Dict[str, Dict[str, Any]]:
    """Template string."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Hello, {{name}}!",
        description='Template string with {{variable}} placeholders',
        group=FieldGroup.BASIC,
    )


def STRING_VARIABLES(
    *,
    key: str = "variables",
    required: bool = True,
    label: str = "Variables",
    label_key: str = "schema.field.string_variables",
) -> Dict[str, Dict[str, Any]]:
    """Template variables."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        placeholder='{"name": "John", "count": 5}',
        description='Variables to substitute',
        group=FieldGroup.BASIC,
    )
