"""
Search Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def SEARCH_KEYWORD(
    *,
    key: str = "keyword",
    required: bool = True,
    placeholder: str = "search query",
    label: str = "Keyword",
    label_key: str = "schema.field.search_keyword",
) -> Dict[str, Dict[str, Any]]:
    """Search keyword."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Search keyword or query',
        group=FieldGroup.BASIC,
    )


def SEARCH_LIMIT(
    *,
    key: str = "limit",
    default: int = 10,
    min_val: int = 1,
    max_val: int = 100,
    label: str = "Limit",
    label_key: str = "schema.field.search_limit",
) -> Dict[str, Dict[str, Any]]:
    """Search result limit."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        required=False,
        description='Maximum number of results',
        group=FieldGroup.OPTIONS,
    )
