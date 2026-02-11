"""
Format Operations Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def FORMAT_NUMBER_INPUT(
    *,
    key: str = "number",
    required: bool = True,
    label: str = "Number",
    label_key: str = "schema.field.format_number",
) -> Dict[str, Dict[str, Any]]:
    """Number to format."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="1234567.89",
        description='Number to format',
        group=FieldGroup.BASIC,
    )


def FORMAT_DECIMAL_PLACES(
    *,
    key: str = "decimal_places",
    default: int = 2,
    min_val: int = 0,
    max_val: int = 10,
    label: str = "Decimal Places",
    label_key: str = "schema.field.decimal_places",
) -> Dict[str, Dict[str, Any]]:
    """Number of decimal places."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Number of decimal places',
        group=FieldGroup.OPTIONS,
    )


def THOUSAND_SEPARATOR(
    *,
    key: str = "thousand_separator",
    default: str = ",",
    label: str = "Thousand Separator",
    label_key: str = "schema.field.thousand_separator",
) -> Dict[str, Dict[str, Any]]:
    """Separator for thousands."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Separator for thousands',
        group=FieldGroup.OPTIONS,
    
        placeholder=',',
)


def CURRENCY_CODE(
    *,
    key: str = "currency",
    default: str = "USD",
    label: str = "Currency",
    label_key: str = "schema.field.currency_code",
) -> Dict[str, Dict[str, Any]]:
    """Currency code."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Currency code (USD, EUR, etc)',
        group=FieldGroup.BASIC,
        options=[
            {'value': 'USD', 'label': 'US Dollar ($)'},
            {'value': 'EUR', 'label': 'Euro (\u20ac)'},
            {'value': 'GBP', 'label': 'British Pound (\u00a3)'},
            {'value': 'JPY', 'label': 'Japanese Yen (\u00a5)'},
            {'value': 'CNY', 'label': 'Chinese Yuan (\u00a5)'},
            {'value': 'TWD', 'label': 'Taiwan Dollar (NT$)'},
        ]
    )


def BYTES_INPUT(
    *,
    key: str = "bytes",
    required: bool = True,
    label: str = "Bytes",
    label_key: str = "schema.field.bytes_input",
) -> Dict[str, Dict[str, Any]]:
    """Size in bytes."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="1048576",
        description='Size in bytes',
        group=FieldGroup.BASIC,
    )


def SECONDS_INPUT(
    *,
    key: str = "seconds",
    required: bool = True,
    label: str = "Seconds",
    label_key: str = "schema.field.seconds_input",
) -> Dict[str, Dict[str, Any]]:
    """Duration in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="3661",
        description='Duration in seconds',
        group=FieldGroup.BASIC,
    )
