"""
Random Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def RANDOM_ARRAY(
    *,
    key: str = "array",
    required: bool = True,
    label: str = "Array",
    label_key: str = "schema.field.random_array",
) -> Dict[str, Dict[str, Any]]:
    """Array for random operations."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder='["apple", "banana", "cherry"]',
        description='Array for random operations',
        group=FieldGroup.BASIC,
    )


def RANDOM_COUNT(
    *,
    key: str = "count",
    default: int = 1,
    min_val: int = 1,
    label: str = "Count",
    label_key: str = "schema.field.random_count",
) -> Dict[str, Dict[str, Any]]:
    """Number of items to select."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        description='Number of items to select',
        group=FieldGroup.OPTIONS,
    )


def RANDOM_MIN(
    *,
    key: str = "min",
    default: int = 0,
    label: str = "Minimum",
    label_key: str = "schema.field.random_min",
) -> Dict[str, Dict[str, Any]]:
    """Minimum value."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        description='Minimum value (inclusive)',
        group=FieldGroup.BASIC,
    )


def RANDOM_MAX(
    *,
    key: str = "max",
    default: int = 100,
    label: str = "Maximum",
    label_key: str = "schema.field.random_max",
) -> Dict[str, Dict[str, Any]]:
    """Maximum value."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        description='Maximum value (inclusive)',
        group=FieldGroup.BASIC,
    )


def RANDOM_UNIQUE(
    *,
    key: str = "unique",
    default: bool = True,
    label: str = "Unique",
    label_key: str = "schema.field.random_unique",
) -> Dict[str, Dict[str, Any]]:
    """Select unique items."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Select unique items only',
        group=FieldGroup.OPTIONS,
    )
