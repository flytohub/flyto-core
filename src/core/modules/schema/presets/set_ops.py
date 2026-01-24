"""
Set Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def SET_ARRAYS(
    *,
    key: str = "arrays",
    required: bool = True,
    label: str = "Arrays",
    label_key: str = "schema.field.set_arrays",
) -> Dict[str, Dict[str, Any]]:
    """Arrays for set operation."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="[[1, 2], [2, 3]]",
        description='Arrays for set operation',
        group=FieldGroup.BASIC,
    )


def SET_SOURCE(
    *,
    key: str = "source",
    required: bool = True,
    label: str = "Source Array",
    label_key: str = "schema.field.set_source",
) -> Dict[str, Dict[str, Any]]:
    """Source array."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="[1, 2, 3, 4, 5]",
        description='Source array',
        group=FieldGroup.BASIC,
    )


def SET_EXCLUDE(
    *,
    key: str = "exclude",
    required: bool = True,
    label: str = "Exclude Arrays",
    label_key: str = "schema.field.set_exclude",
) -> Dict[str, Dict[str, Any]]:
    """Arrays of elements to exclude."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="[[2, 4], [5]]",
        description='Elements to exclude',
        group=FieldGroup.BASIC,
    )


def SET_ARRAY(
    *,
    key: str = "array",
    required: bool = True,
    label: str = "Array",
    label_key: str = "schema.field.set_array",
) -> Dict[str, Dict[str, Any]]:
    """Array input."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="[1, 2, 2, 3, 3]",
        description='Array input',
        group=FieldGroup.BASIC,
    )


def PRESERVE_ORDER(
    *,
    key: str = "preserve_order",
    default: bool = True,
    label: str = "Preserve Order",
    label_key: str = "schema.field.preserve_order",
) -> Dict[str, Dict[str, Any]]:
    """Keep first occurrence order."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Keep first occurrence order',
        group=FieldGroup.OPTIONS,
    )
