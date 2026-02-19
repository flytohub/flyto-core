# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Output/Display Presets
"""
from __future__ import annotations
from typing import Any, Dict
from ..builders import field
from ..constants import FieldGroup


def DISPLAY_TYPE(
    *,
    key: str = "type",
    default: str = "auto",
    label: str = "Display Type",
    label_key: str = "schema.field.display_type",
) -> Dict[str, Dict[str, Any]]:
    """Display output type."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "auto", "label": "Auto Detect"},
            {"value": "image", "label": "Image"},
            {"value": "text", "label": "Text"},
            {"value": "json", "label": "JSON"},
            {"value": "html", "label": "HTML"},
            {"value": "pdf", "label": "PDF"},
            {"value": "file", "label": "File"},
        ],
        description="Display type (auto-detected if not specified)",
        group=FieldGroup.BASIC,
    )


def DISPLAY_CONTENT(
    *,
    key: str = "content",
    required: bool = True,
    label: str = "Content",
    label_key: str = "schema.field.display_content",
    placeholder: str = "${step.output}",
) -> Dict[str, Dict[str, Any]]:
    """Content to display."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
        description="Content to display (data URI, text, JSON, or HTML)",
        group=FieldGroup.BASIC,
    )


def DISPLAY_TITLE(
    *,
    key: str = "title",
    required: bool = False,
    label: str = "Title",
    label_key: str = "schema.field.display_title",
) -> Dict[str, Dict[str, Any]]:
    """Optional display title."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description="Optional title for the display item",
        group=FieldGroup.BASIC,
    )


def DISPLAY_MODE(
    *,
    key: str = "mode",
    default: str = "display",
    label: str = "Mode",
    label_key: str = "schema.field.display_mode",
) -> Dict[str, Dict[str, Any]]:
    """Display mode: display/output/input."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "display", "label": "Display (debug inspector)"},
            {"value": "output", "label": "Output (workflow output)"},
            {"value": "input", "label": "Input (input receiver)"},
        ],
        description="Node mode: display for inspection, output for workflow results, input for receiving data",
        group=FieldGroup.OPTIONS,
    )


def DISPLAY_OUTPUT_KEY(
    *,
    key: str = "output_key",
    default: str = "result",
    label: str = "Output Key",
    label_key: str = "schema.field.display_output_key",
    placeholder: str = "result",
) -> Dict[str, Dict[str, Any]]:
    """Output key name for workflow output mode."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        placeholder=placeholder,
        description="Key name when used as workflow output",
        displayOptions={"show": {"mode": ["output"]}},
        group=FieldGroup.OPTIONS,
    )
