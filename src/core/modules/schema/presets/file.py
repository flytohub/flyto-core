"""
File Operation Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


def SOURCE_PATH(
    *,
    key: str = "source",
    required: bool = True,
    label: str = "Source Path",
    label_key: str = "schema.field.source_path",
    placeholder: str = "/path/to/source",
) -> Dict[str, Dict[str, Any]]:
    """Source file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def DESTINATION_PATH(
    *,
    key: str = "destination",
    required: bool = True,
    label: str = "Destination Path",
    label_key: str = "schema.field.destination_path",
    placeholder: str = "/path/to/destination",
) -> Dict[str, Dict[str, Any]]:
    """Destination file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def OVERWRITE(
    *,
    key: str = "overwrite",
    default: bool = False,
    label: str = "Overwrite",
    label_key: str = "schema.field.overwrite",
) -> Dict[str, Dict[str, Any]]:
    """Overwrite destination if it exists."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Overwrite destination if it exists',
    )


def IGNORE_MISSING(
    *,
    key: str = "ignore_missing",
    default: bool = False,
    label: str = "Ignore Missing",
    label_key: str = "schema.field.ignore_missing",
) -> Dict[str, Dict[str, Any]]:
    """Do not raise error if file does not exist."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Do not raise error if file does not exist',
    )


def WRITE_MODE(
    *,
    key: str = "mode",
    default: str = "overwrite",
    label: str = "Write Mode",
    label_key: str = "schema.field.write_mode",
) -> Dict[str, Dict[str, Any]]:
    """Write mode: overwrite or append."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["overwrite", "append"],
    )


def FILE_CONTENT(
    *,
    key: str = "content",
    required: bool = True,
    label: str = "Content",
    label_key: str = "schema.field.file_content",
) -> Dict[str, Dict[str, Any]]:
    """File content to write."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        format="multiline",
    )

