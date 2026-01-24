"""
Path Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def PATH_INPUT(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "Path",
    label_key: str = "schema.field.path_input",
) -> Dict[str, Dict[str, Any]]:
    """File path input."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="/home/user/file.txt",
        description='File path',
        group=FieldGroup.BASIC,
    )


def PATH_PARTS(
    *,
    key: str = "parts",
    required: bool = True,
    label: str = "Path Parts",
    label_key: str = "schema.field.path_parts",
) -> Dict[str, Dict[str, Any]]:
    """Path components to join."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder='["/home", "user", "file.txt"]',
        description='Path components to join',
        group=FieldGroup.BASIC,
    )


def REMOVE_EXTENSION(
    *,
    key: str = "remove_extension",
    default: bool = False,
    label: str = "Remove Extension",
    label_key: str = "schema.field.remove_extension",
) -> Dict[str, Dict[str, Any]]:
    """Remove file extension from result."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Remove file extension from result',
        group=FieldGroup.OPTIONS,
    )


def RESOLVE_PATH(
    *,
    key: str = "resolve",
    default: bool = False,
    label: str = "Resolve",
    label_key: str = "schema.field.resolve_path",
) -> Dict[str, Dict[str, Any]]:
    """Resolve to absolute path."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Resolve to absolute path',
        group=FieldGroup.OPTIONS,
    )
