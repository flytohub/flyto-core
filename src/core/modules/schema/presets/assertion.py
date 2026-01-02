"""
Test/Assert Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


def HTTP_STATUS(
    *,
    key: str = "status",
    label: str = "Expected Status",
    label_key: str = "schema.field.http_status",
) -> Dict[str, Dict[str, Any]]:
    """Expected HTTP status code (number, array, or range)."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='Expected status code (number, array of numbers, or range string "200-299")',
        examples=[200, [200, 201], '200-299'],
    )


def BODY_CONTAINS(
    *,
    key: str = "body_contains",
    label: str = "Body Contains",
    label_key: str = "schema.field.body_contains",
) -> Dict[str, Dict[str, Any]]:
    """String or array of strings that body should contain."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='String or array of strings that body should contain',
    )


def BODY_NOT_CONTAINS(
    *,
    key: str = "body_not_contains",
    label: str = "Body Not Contains",
    label_key: str = "schema.field.body_not_contains",
) -> Dict[str, Dict[str, Any]]:
    """String or array of strings that body should NOT contain."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='String or array of strings that body should NOT contain',
    )


def REGEX_PATTERN(
    *,
    key: str = "pattern",
    label: str = "Regex Pattern",
    label_key: str = "schema.field.regex_pattern",
    placeholder: str = "^[a-z]+$",
) -> Dict[str, Dict[str, Any]]:
    """Regular expression pattern field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
    )


def JSON_PATH_ASSERTIONS(
    *,
    key: str = "json_path",
    label: str = "JSON Path Assertions",
    label_key: str = "schema.field.json_path_assertions",
) -> Dict[str, Dict[str, Any]]:
    """Object mapping JSON paths to expected values."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Object mapping JSON paths to expected values (e.g., {"data.id": 123})',
        ui={"widget": "key_value"},
    )


def JSON_PATH_EXISTS(
    *,
    key: str = "json_path_exists",
    label: str = "JSON Paths Exist",
    label_key: str = "schema.field.json_path_exists",
) -> Dict[str, Dict[str, Any]]:
    """Array of JSON paths that should exist."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Array of JSON paths that should exist',
    )


def HEADER_CONTAINS(
    *,
    key: str = "header_contains",
    label: str = "Headers Contain",
    label_key: str = "schema.field.header_contains",
) -> Dict[str, Dict[str, Any]]:
    """Object mapping header names to expected values."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Object mapping header names to expected values',
        ui={"widget": "key_value"},
    )


def MAX_DURATION_MS(
    *,
    key: str = "max_duration_ms",
    label: str = "Max Duration (ms)",
    label_key: str = "schema.field.max_duration_ms",
) -> Dict[str, Dict[str, Any]]:
    """Maximum allowed response time in milliseconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=False,
        min=0,
        description='Maximum allowed response time in milliseconds',
    )


def JSON_SCHEMA(
    *,
    key: str = "schema",
    label: str = "JSON Schema",
    label_key: str = "schema.field.json_schema",
) -> Dict[str, Dict[str, Any]]:
    """JSON Schema to validate response body against."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        advanced=True,
        description='JSON Schema to validate response body against',
        ui={"widget": "json_editor"},
    )


def FAIL_FAST(
    *,
    key: str = "fail_fast",
    default: bool = False,
    label: str = "Fail Fast",
    label_key: str = "schema.field.fail_fast",
) -> Dict[str, Dict[str, Any]]:
    """Stop on first assertion failure."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Stop on first assertion failure',
        advanced=True,
    )

