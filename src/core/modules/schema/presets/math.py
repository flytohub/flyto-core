"""
Math Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def INPUT_NUMBER(
    *,
    key: str = "number",
    required: bool = True,
    label: str = "Number",
    label_key: str = "schema.field.input_number",
) -> Dict[str, Dict[str, Any]]:
    """Input number field for math operations."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='Number to process',
        group=FieldGroup.BASIC,
    )


def DECIMAL_PLACES(
    *,
    key: str = "decimals",
    default: int = 0,
    label: str = "Decimal Places",
    label_key: str = "schema.field.decimal_places",
) -> Dict[str, Dict[str, Any]]:
    """Number of decimal places for rounding."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        min=0,
        max=15,
        description='Number of decimal places',
        group=FieldGroup.OPTIONS,
    )


def MATH_BASE(
    *,
    key: str = "base",
    required: bool = True,
    label: str = "Base",
    label_key: str = "schema.field.math_base",
) -> Dict[str, Dict[str, Any]]:
    """Base number for power operations."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='Base number',
        group=FieldGroup.BASIC,
    )


def MATH_EXPONENT(
    *,
    key: str = "exponent",
    required: bool = True,
    label: str = "Exponent",
    label_key: str = "schema.field.math_exponent",
) -> Dict[str, Dict[str, Any]]:
    """Exponent for power operations."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='Power to raise to',
        group=FieldGroup.BASIC,
    )


def MATH_OPERATION(
    *,
    key: str = "operation",
    required: bool = True,
    label: str = "Operation",
    label_key: str = "schema.field.math_operation",
) -> Dict[str, Dict[str, Any]]:
    """Mathematical operation selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Operation to perform',
        options=[
            {'value': 'add', 'label': 'Add'},
            {'value': 'subtract', 'label': 'Subtract'},
            {'value': 'multiply', 'label': 'Multiply'},
            {'value': 'divide', 'label': 'Divide'},
            {'value': 'power', 'label': 'Power'},
            {'value': 'modulo', 'label': 'Modulo'},
            {'value': 'sqrt', 'label': 'Square Root'},
            {'value': 'abs', 'label': 'Absolute Value'},
        ],
        group=FieldGroup.BASIC,
    )


def FIRST_OPERAND(
    *,
    key: str = "a",
    required: bool = True,
    label: str = "First Number",
    label_key: str = "schema.field.first_operand",
) -> Dict[str, Dict[str, Any]]:
    """First operand for calculations."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='First operand',
        group=FieldGroup.BASIC,
    )


def SECOND_OPERAND(
    *,
    key: str = "b",
    required: bool = False,
    label: str = "Second Number",
    label_key: str = "schema.field.second_operand",
) -> Dict[str, Dict[str, Any]]:
    """Second operand for calculations (optional for unary ops)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='Second operand (not required for sqrt and abs)',
        group=FieldGroup.BASIC,
    )


def DECIMAL_PRECISION(
    *,
    key: str = "precision",
    default: int = 2,
    label: str = "Decimal Precision",
    label_key: str = "schema.field.decimal_precision",
) -> Dict[str, Dict[str, Any]]:
    """Decimal precision for calculation results."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Number of decimal places',
        group=FieldGroup.OPTIONS,
    )
