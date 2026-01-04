"""
Array Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def INPUT_ARRAY(
    *,
    key: str = "array",
    required: bool = True,
    label: str = "Array",
    label_key: str = "schema.field.input_array",
) -> Dict[str, Dict[str, Any]]:
    """Input array field."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        group=FieldGroup.BASIC,
    )


def FILTER_CONDITION(
    *,
    key: str = "condition",
    required: bool = True,
    label: str = "Condition",
    label_key: str = "schema.field.filter_condition",
) -> Dict[str, Dict[str, Any]]:
    """Filter condition selector (gt, lt, eq, ne, contains)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        options=[
            {'value': 'gt', 'label': 'Greater Than'},
            {'value': 'lt', 'label': 'Less Than'},
            {'value': 'eq', 'label': 'Equal'},
            {'value': 'ne', 'label': 'Not Equal'},
            {'value': 'contains', 'label': 'Contains'},
        ],
        group=FieldGroup.BASIC,
    )


def COMPARE_VALUE(
    *,
    key: str = "value",
    required: bool = True,
    label: str = "Value",
    label_key: str = "schema.field.compare_value",
) -> Dict[str, Dict[str, Any]]:
    """Value to compare against."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to compare against',
        group=FieldGroup.BASIC,
    )


def ARRAY_OPERATION(
    *,
    key: str = "operation",
    required: bool = True,
    label: str = "Operation",
    label_key: str = "schema.field.array_operation",
) -> Dict[str, Dict[str, Any]]:
    """Array transformation operation selector."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        required=required,
        options=[
            {'value': 'multiply', 'label': 'Multiply'},
            {'value': 'add', 'label': 'Add'},
            {'value': 'extract', 'label': 'Extract field'},
            {'value': 'uppercase', 'label': 'To uppercase'},
            {'value': 'lowercase', 'label': 'To lowercase'},
        ],
        group=FieldGroup.BASIC,
    )


def SORT_ORDER(
    *,
    key: str = "order",
    default: str = "asc",
    label: str = "Order",
    label_key: str = "schema.field.sort_order",
) -> Dict[str, Dict[str, Any]]:
    """Sort order selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {'value': 'asc', 'label': 'Ascending'},
            {'value': 'desc', 'label': 'Descending'},
        ],
        group=FieldGroup.OPTIONS,
    )


def CHUNK_SIZE(
    *,
    key: str = "size",
    required: bool = True,
    label: str = "Chunk Size",
    label_key: str = "schema.field.chunk_size",
) -> Dict[str, Dict[str, Any]]:
    """Size of each chunk."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=1,
        description='Size of each chunk',
        group=FieldGroup.BASIC,
    )


def FLATTEN_DEPTH(
    *,
    key: str = "depth",
    default: int = 1,
    label: str = "Depth",
    label_key: str = "schema.field.flatten_depth",
) -> Dict[str, Dict[str, Any]]:
    """Depth level to flatten (-1 for infinite)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        description='Depth level to flatten (default: 1, use -1 for infinite)',
        group=FieldGroup.OPTIONS,
    )


def PRESERVE_ORDER(
    *,
    key: str = "preserve_order",
    default: bool = True,
    label: str = "Preserve Order",
    label_key: str = "schema.field.preserve_order",
) -> Dict[str, Dict[str, Any]]:
    """Maintain original order of elements."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Maintain original order of elements',
        group=FieldGroup.OPTIONS,
    )


def OPERATION_VALUE(
    *,
    key: str = "value",
    label: str = "Value",
    label_key: str = "schema.field.operation_value",
) -> Dict[str, Dict[str, Any]]:
    """Value for operation (number for math, field name for extract)."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='Value for operation (number for math, field name for extract)',
        group=FieldGroup.OPTIONS,
    )


def REDUCE_OPERATION(
    *,
    key: str = "operation",
    required: bool = True,
    label: str = "Operation",
    label_key: str = "schema.field.reduce_operation",
) -> Dict[str, Dict[str, Any]]:
    """Reduction operation selector."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        required=required,
        options=[
            {'value': 'sum', 'label': 'Sum'},
            {'value': 'product', 'label': 'Product'},
            {'value': 'average', 'label': 'Average'},
            {'value': 'min', 'label': 'Min'},
            {'value': 'max', 'label': 'Max'},
            {'value': 'join', 'label': 'Join'},
        ],
        group=FieldGroup.BASIC,
    )


def SEPARATOR(
    *,
    key: str = "separator",
    default: str = ",",
    label: str = "Separator",
    label_key: str = "schema.field.separator",
) -> Dict[str, Dict[str, Any]]:
    """Separator string for join operations."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='String to insert between elements',
        group=FieldGroup.OPTIONS,
    )


def SECOND_ARRAY(
    *,
    key: str = "array2",
    required: bool = True,
    label: str = "Second Array",
    label_key: str = "schema.field.second_array",
) -> Dict[str, Dict[str, Any]]:
    """Second input array for set operations."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        group=FieldGroup.BASIC,
    )


def ARRAYS(
    *,
    key: str = "arrays",
    required: bool = True,
    label: str = "Arrays",
    label_key: str = "schema.field.arrays",
) -> Dict[str, Dict[str, Any]]:
    """Multiple arrays for set operations (intersection, union)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Arrays to process',
        group=FieldGroup.BASIC,
    )


def SUBTRACT_ARRAYS(
    *,
    key: str = "subtract",
    required: bool = True,
    label: str = "Subtract Arrays",
    label_key: str = "schema.field.subtract_arrays",
) -> Dict[str, Dict[str, Any]]:
    """Arrays to subtract from base array."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Arrays to subtract from base',
        group=FieldGroup.BASIC,
    )
