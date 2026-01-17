"""
Compare Presets - Value comparison field definitions
"""
from __future__ import annotations
from typing import Any, Dict
from ..builders import field
from ..constants import FieldGroup


def COMPARE_CURRENT_VALUE(
    *,
    key: str = "current_value",
    required: bool = True,
    placeholder: str = "42350.50",
    label: str = "Current Value",
    label_key: str = "schema.field.compare_current_value",
) -> Dict[str, Dict[str, Any]]:
    """Current/new value to compare."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='The current/new value to compare',
        group=FieldGroup.BASIC,
    )


def COMPARE_PREVIOUS_VALUE(
    *,
    key: str = "previous_value",
    required: bool = True,
    placeholder: str = "41000.00",
    label: str = "Previous Value",
    label_key: str = "schema.field.compare_previous_value",
) -> Dict[str, Dict[str, Any]]:
    """Previous/old value to compare against."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='The previous/old value to compare against',
        group=FieldGroup.BASIC,
    )


def COMPARE_MODE(
    *,
    key: str = "mode",
    required: bool = False,
    default: str = "percent",
    label: str = "Detection Mode",
    label_key: str = "schema.field.compare_mode",
) -> Dict[str, Dict[str, Any]]:
    """How to measure change."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        required=required,
        options=[
            {'value': 'percent', 'label': 'Percentage Change'},
            {'value': 'absolute', 'label': 'Absolute Change'},
            {'value': 'any', 'label': 'Any Change'},
        ],
        description='How to measure change',
        group=FieldGroup.OPTIONS,
    )


def COMPARE_THRESHOLD(
    *,
    key: str = "threshold",
    required: bool = False,
    default: float = 5,
    placeholder: str = "5",
    label: str = "Threshold",
    label_key: str = "schema.field.compare_threshold",
) -> Dict[str, Dict[str, Any]]:
    """Minimum change to trigger alert."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        placeholder=placeholder,
        required=required,
        min=0,
        description='Minimum change to trigger (5 = 5% or 5 units)',
        group=FieldGroup.OPTIONS,
    )


def COMPARE_DIRECTION(
    *,
    key: str = "direction",
    required: bool = False,
    default: str = "both",
    label: str = "Direction",
    label_key: str = "schema.field.compare_direction",
) -> Dict[str, Dict[str, Any]]:
    """Which direction of change to detect."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        required=required,
        options=[
            {'value': 'both', 'label': 'Both (Up or Down)'},
            {'value': 'up', 'label': 'Up Only (Increase)'},
            {'value': 'down', 'label': 'Down Only (Decrease)'},
        ],
        description='Which direction of change to detect',
        group=FieldGroup.OPTIONS,
    )
