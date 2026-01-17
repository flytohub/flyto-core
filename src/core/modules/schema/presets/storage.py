"""
Storage Presets - Key-Value storage field definitions
"""
from __future__ import annotations
from typing import Any, Dict
from ..builders import field
from ..constants import FieldGroup


def STORAGE_NAMESPACE(
    *,
    key: str = "namespace",
    required: bool = True,
    default: str = "default",
    placeholder: str = "my-workflow",
    label: str = "Namespace",
    label_key: str = "schema.field.storage_namespace",
) -> Dict[str, Dict[str, Any]]:
    """Storage namespace for grouping related keys."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        default=default,
        required=required,
        description='Storage namespace (e.g., workflow name or project)',
        group=FieldGroup.BASIC,
    )


def STORAGE_KEY(
    *,
    key: str = "key",
    required: bool = True,
    placeholder: str = "last_value",
    label: str = "Key",
    label_key: str = "schema.field.storage_key",
) -> Dict[str, Dict[str, Any]]:
    """Storage key for retrieving/storing values."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Key to store or retrieve value',
        group=FieldGroup.BASIC,
    )


def STORAGE_VALUE(
    *,
    key: str = "value",
    required: bool = True,
    placeholder: str = "",
    label: str = "Value",
    label_key: str = "schema.field.storage_value",
) -> Dict[str, Dict[str, Any]]:
    """Value to store."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Value to store (string, number, or object)',
        group=FieldGroup.BASIC,
    )


def STORAGE_DEFAULT(
    *,
    key: str = "default",
    required: bool = False,
    label: str = "Default Value",
    label_key: str = "schema.field.storage_default",
) -> Dict[str, Dict[str, Any]]:
    """Default value if key not found."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to return if key does not exist',
        group=FieldGroup.OPTIONS,
    )


def STORAGE_TTL(
    *,
    key: str = "ttl_seconds",
    required: bool = False,
    default: int = 0,
    label: str = "TTL (seconds)",
    label_key: str = "schema.field.storage_ttl",
) -> Dict[str, Dict[str, Any]]:
    """Time-to-live in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=required,
        min=0,
        max=31536000,
        description='Time to live in seconds (0 = no expiration)',
        group=FieldGroup.OPTIONS,
    )
