"""
Auth Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


def BEARER_TOKEN(
    *,
    key: str = "token",
    required: bool = True,
    label: str = "Bearer Token",
    label_key: str = "schema.field.bearer_token",
) -> Dict[str, Dict[str, Any]]:
    """Bearer token field (masked input)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        format="password",
        placeholder="${env.API_TOKEN}",
    )


def API_KEY(
    *,
    key: str = "api_key",
    header_name: str = "X-API-Key",
    required: bool = True,
    label: str = "API Key",
    label_key: str = "schema.field.api_key",
) -> Dict[str, Dict[str, Any]]:
    """API key field with header name."""
    return compose(
        field(
            key,
            type="string",
            label=label,
            label_key=label_key,
            required=required,
            format="password",
            placeholder="${env.API_KEY}",
        ),
        field(
            "header_name",
            type="string",
            label="Header Name",
            label_key="schema.field.api_key_header",
            default=header_name,
        ),
    )

