"""
Object Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def INPUT_OBJECT(
    *,
    key: str = "object",
    required: bool = True,
    label: str = "Object",
    label_key: str = "schema.field.input_object",
) -> Dict[str, Dict[str, Any]]:
    """Input object/dictionary field."""
    return field(
        key,
        type="json",
        label=label,
        label_key=label_key,
        required=required,
        description='Input object/dictionary',
        group=FieldGroup.BASIC,
    )


def INPUT_OBJECTS(
    *,
    key: str = "objects",
    required: bool = True,
    label: str = "Objects",
    label_key: str = "schema.field.input_objects",
) -> Dict[str, Dict[str, Any]]:
    """Array of objects to process."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Array of objects to process',
        group=FieldGroup.BASIC,
    )


def OBJECT_KEYS(
    *,
    key: str = "keys",
    required: bool = True,
    label: str = "Keys",
    label_key: str = "schema.field.object_keys",
) -> Dict[str, Dict[str, Any]]:
    """Array of object keys to pick or omit."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Keys to pick or omit',
        group=FieldGroup.BASIC,
    )
