"""
Schema Builders - Composable schema construction utilities

Usage:
    from core.modules.schema import compose, field, patch, presets

    params_schema = compose(
        presets.URL(required=True),
        presets.TIMEOUT(default=30000),
        field("custom_field", type="string", label="Custom"),
    )
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, Union

Schema = Dict[str, Dict[str, Any]]
SchemaLike = Union[Schema, Mapping[str, Mapping[str, Any]]]


class SchemaComposeError(ValueError):
    """Raised when schema composition fails due to conflicts."""
    pass


def deep_merge(a: dict, b: dict) -> dict:
    """
    Deep merge dict b into dict a (returns new dict).
    - dict+dict => recursively merge
    - otherwise b overwrites a
    """
    out = deepcopy(a)
    for k, v in b.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def compose(*parts: SchemaLike, on_conflict: str = "error") -> Schema:
    """
    Compose multiple schema fragments into one schema dict.

    Args:
        *parts: Schema fragments to compose
        on_conflict: How to handle field key conflicts
            - "error": raise SchemaComposeError if same key appears twice
            - "overwrite": later part overwrites earlier
            - "merge": deep-merge field definitions (same key)

    Returns:
        Merged schema dict

    Example:
        schema = compose(
            presets.URL(required=True),
            presets.TIMEOUT(),
            {"custom": {"type": "string"}},
            on_conflict="merge"
        )
    """
    result: Schema = {}
    for part in parts:
        if part is None:
            continue
        for field_key, field_def in dict(part).items():
            if field_key not in result:
                result[field_key] = deepcopy(dict(field_def))
                continue

            if on_conflict == "error":
                raise SchemaComposeError(
                    f"Schema field conflict: '{field_key}' defined twice. "
                    f"Use on_conflict='merge' or 'overwrite' to resolve."
                )
            elif on_conflict == "overwrite":
                result[field_key] = deepcopy(dict(field_def))
            elif on_conflict == "merge":
                result[field_key] = deep_merge(result[field_key], dict(field_def))
            else:
                raise SchemaComposeError(f"Unknown on_conflict mode: {on_conflict}")
    return result


def field(
    key: str,
    *,
    type: str,
    label: Optional[str] = None,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
    description_key: Optional[str] = None,
    placeholder: Optional[str] = None,
    required: bool = False,
    default: Any = None,
    validation: Optional[dict] = None,
    options: Optional[List[dict]] = None,
    enum: Optional[List[str]] = None,
    min: Optional[float] = None,
    max: Optional[float] = None,
    step: Optional[float] = None,
    format: Optional[str] = None,
    ui: Optional[dict] = None,
    advanced: bool = False,
    visibility: Optional[str] = None,
    group: Optional[str] = None,
    # Dynamic schema conditions (ITEM_PIPELINE_SPEC.md Section 6)
    showIf: Optional[dict] = None,
    hideIf: Optional[dict] = None,
    dependsOn: Optional[List[str]] = None,
    displayOptions: Optional[dict] = None,
    # Dynamic options
    optionsFrom: Optional[str] = None,
    loadOptions: Optional[dict] = None,
    **extra: Any,
) -> Schema:
    """
    Helper to build a single field schema fragment.
    Supports i18n via label_key/description_key.
    Supports dynamic conditions via showIf/hideIf/dependsOn/displayOptions.

    Args:
        key: Field name in params
        type: Field type (string, number, boolean, select, object, array, file)
        label: Display label (fallback if label_key not found)
        label_key: i18n key for label
        description: Field description
        description_key: i18n key for description
        placeholder: Input placeholder text
        required: Whether field is required
        default: Default value
        validation: Validation rules (pattern, min, max, etc.)
        options: Select options [{value, label, label_key}]
        enum: Simple enum values (alternative to options)
        min: Minimum value (for numbers)
        max: Maximum value (for numbers)
        step: Step value (for numbers)
        format: Format hint (multiline, path, url, email, password, color, date, etc.)
        ui: UI rendering hints (widget, etc.)
        advanced: Mark as advanced/expert option (legacy, prefer visibility)
        visibility: Field visibility level ('default', 'expert', 'hidden')
        group: Field group name ('basic', 'connection', 'options', 'advanced')
        showIf: Condition to show field (e.g., {"operation": "create"})
        hideIf: Condition to hide field (e.g., {"mode": "simple"})
        dependsOn: List of fields this field depends on
        displayOptions: n8n-compatible display options (show/hide)
        optionsFrom: Dynamic options source (API endpoint or method name)
        loadOptions: Configuration for loading dynamic options
        **extra: Additional custom properties

    Returns:
        Schema fragment with single field: {key: {...}}

    Example:
        schema = field(
            "url",
            type="string",
            label_key="schema.field.url",
            placeholder="https://example.com",
            required=True,
            validation={"pattern": r"^https?://"}
        )

    Dynamic conditions example:
        schema = compose(
            field("operation", type="select", options=[
                {"value": "get", "label": "Get"},
                {"value": "create", "label": "Create"},
            ]),
            field("id", type="string",
                label="Record ID",
                showIf={"operation": {"$in": ["get", "update"]}},
                required=True
            ),
            field("data", type="object",
                label="Record Data",
                showIf={"operation": {"$in": ["create", "update"]}}
            ),
        )
    """
    d: Dict[str, Any] = {"type": type}

    # Labels and descriptions
    if label is not None:
        d["label"] = label
    if label_key is not None:
        d["label_key"] = label_key
    if description is not None:
        d["description"] = description
    if description_key is not None:
        d["description_key"] = description_key
    if placeholder is not None:
        d["placeholder"] = placeholder

    # Constraints
    if required:
        d["required"] = True
    if default is not None:
        d["default"] = default

    # Validation
    if validation is not None:
        d["validation"] = validation
    if min is not None:
        d.setdefault("validation", {})["min"] = min
    if max is not None:
        d.setdefault("validation", {})["max"] = max

    # Number specific
    if step is not None:
        d["step"] = step

    # Select/enum
    if options is not None:
        d["options"] = options
    if enum is not None:
        d["enum"] = enum

    # Format hint
    if format is not None:
        d["format"] = format

    # UI hints
    if ui is not None:
        d["ui"] = ui
    if advanced:
        d["advanced"] = True

    # Visibility: explicit > advanced flag > default
    if visibility is not None:
        d["visibility"] = visibility
    elif advanced:
        d["visibility"] = "expert"

    # Group
    if group is not None:
        d["group"] = group

    # Dynamic schema conditions (ITEM_PIPELINE_SPEC.md Section 6)
    if showIf is not None:
        d["showIf"] = showIf
    if hideIf is not None:
        d["hideIf"] = hideIf
    if dependsOn is not None:
        d["dependsOn"] = dependsOn
    if displayOptions is not None:
        d["displayOptions"] = displayOptions

    # Dynamic options
    if optionsFrom is not None:
        d["optionsFrom"] = optionsFrom
    if loadOptions is not None:
        d["loadOptions"] = loadOptions

    # Extra properties
    d.update(extra)

    return {key: d}


def patch(key: str, **updates: Any) -> Schema:
    """
    Create a patch for an existing field definition.
    Used with compose(..., on_conflict="merge") to override specific properties.

    Args:
        key: Field name to patch
        **updates: Properties to override/add

    Example:
        schema = compose(
            presets.URL(),
            patch("url", placeholder="https://api.example.com"),
            on_conflict="merge"
        )
    """
    return {key: updates}


def extend(base: Schema, *additions: SchemaLike) -> Schema:
    """
    Extend a base schema with additional fields.
    Convenience wrapper for compose with on_conflict="merge".

    Args:
        base: Base schema to extend
        *additions: Additional schema fragments

    Returns:
        Extended schema
    """
    return compose(base, *additions, on_conflict="merge")
