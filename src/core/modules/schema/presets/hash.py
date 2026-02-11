"""
Hash Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def HASH_TEXT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.hash_text",
) -> Dict[str, Dict[str, Any]]:
    """Text to hash."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Hello World",
        description='Text to hash',
        group=FieldGroup.BASIC,
    )


def HASH_ENCODING(
    *,
    key: str = "encoding",
    default: str = "utf-8",
    label: str = "Encoding",
    label_key: str = "schema.field.hash_encoding",
) -> Dict[str, Dict[str, Any]]:
    """Text encoding."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Text encoding',
        group=FieldGroup.OPTIONS,
    
        placeholder='hex',
)


def HASH_ALGORITHM(
    *,
    key: str = "algorithm",
    default: str = "sha256",
    label: str = "Algorithm",
    label_key: str = "schema.field.hash_algorithm",
) -> Dict[str, Dict[str, Any]]:
    """Hash algorithm."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Hash algorithm',
        group=FieldGroup.BASIC,
        options=[
            {'value': 'md5', 'label': 'MD5'},
            {'value': 'sha1', 'label': 'SHA-1'},
            {'value': 'sha256', 'label': 'SHA-256'},
            {'value': 'sha512', 'label': 'SHA-512'},
        ]
    )
