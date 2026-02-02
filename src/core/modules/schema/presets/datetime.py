"""
DateTime Presets - Date and time field configurations
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


# Common datetime format options with user-friendly labels
DATETIME_FORMAT_OPTIONS = [
    {"value": "%Y-%m-%d", "label": "2024-01-30 (ISO Date)"},
    {"value": "%Y-%m-%d %H:%M:%S", "label": "2024-01-30 14:30:00 (ISO DateTime)"},
    {"value": "%Y/%m/%d", "label": "2024/01/30"},
    {"value": "%d/%m/%Y", "label": "30/01/2024 (DD/MM/YYYY)"},
    {"value": "%m/%d/%Y", "label": "01/30/2024 (MM/DD/YYYY)"},
    {"value": "%Y年%m月%d日", "label": "2024年01月30日 (中文)"},
    {"value": "%B %d, %Y", "label": "January 30, 2024 (English)"},
    {"value": "%d %b %Y", "label": "30 Jan 2024"},
    {"value": "%H:%M:%S", "label": "14:30:00 (Time only)"},
    {"value": "%H:%M", "label": "14:30 (Hour:Minute)"},
    {"value": "%I:%M %p", "label": "02:30 PM (12-hour)"},
    {"value": "%Y%m%d", "label": "20240130 (Compact)"},
    {"value": "%Y-%m-%dT%H:%M:%SZ", "label": "2024-01-30T14:30:00Z (ISO 8601)"},
    {"value": "%a, %d %b %Y %H:%M:%S", "label": "Tue, 30 Jan 2024 14:30:00 (RFC 2822)"},
]


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
        placeholder="2024-01-30T14:30:00Z",
        description='DateTime string to parse (ISO 8601 format recommended)',
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
        placeholder="now or 2024-01-30T14:30:00",
        description='Enter "now" for current time, or ISO 8601 format (e.g., 2024-01-30T14:30:00)',
        group=FieldGroup.BASIC,
    )


def DATETIME_FORMAT(
    *,
    key: str = "format",
    default: str = "%Y-%m-%d %H:%M:%S",
    label: str = "Output Format",
    label_key: str = "schema.field.datetime_format",
    allow_custom: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """DateTime format selector with common presets."""
    field_def = field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        options=DATETIME_FORMAT_OPTIONS,
        description='Select a format or enter custom strftime pattern',
        group=FieldGroup.OPTIONS,
    )
    if allow_custom:
        # Allow custom input in addition to dropdown
        field_def[key]['ui'] = {'allowCustomValue': True}
    return field_def


def DATETIME_PARSE_FORMAT(
    *,
    key: str = "parse_format",
    default: str = None,
    label: str = "Input Format",
    label_key: str = "schema.field.datetime_parse_format",
) -> Dict[str, Dict[str, Any]]:
    """DateTime parse format (for parsing non-standard input)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        options=DATETIME_FORMAT_OPTIONS,
        placeholder="Auto-detect or select format",
        description='Format of input string (leave empty for auto-detect ISO 8601)',
        ui={'allowCustomValue': True},
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
        min=-3650,  # ~10 years
        max=3650,
        placeholder="0",
        description='Number of days to add (positive) or subtract (negative)',
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
        min=-8760,  # ~1 year
        max=8760,
        placeholder="0",
        description='Number of hours to add (positive) or subtract (negative)',
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
        min=-525600,  # 1 year
        max=525600,
        placeholder="0",
        description='Number of minutes to add (positive) or subtract (negative)',
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
        placeholder="0",
        description='Number of seconds to add (positive) or subtract (negative)',
        group=FieldGroup.OPTIONS,
    )


def TIMEZONE(
    *,
    key: str = "timezone",
    default: str = "UTC",
    label: str = "Timezone",
    label_key: str = "schema.field.timezone",
) -> Dict[str, Dict[str, Any]]:
    """Timezone selector."""
    common_timezones = [
        {"value": "UTC", "label": "UTC (Coordinated Universal Time)"},
        {"value": "Asia/Taipei", "label": "Asia/Taipei (台北 UTC+8)"},
        {"value": "Asia/Tokyo", "label": "Asia/Tokyo (東京 UTC+9)"},
        {"value": "Asia/Shanghai", "label": "Asia/Shanghai (上海 UTC+8)"},
        {"value": "Asia/Hong_Kong", "label": "Asia/Hong_Kong (香港 UTC+8)"},
        {"value": "Asia/Singapore", "label": "Asia/Singapore (新加坡 UTC+8)"},
        {"value": "America/New_York", "label": "America/New_York (紐約 UTC-5/-4)"},
        {"value": "America/Los_Angeles", "label": "America/Los_Angeles (洛杉磯 UTC-8/-7)"},
        {"value": "Europe/London", "label": "Europe/London (倫敦 UTC+0/+1)"},
        {"value": "Europe/Paris", "label": "Europe/Paris (巴黎 UTC+1/+2)"},
        {"value": "Australia/Sydney", "label": "Australia/Sydney (雪梨 UTC+10/+11)"},
    ]
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        options=common_timezones,
        description='Select timezone for conversion',
        ui={'allowCustomValue': True},
        group=FieldGroup.OPTIONS,
    )
