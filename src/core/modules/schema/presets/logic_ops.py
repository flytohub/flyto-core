"""
Logic Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def LOGIC_VALUES(
    *,
    key: str = "values",
    required: bool = True,
    label: str = "Values",
    label_key: str = "schema.field.logic_values",
) -> Dict[str, Dict[str, Any]]:
    """Boolean values for logic operation."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="[true, true, false]",
        description='Boolean values for operation',
        group=FieldGroup.BASIC,
    )


def LOGIC_VALUE(
    *,
    key: str = "value",
    required: bool = True,
    label: str = "Value",
    label_key: str = "schema.field.logic_value",
) -> Dict[str, Dict[str, Any]]:
    """Boolean value."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        required=required,
        default=False,
        description='Boolean value',
        group=FieldGroup.BASIC,
    )


def COMPARE_VALUE_A(
    *,
    key: str = "a",
    required: bool = True,
    label: str = "Value A",
    label_key: str = "schema.field.compare_value_a",
) -> Dict[str, Dict[str, Any]]:
    """First value to compare."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="First value",
        description='First value to compare',
        group=FieldGroup.BASIC,
    )


def COMPARE_VALUE_B(
    *,
    key: str = "b",
    required: bool = True,
    label: str = "Value B",
    label_key: str = "schema.field.compare_value_b",
) -> Dict[str, Dict[str, Any]]:
    """Second value to compare."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Second value",
        description='Second value to compare',
        group=FieldGroup.BASIC,
    )


def STRICT_COMPARE(
    *,
    key: str = "strict",
    default: bool = False,
    label: str = "Strict",
    label_key: str = "schema.field.strict_compare",
) -> Dict[str, Dict[str, Any]]:
    """Require same type (no coercion)."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Require same type',
        group=FieldGroup.OPTIONS,
    )
