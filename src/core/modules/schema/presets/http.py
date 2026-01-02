"""
HTTP Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


def HTTP_METHOD(
    *,
    key: str = "method",
    default: str = "GET",
    label: str = "Method",
    label_key: str = "schema.field.http_method",
) -> Dict[str, Dict[str, Any]]:
    """HTTP method selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        group=FieldGroup.BASIC,
    )


def HEADERS(
    *,
    key: str = "headers",
    label: str = "Headers",
    label_key: str = "schema.field.headers",
) -> Dict[str, Dict[str, Any]]:
    """HTTP headers key-value editor."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        default={},
        ui={"widget": "key_value"},
        group=FieldGroup.OPTIONS,
    )


def REQUEST_BODY(
    *,
    key: str = "body",
    label: str = "Request Body",
    label_key: str = "schema.field.body",
) -> Dict[str, Dict[str, Any]]:
    """HTTP request body (JSON or text)."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        format="multiline",
        ui={"widget": "json_editor"},
        group=FieldGroup.OPTIONS,
    )


def CONTENT_TYPE(
    *,
    key: str = "content_type",
    default: str = "application/json",
    label: str = "Content Type",
    label_key: str = "schema.field.content_type",
) -> Dict[str, Dict[str, Any]]:
    """Content-Type header selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=[
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
            "text/plain",
            "text/html",
            "application/xml",
        ],
        group=FieldGroup.OPTIONS,
    )


def QUERY_PARAMS(
    *,
    key: str = "query",
    label: str = "Query Parameters",
    label_key: str = "schema.field.query_params",
) -> Dict[str, Dict[str, Any]]:
    """URL query parameters key-value editor."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        default={},
        ui={"widget": "key_value"},
        group=FieldGroup.OPTIONS,
    )


def FOLLOW_REDIRECTS(
    *,
    key: str = "follow_redirects",
    default: bool = True,
    label: str = "Follow Redirects",
    label_key: str = "schema.field.follow_redirects",
) -> Dict[str, Dict[str, Any]]:
    """HTTP follow redirects toggle."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description="Automatically follow HTTP redirects",
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
    )


def VERIFY_SSL(
    *,
    key: str = "verify_ssl",
    default: bool = True,
    label: str = "Verify SSL",
    label_key: str = "schema.field.verify_ssl",
) -> Dict[str, Dict[str, Any]]:
    """SSL certificate verification toggle."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description="Verify SSL certificates",
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
    )


def RESPONSE_TYPE(
    *,
    key: str = "response_type",
    default: str = "auto",
    label: str = "Response Type",
    label_key: str = "schema.field.response_type",
) -> Dict[str, Dict[str, Any]]:
    """Expected response format selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["auto", "json", "text", "binary"],
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
    )


def HTTP_AUTH(
    *,
    key: str = "auth",
    label: str = "Authentication",
    label_key: str = "schema.field.http_auth",
) -> Dict[str, Dict[str, Any]]:
    """HTTP authentication configuration."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        properties={
            "type": {
                "type": "string",
                "enum": ["bearer", "basic", "api_key"],
                "default": "bearer",
            },
            "token": {"type": "string", "format": "password"},
            "username": {"type": "string"},
            "password": {"type": "string", "format": "password"},
            "header_name": {"type": "string", "default": "X-API-Key"},
            "api_key": {"type": "string", "format": "password"},
        },
        ui={"widget": "auth_config"},
        group=FieldGroup.CONNECTION,
    )

