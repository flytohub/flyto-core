"""
Encoding Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def ENCODE_TEXT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.encode_text",
) -> Dict[str, Dict[str, Any]]:
    """Text to encode."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Hello World",
        description='Text to encode',
        group=FieldGroup.BASIC,
    )


def ENCODING_TYPE(
    *,
    key: str = "encoding",
    default: str = "utf-8",
    label: str = "Encoding",
    label_key: str = "schema.field.encoding_type",
) -> Dict[str, Dict[str, Any]]:
    """Character encoding type."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Character encoding',
        group=FieldGroup.OPTIONS,
        options=[
            {'value': 'utf-8', 'label': 'UTF-8'},
            {'value': 'ascii', 'label': 'ASCII'},
            {'value': 'iso-8859-1', 'label': 'ISO-8859-1'},
            {'value': 'utf-16', 'label': 'UTF-16'},
        ]
    )


def URL_SAFE(
    *,
    key: str = "url_safe",
    default: bool = False,
    label: str = "URL Safe",
    label_key: str = "schema.field.url_safe",
) -> Dict[str, Dict[str, Any]]:
    """Use URL-safe encoding."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Use URL-safe encoding variant',
        group=FieldGroup.OPTIONS,
    )
