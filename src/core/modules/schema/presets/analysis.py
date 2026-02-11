"""
Analysis/HTML Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def HTML_CONTENT(
    *,
    key: str = "html",
    required: bool = True,
    label: str = "HTML",
    label_key: str = "schema.field.html_content",
) -> Dict[str, Dict[str, Any]]:
    """HTML content to analyze."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='HTML content to analyze',
        group=FieldGroup.BASIC,
    
        placeholder='<html><body>content</body></html>',
)

