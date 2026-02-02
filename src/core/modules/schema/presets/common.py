"""
Common Presets / Common Field Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def URL(
    *,
    key: str = "url",
    required: bool = True,
    placeholder: str = "https://example.com",
    label: str = "URL",
    label_key: str = "schema.field.url",
    description: str = "URL to navigate to",
    http_only: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """URL input field with validation."""
    validation = validators.URL_HTTP if http_only else validators.URL_ANY
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description=description,
        placeholder=placeholder,
        required=required,
        validation=validation,
        group=FieldGroup.BASIC,
    )


def TEXT(
    *,
    key: str = "text",
    required: bool = False,
    placeholder: str = "",
    label: str = "Text",
    label_key: str = "schema.field.text",
    description: str = "",
    multiline: bool = False,
    max_length: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Text input field."""
    validation = None
    if max_length:
        validation = validators.length(max_len=max_length)

    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description=description,
        placeholder=placeholder,
        required=required,
        validation=validation,
        format="multiline" if multiline else None,
    )


def FILE_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "File Path",
    label_key: str = "schema.field.file_path",
    placeholder: str = "/path/to/file",
    description: str = "Path to the file",
) -> Dict[str, Dict[str, Any]]:
    """File path input field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description=description,
        placeholder=placeholder,
        required=required,
        format="path",
        group=FieldGroup.BASIC,
    )


def TIMEOUT_MS(
    *,
    key: str = "timeout",
    default: int = 30000,
    min_ms: int = 0,
    max_ms: int = 300000,
    label: str = "Timeout (ms)",
    label_key: str = "schema.field.timeout_ms",
) -> Dict[str, Dict[str, Any]]:
    """Timeout field in milliseconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        description="Maximum time to wait in milliseconds",
        default=default,
        min=min_ms,
        max=max_ms,
        step=100,
        ui={"unit": "ms"},
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
    )


def TIMEOUT_S(
    *,
    key: str = "timeout",
    default: int = 30,
    min_s: int = 0,
    max_s: int = 300,
    label: str = "Timeout (seconds)",
    label_key: str = "schema.field.timeout_s",
) -> Dict[str, Dict[str, Any]]:
    """Timeout field in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        description="Maximum time to wait in seconds",
        default=default,
        min=min_s,
        max=max_s,
        step=1,
        ui={"unit": "s"},
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
    )


def DURATION_MS(
    *,
    key: str = "duration_ms",
    default: int = 1000,
    min_ms: int = 0,
    max_ms: int = 300000,
    label: str = "Duration (ms)",
    label_key: str = "schema.field.duration_ms",
) -> Dict[str, Dict[str, Any]]:
    """Duration field in milliseconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        description="Duration of the operation in milliseconds",
        default=default,
        min=min_ms,
        max=max_ms,
        step=100,
        ui={"unit": "ms"},
        visibility=Visibility.DEFAULT,
        group=FieldGroup.BASIC,
    )


def DURATION_S(
    *,
    key: str = "duration_s",
    default: float = 1,
    min_s: float = 0,
    max_s: float = 300,
    label: str = "Duration (seconds)",
    label_key: str = "schema.field.duration_s",
) -> Dict[str, Dict[str, Any]]:
    """Duration field in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        description="Duration of the operation in seconds",
        default=default,
        min=min_s,
        max=max_s,
        step=0.1,
        ui={"unit": "s"},
        visibility=Visibility.DEFAULT,
        group=FieldGroup.BASIC,
    )


def BOOLEAN(
    *,
    key: str,
    default: bool = False,
    label: str,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Boolean toggle field."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description=description,
    )


def NUMBER(
    *,
    key: str,
    default: float = 0,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    step: float = 1,
    label: str,
    label_key: Optional[str] = None,
    description: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Numeric input field."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        description=description,
        default=default,
        min=min_val,
        max=max_val,
        step=step,
    )


def SELECT(
    *,
    key: str,
    options: List[Dict[str, Any]],
    default: Optional[str] = None,
    required: bool = False,
    label: str,
    label_key: Optional[str] = None,
    description: str = "Select an option",
) -> Dict[str, Dict[str, Any]]:
    """Select dropdown field."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        description=description,
        options=options,
        default=default or (options[0]["value"] if options else None),
        required=required,
    )

def DESCRIPTION(
    *,
    key: str = "description",
    label: str = "Description",
    label_key: str = "schema.field.description",
    multiline: bool = False,
    placeholder: str = "Enter description...",
) -> Dict[str, Dict[str, Any]]:
    """Generic description field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description="Optional description text",
        required=False,
        placeholder=placeholder,
        format="multiline" if multiline else None,
        group=FieldGroup.OPTIONS,
    )



