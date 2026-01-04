"""
Training/Practice Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def PRACTICE_URL(
    *,
    key: str = "url",
    required: bool = True,
    label: str = "URL",
    label_key: str = "schema.field.practice_url",
    placeholder: str = "https://example.com",
) -> Dict[str, Dict[str, Any]]:
    """URL for practice session."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validators.URL_HTTP,
        group=FieldGroup.BASIC,
    )


def PRACTICE_MAX_ITEMS(
    *,
    key: str = "max_items",
    default: int = 10,
    min_val: int = 1,
    max_val: int = 100,
    label: str = "Max Items",
    label_key: str = "schema.field.practice_max_items",
) -> Dict[str, Dict[str, Any]]:
    """Maximum items for practice."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Maximum items to process',
        group=FieldGroup.OPTIONS,
    )


def PRACTICE_SAMPLE_SIZE(
    *,
    key: str = "sample_size",
    default: int = 5,
    min_val: int = 1,
    max_val: int = 50,
    label: str = "Sample Size",
    label_key: str = "schema.field.practice_sample_size",
) -> Dict[str, Dict[str, Any]]:
    """Sample size for schema inference."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Number of samples to analyze',
        group=FieldGroup.OPTIONS,
    )
