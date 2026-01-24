"""
Convert Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def CONVERT_VALUE(
    *,
    key: str = "value",
    required: bool = True,
    label: str = "Value",
    label_key: str = "schema.field.convert_value",
) -> Dict[str, Dict[str, Any]]:
    """Value to convert."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to convert',
        group=FieldGroup.BASIC,
    )


def CONVERT_DEFAULT(
    *,
    key: str = "default",
    default: Any = None,
    label: str = "Default",
    label_key: str = "schema.field.convert_default",
) -> Dict[str, Dict[str, Any]]:
    """Default value if conversion fails."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        default=default,
        description='Default value if conversion fails',
        group=FieldGroup.OPTIONS,
    )


def CONVERT_STRICT(
    *,
    key: str = "strict",
    default: bool = False,
    label: str = "Strict Mode",
    label_key: str = "schema.field.convert_strict",
) -> Dict[str, Dict[str, Any]]:
    """Strict conversion mode."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Use strict conversion rules',
        group=FieldGroup.OPTIONS,
    )


def CONVERT_PRETTY(
    *,
    key: str = "pretty",
    default: bool = False,
    label: str = "Pretty Print",
    label_key: str = "schema.field.convert_pretty",
) -> Dict[str, Dict[str, Any]]:
    """Format output with indentation."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Format output with indentation',
        group=FieldGroup.OPTIONS,
    )
