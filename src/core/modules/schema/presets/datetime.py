"""
DateTime Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def DATETIME_STRING(
    *,
    key: str = "datetime_string",
    required: bool = True,
    label: str = "DateTime String",
    label_key: str = "schema.field.datetime_string",
) -> Dict[str, Dict[str, Any]]:
    """DateTime string to parse."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='DateTime string to parse',
        group=FieldGroup.BASIC,
    )


def DATETIME_INPUT(
    *,
    key: str = "datetime",
    default: str = "now",
    label: str = "DateTime",
    label_key: str = "schema.field.datetime_input",
) -> Dict[str, Dict[str, Any]]:
    """DateTime input (ISO format or 'now')."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='DateTime (ISO format or "now")',
        group=FieldGroup.BASIC,
    )


def DATETIME_FORMAT(
    *,
    key: str = "format",
    default: str = None,
    label: str = "Format",
    label_key: str = "schema.field.datetime_format",
) -> Dict[str, Dict[str, Any]]:
    """strftime/strptime format string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Format string (strftime/strptime)',
        group=FieldGroup.OPTIONS,
    )


def TIME_DAYS(
    *,
    key: str = "days",
    default: int = 0,
    label: str = "Days",
    label_key: str = "schema.field.time_days",
) -> Dict[str, Dict[str, Any]]:
    """Days to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Days to add/subtract',
        group=FieldGroup.OPTIONS,
    )


def TIME_HOURS(
    *,
    key: str = "hours",
    default: int = 0,
    label: str = "Hours",
    label_key: str = "schema.field.time_hours",
) -> Dict[str, Dict[str, Any]]:
    """Hours to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Hours to add/subtract',
        group=FieldGroup.OPTIONS,
    )


def TIME_MINUTES(
    *,
    key: str = "minutes",
    default: int = 0,
    label: str = "Minutes",
    label_key: str = "schema.field.time_minutes",
) -> Dict[str, Dict[str, Any]]:
    """Minutes to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Minutes to add/subtract',
        group=FieldGroup.OPTIONS,
    )


def TIME_SECONDS(
    *,
    key: str = "seconds",
    default: int = 0,
    label: str = "Seconds",
    label_key: str = "schema.field.time_seconds",
) -> Dict[str, Dict[str, Any]]:
    """Seconds to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Seconds to add/subtract',
        group=FieldGroup.OPTIONS,
    )
