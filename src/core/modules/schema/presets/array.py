"""
Array Presets - Array/list processing field configurations
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
    label: str = "Input Array",
    label_key: str = "schema.field.input_array",
) -> Dict[str, Dict[str, Any]]:
    """Input array field."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder='[1, 2, 3] or ["a", "b", "c"]',
        description='Array of items to process. Can be numbers, strings, or objects.',
        group=FieldGroup.BASIC,
    )


def FILTER_CONDITION(
    *,
    key: str = "condition",
    required: bool = True,
    label: str = "Condition",
    label_key: str = "schema.field.filter_condition",
) -> Dict[str, Dict[str, Any]]:
    """Filter condition selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        options=[
            {'value': 'eq', 'label': '= Equal to'},
            {'value': 'ne', 'label': '!= Not equal to'},
            {'value': 'gt', 'label': '> Greater than'},
            {'value': 'gte', 'label': '>= Greater or equal'},
            {'value': 'lt', 'label': '< Less than'},
            {'value': 'lte', 'label': '<= Less or equal'},
            {'value': 'contains', 'label': 'Contains (text)'},
            {'value': 'startswith', 'label': 'Starts with'},
            {'value': 'endswith', 'label': 'Ends with'},
            {'value': 'regex', 'label': 'Matches regex'},
            {'value': 'in', 'label': 'In list'},
            {'value': 'notin', 'label': 'Not in list'},
            {'value': 'exists', 'label': 'Field exists'},
            {'value': 'empty', 'label': 'Is empty'},
            {'value': 'notempty', 'label': 'Is not empty'},
        ],
        description='How to compare each item against the value',
        group=FieldGroup.BASIC,
    )


def COMPARE_VALUE(
    *,
    key: str = "value",
    required: bool = False,
    label: str = "Compare Value",
    label_key: str = "schema.field.compare_value",
) -> Dict[str, Dict[str, Any]]:
    """Value to compare against."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="Enter value to compare...",
        description='Value to compare each item against (leave empty for exists/empty checks)',
        group=FieldGroup.BASIC,
    )


def FILTER_FIELD(
    *,
    key: str = "field",
    required: bool = False,
    label: str = "Field Name",
    label_key: str = "schema.field.filter_field",
) -> Dict[str, Dict[str, Any]]:
    """Field name to filter on (for object arrays)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="name, price, data.nested.value",
        description='Field path to compare (e.g., "price" or "user.name"). Leave empty for simple arrays.',
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
            {'value': 'multiply', 'label': '× Multiply (numbers)'},
            {'value': 'add', 'label': '+ Add (numbers)'},
            {'value': 'subtract', 'label': '- Subtract (numbers)'},
            {'value': 'divide', 'label': '÷ Divide (numbers)'},
            {'value': 'extract', 'label': 'Extract field (objects)'},
            {'value': 'uppercase', 'label': 'To UPPERCASE (strings)'},
            {'value': 'lowercase', 'label': 'To lowercase (strings)'},
            {'value': 'trim', 'label': 'Trim whitespace (strings)'},
            {'value': 'tostring', 'label': 'Convert to string'},
            {'value': 'tonumber', 'label': 'Convert to number'},
        ],
        description='Transformation to apply to each item',
        group=FieldGroup.BASIC,
    )


def SORT_ORDER(
    *,
    key: str = "order",
    default: str = "asc",
    label: str = "Sort Order",
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
            {'value': 'asc', 'label': '↑ Ascending (A-Z, 1-9)'},
            {'value': 'desc', 'label': '↓ Descending (Z-A, 9-1)'},
        ],
        description='Direction to sort items',
        group=FieldGroup.OPTIONS,
    )


def SORT_BY(
    *,
    key: str = "sort_by",
    required: bool = False,
    label: str = "Sort By Field",
    label_key: str = "schema.field.sort_by",
) -> Dict[str, Dict[str, Any]]:
    """Field to sort by (for object arrays)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="name, created_at, data.score",
        description='Field path to sort by. Leave empty for simple arrays.',
        group=FieldGroup.OPTIONS,
    )


def CHUNK_SIZE(
    *,
    key: str = "size",
    required: bool = True,
    default: int = 10,
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
        default=default,
        min=1,
        max=10000,
        placeholder="10",
        description='Number of items per chunk',
        group=FieldGroup.BASIC,
    )


def FLATTEN_DEPTH(
    *,
    key: str = "depth",
    default: int = 1,
    label: str = "Flatten Depth",
    label_key: str = "schema.field.flatten_depth",
) -> Dict[str, Dict[str, Any]]:
    """Depth level to flatten."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=-1,
        max=100,
        options=[
            {'value': 1, 'label': '1 level (default)'},
            {'value': 2, 'label': '2 levels'},
            {'value': 3, 'label': '3 levels'},
            {'value': -1, 'label': 'Infinite (fully flatten)'},
        ],
        description='How many levels of nesting to flatten (-1 for infinite)',
        ui={'allowCustomValue': True},
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
        description='Keep items in their original order (when possible)',
        group=FieldGroup.OPTIONS,
    )


def OPERATION_VALUE(
    *,
    key: str = "value",
    label: str = "Operation Value",
    label_key: str = "schema.field.operation_value",
) -> Dict[str, Dict[str, Any]]:
    """Value for operation."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        placeholder="Number for math, field name for extract",
        description='Value for the operation: number for math operations, field name for extract',
        group=FieldGroup.OPTIONS,
    )


def REDUCE_OPERATION(
    *,
    key: str = "operation",
    required: bool = True,
    label: str = "Reduce Operation",
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
            {'value': 'sum', 'label': 'Σ Sum (add all numbers)'},
            {'value': 'product', 'label': '∏ Product (multiply all numbers)'},
            {'value': 'average', 'label': 'x̄ Average (mean)'},
            {'value': 'min', 'label': '↓ Minimum value'},
            {'value': 'max', 'label': '↑ Maximum value'},
            {'value': 'count', 'label': '# Count items'},
            {'value': 'join', 'label': '+ Join (concatenate strings)'},
            {'value': 'first', 'label': '← First item'},
            {'value': 'last', 'label': '→ Last item'},
        ],
        description='How to combine all items into a single value',
        group=FieldGroup.BASIC,
    )


def SEPARATOR(
    *,
    key: str = "separator",
    default: str = ", ",
    label: str = "Separator",
    label_key: str = "schema.field.separator",
) -> Dict[str, Dict[str, Any]]:
    """Separator string for join operations."""
    common_separators = [
        {"value": ", ", "label": ", (Comma space)"},
        {"value": ",", "label": ", (Comma)"},
        {"value": " ", "label": "Space"},
        {"value": "\n", "label": "Newline"},
        {"value": " | ", "label": " | (Pipe)"},
        {"value": " - ", "label": " - (Dash)"},
        {"value": "", "label": "(No separator)"},
    ]
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=common_separators,
        placeholder=", ",
        description='String to insert between items when joining',
        ui={'allowCustomValue': True},
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
        placeholder='[3, 4, 5]',
        description='Second array for comparison operations',
        group=FieldGroup.BASIC,
    )


def ARRAYS(
    *,
    key: str = "arrays",
    required: bool = True,
    label: str = "Arrays",
    label_key: str = "schema.field.arrays",
) -> Dict[str, Dict[str, Any]]:
    """Multiple arrays for set operations."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder='[[1,2], [2,3], [3,4]]',
        description='Array of arrays to process (for intersection, union)',
        group=FieldGroup.BASIC,
    )


def SUBTRACT_ARRAYS(
    *,
    key: str = "subtract",
    required: bool = True,
    label: str = "Arrays to Subtract",
    label_key: str = "schema.field.subtract_arrays",
) -> Dict[str, Dict[str, Any]]:
    """Arrays to subtract from base array."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        placeholder='[[2], [4]]',
        description='Arrays containing items to remove from the base array',
        group=FieldGroup.BASIC,
    )


def LIMIT(
    *,
    key: str = "limit",
    default: int = None,
    label: str = "Limit",
    label_key: str = "schema.field.limit",
) -> Dict[str, Dict[str, Any]]:
    """Maximum number of items to return."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=0,
        placeholder="No limit",
        description='Maximum number of items to return (leave empty for all)',
        group=FieldGroup.OPTIONS,
    )


def SKIP(
    *,
    key: str = "skip",
    default: int = 0,
    label: str = "Skip",
    label_key: str = "schema.field.skip",
) -> Dict[str, Dict[str, Any]]:
    """Number of items to skip from the start."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=0,
        placeholder="0",
        description='Number of items to skip from the beginning',
        group=FieldGroup.OPTIONS,
    )
