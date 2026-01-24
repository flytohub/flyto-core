"""
Validation Presets
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from ..builders import field
from ..constants import FieldGroup


def VALIDATE_EMAIL(
    *,
    key: str = "email",
    required: bool = True,
    label: str = "Email",
    label_key: str = "schema.field.validate_email",
) -> Dict[str, Dict[str, Any]]:
    """Email address to validate."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="user@example.com",
        description='Email address to validate',
        group=FieldGroup.BASIC,
    )


def VALIDATE_URL(
    *,
    key: str = "url",
    required: bool = True,
    label: str = "URL",
    label_key: str = "schema.field.validate_url",
) -> Dict[str, Dict[str, Any]]:
    """URL to validate."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="https://example.com",
        description='URL to validate',
        group=FieldGroup.BASIC,
    )


def VALIDATE_PHONE(
    *,
    key: str = "phone",
    required: bool = True,
    label: str = "Phone Number",
    label_key: str = "schema.field.validate_phone",
) -> Dict[str, Dict[str, Any]]:
    """Phone number to validate."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="+1234567890",
        description='Phone number to validate',
        group=FieldGroup.BASIC,
    )


def VALIDATE_UUID(
    *,
    key: str = "uuid",
    required: bool = True,
    label: str = "UUID",
    label_key: str = "schema.field.validate_uuid",
) -> Dict[str, Dict[str, Any]]:
    """UUID to validate."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="550e8400-e29b-41d4-a716-446655440000",
        description='UUID to validate',
        group=FieldGroup.BASIC,
    )


def VALIDATE_IP(
    *,
    key: str = "ip",
    required: bool = True,
    label: str = "IP Address",
    label_key: str = "schema.field.validate_ip",
) -> Dict[str, Dict[str, Any]]:
    """IP address to validate."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="192.168.1.1",
        description='IP address to validate',
        group=FieldGroup.BASIC,
    )


def VALIDATE_CARD(
    *,
    key: str = "card_number",
    required: bool = True,
    label: str = "Card Number",
    label_key: str = "schema.field.validate_card",
) -> Dict[str, Dict[str, Any]]:
    """Credit card number to validate."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder="4111111111111111",
        description='Credit card number to validate',
        group=FieldGroup.BASIC,
    )
