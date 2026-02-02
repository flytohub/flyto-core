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
        options=[
            {"value": "GET", "label": "GET (read data)"},
            {"value": "POST", "label": "POST (create/submit)"},
            {"value": "PUT", "label": "PUT (replace)"},
            {"value": "PATCH", "label": "PATCH (update)"},
            {"value": "DELETE", "label": "DELETE (remove)"},
            {"value": "HEAD", "label": "HEAD (headers only)"},
            {"value": "OPTIONS", "label": "OPTIONS (allowed methods)"},
        ],
        description='HTTP request method',
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
        description="HTTP request headers as key-value pairs",
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
        description="HTTP request body content (JSON, text, or form data)",
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
        options=[
            {"value": "application/json", "label": "JSON (application/json)"},
            {"value": "application/x-www-form-urlencoded", "label": "Form URL Encoded"},
            {"value": "multipart/form-data", "label": "Multipart (file upload)"},
            {"value": "text/plain", "label": "Plain Text"},
            {"value": "text/html", "label": "HTML"},
            {"value": "application/xml", "label": "XML"},
        ],
        description='Content type of the request body',
        ui={'allowCustomValue': True},
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
        description="URL query string parameters as key-value pairs",
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
        options=[
            {"value": "auto", "label": "Auto-detect"},
            {"value": "json", "label": "JSON (parse as object)"},
            {"value": "text", "label": "Text (raw string)"},
            {"value": "binary", "label": "Binary (base64)"},
        ],
        description='How to parse the response body',
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
        description="Authentication credentials for the HTTP request",
        required=False,
        properties={
            "type": {
                "type": "string",
                "description": "Authentication type",
                "enum": ["bearer", "basic", "api_key"],
                "default": "bearer",
            },
            "token": {"type": "string", "description": "Bearer token", "format": "password"},
            "username": {"type": "string", "description": "Basic auth username"},
            "password": {"type": "string", "description": "Basic auth password", "format": "password"},
            "header_name": {"type": "string", "description": "API key header name", "default": "X-API-Key"},
            "api_key": {"type": "string", "description": "API key value", "format": "password"},
        },
        ui={"widget": "auth_config"},
        group=FieldGroup.CONNECTION,
    )

