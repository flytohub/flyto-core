"""
Vision/AI Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def VISION_IMAGE(
    *,
    key: str = "image",
    required: bool = True,
    label: str = "Image",
    label_key: str = "schema.field.vision_image",
    placeholder: str = "./screenshots/home.png",
) -> Dict[str, Dict[str, Any]]:
    """Image for AI vision analysis (path, URL, or base64)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Image file path, URL, or base64 data',
        group=FieldGroup.BASIC,
    )


def VISION_PROMPT(
    *,
    key: str = "prompt",
    required: bool = True,
    label: str = "Analysis Prompt",
    label_key: str = "schema.field.vision_prompt",
    placeholder: str = "Analyze this UI screenshot...",
) -> Dict[str, Dict[str, Any]]:
    """Prompt for vision analysis."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        multiline=True,
        description='What to analyze in the image',
        group=FieldGroup.BASIC,
    )


def VISION_ANALYSIS_TYPE(
    *,
    key: str = "analysis_type",
    default: str = "general",
    label: str = "Analysis Type",
    label_key: str = "schema.field.vision_analysis_type",
) -> Dict[str, Dict[str, Any]]:
    """Type of vision analysis."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "general", "label": "General Analysis"},
            {"value": "ui_review", "label": "UI/UX Review"},
            {"value": "accessibility", "label": "Accessibility Check"},
            {"value": "bug_detection", "label": "Bug Detection"},
            {"value": "comparison", "label": "Image Comparison"},
            {"value": "data_extraction", "label": "Data Extraction"},
        ],
        description='Type of analysis to perform',
        group=FieldGroup.OPTIONS,
    )


def VISION_OUTPUT_FORMAT(
    *,
    key: str = "output_format",
    default: str = "structured",
    label: str = "Output Format",
    label_key: str = "schema.field.vision_output_format",
) -> Dict[str, Dict[str, Any]]:
    """Output format for vision analysis."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "text", "label": "Plain Text"},
            {"value": "structured", "label": "Structured Text"},
            {"value": "json", "label": "JSON (machine-readable)"},
            {"value": "checklist", "label": "Checklist"},
        ],
        description='Format of the analysis output',
        group=FieldGroup.OPTIONS,
    )


def VISION_CONTEXT(
    *,
    key: str = "context",
    required: bool = False,
    label: str = "Additional Context",
    label_key: str = "schema.field.vision_context",
    placeholder: str = "This is a dashboard page for a SaaS app...",
) -> Dict[str, Dict[str, Any]]:
    """Additional context for vision analysis."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        multiline=True,
        description='Additional context about the image',
        group=FieldGroup.OPTIONS,
    )


def VISION_DETAIL(
    *,
    key: str = "detail",
    default: str = "high",
    label: str = "Detail Level",
    label_key: str = "schema.field.vision_detail",
) -> Dict[str, Dict[str, Any]]:
    """Image detail level for vision analysis."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "low", "label": "Low (fast)"},
            {"value": "high", "label": "High (detailed)"},
            {"value": "auto", "label": "Auto"},
        ],
        description='Level of detail for image analysis',
        group=FieldGroup.OPTIONS,
    )


def VISION_IMAGE_BEFORE(
    *,
    key: str = "image_before",
    required: bool = True,
    label: str = "Before Image",
    label_key: str = "schema.field.vision_image_before",
    placeholder: str = "./screenshots/baseline.png",
) -> Dict[str, Dict[str, Any]]:
    """Before/baseline image for comparison."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Path to baseline/before image',
        group=FieldGroup.BASIC,
    )


def VISION_IMAGE_AFTER(
    *,
    key: str = "image_after",
    required: bool = True,
    label: str = "After Image",
    label_key: str = "schema.field.vision_image_after",
    placeholder: str = "./screenshots/current.png",
) -> Dict[str, Dict[str, Any]]:
    """After/current image for comparison."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Path to current/after image',
        group=FieldGroup.BASIC,
    )


def VISION_COMPARISON_TYPE(
    *,
    key: str = "comparison_type",
    default: str = "visual_regression",
    label: str = "Comparison Type",
    label_key: str = "schema.field.vision_comparison_type",
) -> Dict[str, Dict[str, Any]]:
    """Type of image comparison."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {"value": "visual_regression", "label": "Visual Regression (pixel-level)"},
            {"value": "layout_diff", "label": "Layout Diff (structure)"},
            {"value": "content_diff", "label": "Content Diff (text)"},
            {"value": "full_analysis", "label": "Full Analysis"},
        ],
        description='Type of comparison to perform',
        group=FieldGroup.OPTIONS,
    )


def VISION_THRESHOLD(
    *,
    key: str = "threshold",
    default: int = 5,
    min_val: int = 0,
    max_val: int = 100,
    label: str = "Threshold (%)",
    label_key: str = "schema.field.vision_threshold",
) -> Dict[str, Dict[str, Any]]:
    """Acceptable difference threshold."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Acceptable difference percentage',
        group=FieldGroup.OPTIONS,
    )


def VISION_FOCUS_AREAS(
    *,
    key: str = "focus_areas",
    required: bool = False,
    label: str = "Focus Areas",
    label_key: str = "schema.field.vision_focus_areas",
) -> Dict[str, Dict[str, Any]]:
    """Areas to focus comparison on."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Specific areas to focus on',
        group=FieldGroup.OPTIONS,
    )


def VISION_IGNORE_AREAS(
    *,
    key: str = "ignore_areas",
    required: bool = False,
    label: str = "Ignore Areas",
    label_key: str = "schema.field.vision_ignore_areas",
) -> Dict[str, Dict[str, Any]]:
    """Areas to ignore in comparison."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Areas to ignore (dynamic content, ads, etc.)',
        group=FieldGroup.OPTIONS,
    )
