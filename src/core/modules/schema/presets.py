"""
Schema Presets - Reusable field definitions for common parameters

Usage:
    from core.modules.schema import presets, compose

    params_schema = compose(
        presets.URL(required=True),
        presets.SELECTOR(),
        presets.TIMEOUT_MS(default=30000),
    )

Categories:
    - Common: URL, TEXT, FILE_PATH, TIMEOUT
    - Browser: SELECTOR, WAIT_CONDITION, VIEWPORT
    - HTTP: METHOD, HEADERS, BODY, CONTENT_TYPE
    - Auth: BEARER_TOKEN, BASIC_AUTH, API_KEY
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .builders import field
from . import validators


# ============================================
# Common Presets
# ============================================

def URL(
    *,
    key: str = "url",
    required: bool = True,
    placeholder: str = "https://example.com",
    label: str = "URL",
    label_key: str = "schema.field.url",
    http_only: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """URL input field with validation."""
    validation = validators.URL_HTTP if http_only else validators.URL_ANY
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validation,
    )


def TEXT(
    *,
    key: str = "text",
    required: bool = False,
    placeholder: str = "",
    label: str = "Text",
    label_key: str = "schema.field.text",
    multiline: bool = False,
    max_length: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Text input field."""
    validation = None
    if max_length:
        validation = validators.length(max_len=max_length)

    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validation,
        format="multiline" if multiline else None,
    )


def FILE_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "File Path",
    label_key: str = "schema.field.file_path",
    placeholder: str = "/path/to/file",
) -> Dict[str, Dict[str, Any]]:
    """File path input field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def TIMEOUT_MS(
    *,
    key: str = "timeout",
    default: int = 30000,
    min_ms: int = 0,
    max_ms: int = 300000,
    label: str = "Timeout (ms)",
    label_key: str = "schema.field.timeout_ms",
) -> Dict[str, Dict[str, Any]]:
    """Timeout field in milliseconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_ms,
        max=max_ms,
        step=100,
        ui={"unit": "ms"},
    )


def TIMEOUT_S(
    *,
    key: str = "timeout",
    default: int = 30,
    min_s: int = 0,
    max_s: int = 300,
    label: str = "Timeout (seconds)",
    label_key: str = "schema.field.timeout_s",
) -> Dict[str, Dict[str, Any]]:
    """Timeout field in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_s,
        max=max_s,
        step=1,
        ui={"unit": "s"},
    )


def BOOLEAN(
    *,
    key: str,
    default: bool = False,
    label: str,
    label_key: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Boolean toggle field."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description=description,
    )


def NUMBER(
    *,
    key: str,
    default: float = 0,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    step: float = 1,
    label: str,
    label_key: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Numeric input field."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        step=step,
    )


def SELECT(
    *,
    key: str,
    options: List[Dict[str, Any]],
    default: Optional[str] = None,
    required: bool = False,
    label: str,
    label_key: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Select dropdown field."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        options=options,
        default=default or (options[0]["value"] if options else None),
        required=required,
    )


# ============================================
# Browser Presets
# ============================================

def SELECTOR(
    *,
    key: str = "selector",
    required: bool = True,
    label: str = "Element Selector",
    label_key: str = "schema.field.selector",
    placeholder: str = "#element, .class, or xpath=//div",
) -> Dict[str, Dict[str, Any]]:
    """CSS/XPath selector field for browser automation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validators.SELECTOR,
        ui={"widget": "selector"},
    )


def WAIT_CONDITION(
    *,
    key: str = "wait_until",
    default: str = "domcontentloaded",
    label: str = "Wait Condition",
    label_key: str = "schema.field.wait_until",
) -> Dict[str, Dict[str, Any]]:
    """Page load wait condition selector."""
    options = [
        {"value": "load", "label": "Page Load Complete", "label_key": "schema.option.wait.load"},
        {"value": "domcontentloaded", "label": "DOM Content Loaded", "label_key": "schema.option.wait.domcontentloaded"},
        {"value": "networkidle", "label": "Network Idle", "label_key": "schema.option.wait.networkidle"},
    ]
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        options=options,
        default=default,
    )


def VIEWPORT(
    *,
    width_key: str = "width",
    height_key: str = "height",
    default_width: int = 1280,
    default_height: int = 720,
) -> Dict[str, Dict[str, Any]]:
    """Viewport dimensions (returns two fields: width and height)."""
    from .builders import compose
    return compose(
        field(
            width_key,
            type="number",
            label="Width",
            label_key="schema.field.viewport_width",
            default=default_width,
            min=320,
            max=3840,
            step=1,
        ),
        field(
            height_key,
            type="number",
            label="Height",
            label_key="schema.field.viewport_height",
            default=default_height,
            min=240,
            max=2160,
            step=1,
        ),
    )


def SCREENSHOT_OPTIONS(
    *,
    full_page_key: str = "full_page",
    format_key: str = "format",
) -> Dict[str, Dict[str, Any]]:
    """Screenshot options (full page toggle, format select)."""
    from .builders import compose
    return compose(
        field(
            full_page_key,
            type="boolean",
            label="Full Page",
            label_key="schema.field.full_page",
            default=False,
        ),
        field(
            format_key,
            type="select",
            label="Format",
            label_key="schema.field.screenshot_format",
            options=[
                {"value": "png", "label": "PNG"},
                {"value": "jpeg", "label": "JPEG"},
                {"value": "webp", "label": "WebP"},
            ],
            default="png",
        ),
    )


def BROWSER_HEADLESS(
    *,
    key: str = "headless",
    default: bool = True,
    label: str = "Headless Mode",
    label_key: str = "schema.field.headless",
) -> Dict[str, Dict[str, Any]]:
    """Headless browser mode toggle."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description="Run browser without visible window",
    )


# ============================================
# HTTP Presets
# ============================================

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
        advanced=True,
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
        advanced=True,
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
        advanced=True,
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
        advanced=True,
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
    )


# ============================================
# Auth Presets
# ============================================

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
    from .builders import compose
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


# ============================================
# Additional Browser Presets
# ============================================

def DURATION_S(
    *,
    key: str = "duration",
    default: float = 1,
    min_s: float = 0,
    max_s: float = 300,
    label: str = "Duration (seconds)",
    label_key: str = "schema.field.duration_s",
) -> Dict[str, Dict[str, Any]]:
    """Duration field in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_s,
        max=max_s,
        step=0.1,
        ui={"unit": "s"},
    )


def OUTPUT_PATH(
    *,
    key: str = "path",
    default: str = "",
    required: bool = False,
    label: str = "Output Path",
    label_key: str = "schema.field.output_path",
    placeholder: str = "output/file.png",
) -> Dict[str, Dict[str, Any]]:
    """Output file path field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        default=default,
        required=required,
        format="path",
    )


def POSITION(
    *,
    key: str = "position",
    label: str = "Position",
    label_key: str = "schema.field.position",
) -> Dict[str, Dict[str, Any]]:
    """Position object field {x, y}."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        advanced=True,
        properties={
            "x": {"type": "number", "min": 0, "max": 1, "default": 0.5},
            "y": {"type": "number", "min": 0, "max": 1, "default": 0.5},
        },
    )


# ============================================
# Data Presets
# ============================================

def ENCODING(
    *,
    key: str = "encoding",
    default: str = "utf-8",
    label: str = "Encoding",
    label_key: str = "schema.field.encoding",
) -> Dict[str, Dict[str, Any]]:
    """File encoding selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["utf-8", "ascii", "latin-1", "utf-16", "gbk", "big5"],
        advanced=True,
    )


def JSON_PATH(
    *,
    key: str = "path",
    required: bool = False,
    label: str = "JSON Path",
    label_key: str = "schema.field.json_path",
    placeholder: str = "$.data.items[0]",
) -> Dict[str, Dict[str, Any]]:
    """JSON path selector field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validators.JSON_PATH,
    )


def DELIMITER(
    *,
    key: str = "delimiter",
    default: str = ",",
    label: str = "Delimiter",
    label_key: str = "schema.field.delimiter",
) -> Dict[str, Dict[str, Any]]:
    """CSV/text delimiter field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=[",", ";", "\t", "|", " "],
        advanced=True,
    )


# ============================================
# Test/Assert Presets
# ============================================

def HTTP_STATUS(
    *,
    key: str = "status",
    label: str = "Expected Status",
    label_key: str = "schema.field.http_status",
) -> Dict[str, Dict[str, Any]]:
    """Expected HTTP status code (number, array, or range)."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='Expected status code (number, array of numbers, or range string "200-299")',
        examples=[200, [200, 201], '200-299'],
    )


def BODY_CONTAINS(
    *,
    key: str = "body_contains",
    label: str = "Body Contains",
    label_key: str = "schema.field.body_contains",
) -> Dict[str, Dict[str, Any]]:
    """String or array of strings that body should contain."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='String or array of strings that body should contain',
    )


def BODY_NOT_CONTAINS(
    *,
    key: str = "body_not_contains",
    label: str = "Body Not Contains",
    label_key: str = "schema.field.body_not_contains",
) -> Dict[str, Dict[str, Any]]:
    """String or array of strings that body should NOT contain."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=False,
        description='String or array of strings that body should NOT contain',
    )


def REGEX_PATTERN(
    *,
    key: str = "pattern",
    label: str = "Regex Pattern",
    label_key: str = "schema.field.regex_pattern",
    placeholder: str = "^[a-z]+$",
) -> Dict[str, Dict[str, Any]]:
    """Regular expression pattern field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
    )


def JSON_PATH_ASSERTIONS(
    *,
    key: str = "json_path",
    label: str = "JSON Path Assertions",
    label_key: str = "schema.field.json_path_assertions",
) -> Dict[str, Dict[str, Any]]:
    """Object mapping JSON paths to expected values."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Object mapping JSON paths to expected values (e.g., {"data.id": 123})',
        ui={"widget": "key_value"},
    )


def JSON_PATH_EXISTS(
    *,
    key: str = "json_path_exists",
    label: str = "JSON Paths Exist",
    label_key: str = "schema.field.json_path_exists",
) -> Dict[str, Dict[str, Any]]:
    """Array of JSON paths that should exist."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Array of JSON paths that should exist',
    )


def HEADER_CONTAINS(
    *,
    key: str = "header_contains",
    label: str = "Headers Contain",
    label_key: str = "schema.field.header_contains",
) -> Dict[str, Dict[str, Any]]:
    """Object mapping header names to expected values."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Object mapping header names to expected values',
        ui={"widget": "key_value"},
    )


def MAX_DURATION_MS(
    *,
    key: str = "max_duration_ms",
    label: str = "Max Duration (ms)",
    label_key: str = "schema.field.max_duration_ms",
) -> Dict[str, Dict[str, Any]]:
    """Maximum allowed response time in milliseconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=False,
        min=0,
        description='Maximum allowed response time in milliseconds',
    )


def JSON_SCHEMA(
    *,
    key: str = "schema",
    label: str = "JSON Schema",
    label_key: str = "schema.field.json_schema",
) -> Dict[str, Dict[str, Any]]:
    """JSON Schema to validate response body against."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        advanced=True,
        description='JSON Schema to validate response body against',
        ui={"widget": "json_editor"},
    )


def FAIL_FAST(
    *,
    key: str = "fail_fast",
    default: bool = False,
    label: str = "Fail Fast",
    label_key: str = "schema.field.fail_fast",
) -> Dict[str, Dict[str, Any]]:
    """Stop on first assertion failure."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Stop on first assertion failure',
        advanced=True,
    )


# ============================================
# JSON Presets
# ============================================

def JSON_STRING(
    *,
    key: str = "json_string",
    required: bool = True,
    label: str = "JSON String",
    label_key: str = "schema.field.json_string",
    placeholder: str = '{"name": "John", "age": 30}',
) -> Dict[str, Dict[str, Any]]:
    """JSON string input field."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
    )


def DATA_OBJECT(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.data_object",
) -> Dict[str, Dict[str, Any]]:
    """Data object input field."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
    )


def DATA_ARRAY(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.data_array",
) -> Dict[str, Dict[str, Any]]:
    """Data array input field."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
    )


def PRETTY_PRINT(
    *,
    key: str = "pretty",
    default: bool = False,
    label: str = "Pretty Print",
    label_key: str = "schema.field.pretty_print",
) -> Dict[str, Dict[str, Any]]:
    """Pretty print toggle for JSON output."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Format with indentation',
    )


def INDENT_SIZE(
    *,
    key: str = "indent",
    default: int = 2,
    min_val: int = 1,
    max_val: int = 8,
    label: str = "Indent Size",
    label_key: str = "schema.field.indent_size",
) -> Dict[str, Dict[str, Any]]:
    """Indentation size for pretty printing."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Indentation spaces (if pretty=true)',
    )


# ============================================
# CSV Presets
# ============================================

def INCLUDE_HEADER(
    *,
    key: str = "include_header",
    default: bool = True,
    label: str = "Include Header",
    label_key: str = "schema.field.include_header",
) -> Dict[str, Dict[str, Any]]:
    """Include column headers in first row."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Include column headers in first row',
    )


def SKIP_HEADER(
    *,
    key: str = "skip_header",
    default: bool = False,
    label: str = "Skip Header",
    label_key: str = "schema.field.skip_header",
) -> Dict[str, Dict[str, Any]]:
    """Skip first row (header)."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Skip first row (header)',
    )


def FLATTEN_NESTED(
    *,
    key: str = "flatten_nested",
    default: bool = True,
    label: str = "Flatten Nested Objects",
    label_key: str = "schema.field.flatten_nested",
) -> Dict[str, Dict[str, Any]]:
    """Flatten nested objects using dot notation."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Flatten nested objects using dot notation (e.g., address.city)',
    )


def COLUMNS(
    *,
    key: str = "columns",
    label: str = "Columns",
    label_key: str = "schema.field.columns",
) -> Dict[str, Dict[str, Any]]:
    """Specific columns to include."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        default=[],
        description='Specific columns to include (empty = all columns)',
    )


# ============================================
# Template Presets
# ============================================

def TEMPLATE(
    *,
    key: str = "template",
    required: bool = True,
    label: str = "Template",
    label_key: str = "schema.field.template",
    placeholder: str = "Hello {name}, you have {count} messages.",
) -> Dict[str, Dict[str, Any]]:
    """Text template with {variable} placeholders."""
    return field(
        key,
        type="text",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
        description='Text template with {variable} placeholders',
    )


def VARIABLES(
    *,
    key: str = "variables",
    required: bool = True,
    label: str = "Variables",
    label_key: str = "schema.field.variables",
) -> Dict[str, Dict[str, Any]]:
    """Object with variable values for template."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='Object with variable values',
        ui={"widget": "key_value"},
    )


def INPUT_DATA(
    *,
    key: str = "input_data",
    required: bool = True,
    label: str = "Input Data",
    label_key: str = "schema.field.input_data",
) -> Dict[str, Dict[str, Any]]:
    """Any type input data (JSON, file path, etc.)."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=required,
        description='JSON data (array of objects) or path to JSON file',
    )


# ============================================
# Shell/Process Presets
# ============================================

def COMMAND(
    *,
    key: str = "command",
    required: bool = True,
    label: str = "Command",
    label_key: str = "schema.field.command",
    placeholder: str = "npm install",
) -> Dict[str, Dict[str, Any]]:
    """Shell command to execute."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
    )


def WORKING_DIR(
    *,
    key: str = "cwd",
    label: str = "Working Directory",
    label_key: str = "schema.field.working_dir",
    placeholder: str = "/path/to/project",
) -> Dict[str, Dict[str, Any]]:
    """Directory to execute command in."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
        format="path",
    )


def ENV_VARS(
    *,
    key: str = "env",
    label: str = "Environment Variables",
    label_key: str = "schema.field.env_vars",
) -> Dict[str, Dict[str, Any]]:
    """Additional environment variables."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        ui={"widget": "key_value"},
    )


def USE_SHELL(
    *,
    key: str = "shell",
    default: bool = True,
    label: str = "Use Shell",
    label_key: str = "schema.field.use_shell",
) -> Dict[str, Dict[str, Any]]:
    """Execute command through shell."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Execute command through shell (enables pipes, redirects)',
        advanced=True,
    )


def CAPTURE_STDERR(
    *,
    key: str = "capture_stderr",
    default: bool = True,
    label: str = "Capture Stderr",
    label_key: str = "schema.field.capture_stderr",
) -> Dict[str, Dict[str, Any]]:
    """Capture stderr separately from stdout."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        advanced=True,
    )


def RAISE_ON_ERROR(
    *,
    key: str = "raise_on_error",
    default: bool = False,
    label: str = "Raise on Error",
    label_key: str = "schema.field.raise_on_error",
) -> Dict[str, Dict[str, Any]]:
    """Raise exception if command returns non-zero exit code."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        advanced=True,
    )


def PROCESS_NAME(
    *,
    key: str = "name",
    label: str = "Process Name",
    label_key: str = "schema.field.process_name",
    placeholder: str = "dev-server",
) -> Dict[str, Dict[str, Any]]:
    """Friendly name for the process."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
    )


def WAIT_FOR_OUTPUT(
    *,
    key: str = "wait_for_output",
    label: str = "Wait for Output",
    label_key: str = "schema.field.wait_for_output",
    placeholder: str = "ready on",
) -> Dict[str, Dict[str, Any]]:
    """String to wait for in stdout before returning."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
        description='String to wait for in stdout before returning',
    )


def CAPTURE_OUTPUT(
    *,
    key: str = "capture_output",
    default: bool = True,
    label: str = "Capture Output",
    label_key: str = "schema.field.capture_output",
) -> Dict[str, Dict[str, Any]]:
    """Capture stdout/stderr."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


def LOG_FILE(
    *,
    key: str = "log_file",
    label: str = "Log File",
    label_key: str = "schema.field.log_file",
) -> Dict[str, Dict[str, Any]]:
    """File to write process output to."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        format="path",
        advanced=True,
    )


def AUTO_RESTART(
    *,
    key: str = "auto_restart",
    default: bool = False,
    label: str = "Auto Restart",
    label_key: str = "schema.field.auto_restart",
) -> Dict[str, Dict[str, Any]]:
    """Automatically restart if process exits."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        advanced=True,
    )


def SIGNAL_TYPE(
    *,
    key: str = "signal",
    default: str = "SIGTERM",
    label: str = "Signal",
    label_key: str = "schema.field.signal",
) -> Dict[str, Dict[str, Any]]:
    """Signal to send to process."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["SIGTERM", "SIGKILL", "SIGINT"],
        advanced=True,
    )


def FORCE_KILL(
    *,
    key: str = "force",
    default: bool = False,
    label: str = "Force Kill",
    label_key: str = "schema.field.force_kill",
) -> Dict[str, Dict[str, Any]]:
    """Use SIGKILL immediately."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


def STOP_ALL(
    *,
    key: str = "stop_all",
    default: bool = False,
    label: str = "Stop All",
    label_key: str = "schema.field.stop_all",
) -> Dict[str, Dict[str, Any]]:
    """Stop all tracked processes."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


def PROCESS_ID(
    *,
    key: str = "process_id",
    label: str = "Process ID",
    label_key: str = "schema.field.process_id",
) -> Dict[str, Dict[str, Any]]:
    """Internal process ID."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
    )


def PID(
    *,
    key: str = "pid",
    label: str = "PID",
    label_key: str = "schema.field.pid",
) -> Dict[str, Dict[str, Any]]:
    """System process ID."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=False,
    )


def FILTER_NAME(
    *,
    key: str = "filter_name",
    label: str = "Filter by Name",
    label_key: str = "schema.field.filter_name",
) -> Dict[str, Dict[str, Any]]:
    """Filter by name (substring match)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
    )


def INCLUDE_STATUS(
    *,
    key: str = "include_status",
    default: bool = True,
    label: str = "Include Status",
    label_key: str = "schema.field.include_status",
) -> Dict[str, Dict[str, Any]]:
    """Include running/stopped status check."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


# ============================================
# File Operation Presets
# ============================================

def SOURCE_PATH(
    *,
    key: str = "source",
    required: bool = True,
    label: str = "Source Path",
    label_key: str = "schema.field.source_path",
    placeholder: str = "/path/to/source",
) -> Dict[str, Dict[str, Any]]:
    """Source file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def DESTINATION_PATH(
    *,
    key: str = "destination",
    required: bool = True,
    label: str = "Destination Path",
    label_key: str = "schema.field.destination_path",
    placeholder: str = "/path/to/destination",
) -> Dict[str, Dict[str, Any]]:
    """Destination file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def OVERWRITE(
    *,
    key: str = "overwrite",
    default: bool = False,
    label: str = "Overwrite",
    label_key: str = "schema.field.overwrite",
) -> Dict[str, Dict[str, Any]]:
    """Overwrite destination if it exists."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Overwrite destination if it exists',
    )


def IGNORE_MISSING(
    *,
    key: str = "ignore_missing",
    default: bool = False,
    label: str = "Ignore Missing",
    label_key: str = "schema.field.ignore_missing",
) -> Dict[str, Dict[str, Any]]:
    """Do not raise error if file does not exist."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Do not raise error if file does not exist',
    )


def WRITE_MODE(
    *,
    key: str = "mode",
    default: str = "overwrite",
    label: str = "Write Mode",
    label_key: str = "schema.field.write_mode",
) -> Dict[str, Dict[str, Any]]:
    """Write mode: overwrite or append."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["overwrite", "append"],
    )


def FILE_CONTENT(
    *,
    key: str = "content",
    required: bool = True,
    label: str = "Content",
    label_key: str = "schema.field.file_content",
) -> Dict[str, Dict[str, Any]]:
    """File content to write."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        format="multiline",
    )


# ============================================
# LLM Presets
# ============================================

def LLM_PROMPT(
    *,
    key: str = "prompt",
    required: bool = True,
    label: str = "Prompt",
    label_key: str = "schema.field.llm_prompt",
    placeholder: str = "Analyze this code and suggest improvements...",
) -> Dict[str, Dict[str, Any]]:
    """LLM prompt input field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
    )


def SYSTEM_PROMPT(
    *,
    key: str = "system_prompt",
    required: bool = False,
    label: str = "System Prompt",
    label_key: str = "schema.field.system_prompt",
    placeholder: str = "You are an expert code reviewer...",
) -> Dict[str, Dict[str, Any]]:
    """System prompt to set LLM context and behavior."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="multiline",
    )


def LLM_CONTEXT(
    *,
    key: str = "context",
    label: str = "Context Data",
    label_key: str = "schema.field.llm_context",
) -> Dict[str, Dict[str, Any]]:
    """Additional context data to include in prompt."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Additional context data to include',
    )


def CONVERSATION_MESSAGES(
    *,
    key: str = "messages",
    label: str = "Conversation History",
    label_key: str = "schema.field.conversation_messages",
) -> Dict[str, Dict[str, Any]]:
    """Previous messages for multi-turn conversation."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Previous messages for multi-turn conversation',
    )


def LLM_PROVIDER(
    *,
    key: str = "provider",
    default: str = "openai",
    label: str = "Provider",
    label_key: str = "schema.field.llm_provider",
) -> Dict[str, Dict[str, Any]]:
    """LLM provider selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["openai", "anthropic", "ollama"],
    )


def LLM_MODEL(
    *,
    key: str = "model",
    default: str = "gpt-4o",
    label: str = "Model",
    label_key: str = "schema.field.llm_model",
) -> Dict[str, Dict[str, Any]]:
    """LLM model selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Specific model to use',
        examples=[
            'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo',
            'claude-3-5-sonnet-20241022', 'claude-3-opus-20240229',
            'llama2', 'codellama', 'mistral'
        ],
    )


def TEMPERATURE(
    *,
    key: str = "temperature",
    default: float = 0.7,
    min_val: float = 0,
    max_val: float = 2,
    label: str = "Temperature",
    label_key: str = "schema.field.temperature",
) -> Dict[str, Dict[str, Any]]:
    """LLM creativity level (0=deterministic, 1=creative)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        step=0.1,
        description='Creativity level (0=deterministic, 1=creative)',
    )


def MAX_TOKENS(
    *,
    key: str = "max_tokens",
    default: int = 2000,
    label: str = "Max Tokens",
    label_key: str = "schema.field.max_tokens",
) -> Dict[str, Dict[str, Any]]:
    """Maximum tokens in LLM response."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=1,
        max=128000,
        description='Maximum tokens in response',
    )


def LLM_RESPONSE_FORMAT(
    *,
    key: str = "response_format",
    default: str = "text",
    label: str = "Response Format",
    label_key: str = "schema.field.llm_response_format",
) -> Dict[str, Dict[str, Any]]:
    """Expected LLM response format."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["text", "json", "code", "markdown"],
    )


def LLM_API_KEY(
    *,
    key: str = "api_key",
    label: str = "API Key",
    label_key: str = "schema.field.llm_api_key",
) -> Dict[str, Dict[str, Any]]:
    """LLM API key (defaults to provider env var)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        format="password",
        description='API key (defaults to provider env var)',
        advanced=True,
    )


def LLM_BASE_URL(
    *,
    key: str = "base_url",
    label: str = "Base URL",
    label_key: str = "schema.field.llm_base_url",
    placeholder: str = "http://localhost:11434/v1",
) -> Dict[str, Dict[str, Any]]:
    """Custom API base URL (for Ollama or proxies)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=False,
        advanced=True,
        description='Custom API base URL (for Ollama or proxies)',
    )


def CODE_ISSUES(
    *,
    key: str = "issues",
    required: bool = True,
    label: str = "Issues",
    label_key: str = "schema.field.code_issues",
) -> Dict[str, Dict[str, Any]]:
    """List of issues to fix (from ui.evaluate, test results, etc.)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='List of issues to fix (from ui.evaluate, test results, etc.)',
    )


def SOURCE_FILES(
    *,
    key: str = "source_files",
    required: bool = True,
    label: str = "Source Files",
    label_key: str = "schema.field.source_files",
) -> Dict[str, Dict[str, Any]]:
    """Files to analyze and potentially fix."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Files to analyze and potentially fix',
    )


def FIX_MODE(
    *,
    key: str = "fix_mode",
    default: str = "suggest",
    label: str = "Fix Mode",
    label_key: str = "schema.field.fix_mode",
) -> Dict[str, Dict[str, Any]]:
    """How to apply code fixes."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["suggest", "apply", "dry_run"],
        options=[
            {"value": "suggest", "label": "Suggest Only - Return fixes without applying"},
            {"value": "apply", "label": "Apply - Write fixes to files"},
            {"value": "dry_run", "label": "Dry Run - Show what would change"},
        ],
    )


def CREATE_BACKUP(
    *,
    key: str = "backup",
    default: bool = True,
    label: str = "Create Backup",
    label_key: str = "schema.field.create_backup",
) -> Dict[str, Dict[str, Any]]:
    """Create .bak backup before modifying files."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Create .bak backup before modifying files',
    )


# ============================================
# Array Presets
# ============================================

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
    )


# ============================================
# String Presets
# ============================================

def INPUT_TEXT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.input_text",
    placeholder: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Input text string field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='The string to process',
    )


def SEARCH_STRING(
    *,
    key: str = "search",
    required: bool = True,
    label: str = "Search",
    label_key: str = "schema.field.search_string",
) -> Dict[str, Dict[str, Any]]:
    """Substring to search for."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='The substring to search for',
    )


def REPLACE_STRING(
    *,
    key: str = "replace",
    required: bool = True,
    label: str = "Replace With",
    label_key: str = "schema.field.replace_string",
) -> Dict[str, Dict[str, Any]]:
    """Replacement string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='The replacement string',
    )


def STRING_DELIMITER(
    *,
    key: str = "delimiter",
    default: str = " ",
    label: str = "Delimiter",
    label_key: str = "schema.field.string_delimiter",
) -> Dict[str, Dict[str, Any]]:
    """Delimiter for string split operations."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='The delimiter to split on',
    )


# ============================================
# Common Field Presets
# ============================================

def DESCRIPTION(
    *,
    key: str = "description",
    label: str = "Description",
    label_key: str = "schema.field.description",
    multiline: bool = False,
    placeholder: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Generic description field."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        format="multiline" if multiline else None,
    )


def SELECT(
    *,
    key: str,
    label: str,
    options: list,
    default: str = None,
    required: bool = False,
    label_key: str = None,
) -> Dict[str, Dict[str, Any]]:
    """Generic select field with custom options."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key or f"schema.field.{key}",
        default=default,
        required=required,
        options=options,
    )


# ============================================
# Flow Control Presets
# ============================================

def CONDITION_EXPRESSION(
    *,
    key: str = "condition",
    required: bool = True,
    label: str = "Condition",
    label_key: str = "schema.field.condition_expression",
    placeholder: str = "${step1.count} > 0",
) -> Dict[str, Dict[str, Any]]:
    """Condition expression for branching."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Expression to evaluate (supports ==, !=, >, <, >=, <=, contains)',
    )


def SWITCH_EXPRESSION(
    *,
    key: str = "expression",
    required: bool = True,
    label: str = "Expression",
    label_key: str = "schema.field.switch_expression",
) -> Dict[str, Dict[str, Any]]:
    """Value to match against switch cases."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to match against cases (supports variable reference)',
    )


def SWITCH_CASES(
    *,
    key: str = "cases",
    required: bool = True,
    label: str = "Cases",
    label_key: str = "schema.field.switch_cases",
) -> Dict[str, Dict[str, Any]]:
    """Switch case definitions."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='List of case definitions',
    )


def TRIGGER_TYPE(
    *,
    key: str = "trigger_type",
    default: str = "manual",
    label: str = "Trigger Type",
    label_key: str = "schema.field.trigger_type",
) -> Dict[str, Dict[str, Any]]:
    """Trigger type selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["manual", "webhook", "schedule", "event"],
    )


def WEBHOOK_PATH(
    *,
    key: str = "webhook_path",
    label: str = "Webhook Path",
    label_key: str = "schema.field.webhook_path",
    placeholder: str = "/api/webhooks/my-webhook",
) -> Dict[str, Dict[str, Any]]:
    """Webhook URL path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        description='URL path for webhook trigger',
    )


def CRON_SCHEDULE(
    *,
    key: str = "schedule",
    label: str = "Schedule",
    label_key: str = "schema.field.cron_schedule",
    placeholder: str = "0 * * * *",
) -> Dict[str, Dict[str, Any]]:
    """Cron expression for scheduled triggers."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        description='Cron expression for scheduled trigger',
    )


def EVENT_NAME(
    *,
    key: str = "event_name",
    label: str = "Event Name",
    label_key: str = "schema.field.event_name",
) -> Dict[str, Dict[str, Any]]:
    """Event name to listen for."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Event name to listen for',
    )


def OUTPUT_MAPPING(
    *,
    key: str = "output_mapping",
    label: str = "Output Mapping",
    label_key: str = "schema.field.output_mapping",
) -> Dict[str, Dict[str, Any]]:
    """Map internal variables to workflow output."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        default={},
        description='Map internal variables to workflow output',
    )


def MERGE_STRATEGY(
    *,
    key: str = "strategy",
    default: str = "all",
    label: str = "Merge Strategy",
    label_key: str = "schema.field.merge_strategy",
) -> Dict[str, Dict[str, Any]]:
    """How to merge multiple inputs."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["first", "last", "all"],
        description='How to merge multiple inputs',
    )


def JOIN_STRATEGY(
    *,
    key: str = "strategy",
    default: str = "all",
    label: str = "Join Strategy",
    label_key: str = "schema.field.join_strategy",
) -> Dict[str, Dict[str, Any]]:
    """How to handle multiple inputs in join."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["all", "any", "first"],
        description='How to handle multiple inputs',
    )


def PORT_COUNT(
    *,
    key: str = "input_count",
    default: int = 2,
    min_val: int = 2,
    max_val: int = 10,
    label: str = "Input Count",
    label_key: str = "schema.field.port_count",
) -> Dict[str, Dict[str, Any]]:
    """Number of dynamic ports."""
    return field(
        key,
        type="integer",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Number of ports',
    )


def BRANCH_COUNT(
    *,
    key: str = "branch_count",
    default: int = 2,
    label: str = "Branch Count",
    label_key: str = "schema.field.branch_count",
) -> Dict[str, Dict[str, Any]]:
    """Number of parallel branches."""
    return field(
        key,
        type="integer",
        label=label,
        label_key=label_key,
        default=default,
        min=2,
        max=10,
        description='Number of parallel branches',
    )


def TARGET_STEP(
    *,
    key: str = "target",
    required: bool = True,
    label: str = "Target Step",
    label_key: str = "schema.field.target_step",
) -> Dict[str, Dict[str, Any]]:
    """Step ID to jump to."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Step ID to jump to',
    )


def MAX_ITERATIONS(
    *,
    key: str = "max_iterations",
    default: int = 100,
    label: str = "Max Iterations",
    label_key: str = "schema.field.max_iterations",
) -> Dict[str, Dict[str, Any]]:
    """Maximum loop/goto iterations."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        description='Maximum number of iterations (prevents infinite loops)',
    )


def TIMEOUT_MS(
    *,
    key: str = "timeout_ms",
    default: int = 60000,
    label: str = "Timeout (ms)",
    label_key: str = "schema.field.timeout_ms",
) -> Dict[str, Dict[str, Any]]:
    """Maximum wait time in milliseconds."""
    return field(
        key,
        type="integer",
        label=label,
        label_key=label_key,
        default=default,
        min=1000,
        max=600000,
        description='Maximum wait time in milliseconds',
    )


def CANCEL_PENDING(
    *,
    key: str = "cancel_pending",
    default: bool = True,
    label: str = "Cancel Pending",
    label_key: str = "schema.field.cancel_pending",
) -> Dict[str, Dict[str, Any]]:
    """Cancel pending branches on first completion."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Cancel pending branches when using first strategy',
    )


def APPROVAL_TITLE(
    *,
    key: str = "title",
    default: str = "Approval Required",
    label: str = "Title",
    label_key: str = "schema.field.approval_title",
) -> Dict[str, Dict[str, Any]]:
    """Title displayed to approvers."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Title displayed to approvers',
    )


def APPROVAL_MODE(
    *,
    key: str = "approval_mode",
    default: str = "single",
    label: str = "Approval Mode",
    label_key: str = "schema.field.approval_mode",
) -> Dict[str, Dict[str, Any]]:
    """How approvals are counted."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["single", "all", "majority", "first"],
        description='How approvals are counted',
    )


def TIMEOUT_SECONDS(
    *,
    key: str = "timeout_seconds",
    default: int = 0,
    label: str = "Timeout (seconds)",
    label_key: str = "schema.field.timeout_seconds",
) -> Dict[str, Dict[str, Any]]:
    """Maximum wait time in seconds (0 for no timeout)."""
    return field(
        key,
        type="integer",
        label=label,
        label_key=label_key,
        default=default,
        min=0,
        description='Maximum wait time (0 for no timeout)',
    )


def INHERIT_CONTEXT(
    *,
    key: str = "inherit_context",
    default: bool = True,
    label: str = "Inherit Parent Context",
    label_key: str = "schema.field.inherit_context",
) -> Dict[str, Dict[str, Any]]:
    """Whether to inherit variables from parent workflow."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Whether to inherit variables from parent workflow',
    )


def SUBFLOW_DEFINITION(
    *,
    key: str = "subflow",
    label: str = "Subflow Definition",
    label_key: str = "schema.field.subflow_definition",
) -> Dict[str, Dict[str, Any]]:
    """Embedded workflow definition with nodes and edges."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        default={'nodes': [], 'edges': []},
        description='Embedded workflow definition with nodes and edges',
    )


# ============================================
# Object Presets
# ============================================

def INPUT_OBJECT(
    *,
    key: str = "object",
    required: bool = True,
    label: str = "Object",
    label_key: str = "schema.field.input_object",
) -> Dict[str, Dict[str, Any]]:
    """Input object/dictionary field."""
    return field(
        key,
        type="json",
        label=label,
        label_key=label_key,
        required=required,
        description='Input object/dictionary',
    )


def INPUT_OBJECTS(
    *,
    key: str = "objects",
    required: bool = True,
    label: str = "Objects",
    label_key: str = "schema.field.input_objects",
) -> Dict[str, Dict[str, Any]]:
    """Array of objects to process."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Array of objects to process',
    )


def OBJECT_KEYS(
    *,
    key: str = "keys",
    required: bool = True,
    label: str = "Keys",
    label_key: str = "schema.field.object_keys",
) -> Dict[str, Dict[str, Any]]:
    """Array of object keys to pick or omit."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Keys to pick or omit',
    )


# ============================================
# Math Presets
# ============================================

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
    )


# ============================================
# DateTime Presets
# ============================================

def DATETIME_STRING(
    *,
    key: str = "datetime_string",
    required: bool = True,
    label: str = "DateTime String",
    label_key: str = "schema.field.datetime_string",
) -> Dict[str, Dict[str, Any]]:
    """DateTime string to parse."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='DateTime string to parse',
    )


def DATETIME_INPUT(
    *,
    key: str = "datetime",
    default: str = "now",
    label: str = "DateTime",
    label_key: str = "schema.field.datetime_input",
) -> Dict[str, Dict[str, Any]]:
    """DateTime input (ISO format or 'now')."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='DateTime (ISO format or "now")',
    )


def DATETIME_FORMAT(
    *,
    key: str = "format",
    default: str = None,
    label: str = "Format",
    label_key: str = "schema.field.datetime_format",
) -> Dict[str, Dict[str, Any]]:
    """strftime/strptime format string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Format string (strftime/strptime)',
    )


def TIME_DAYS(
    *,
    key: str = "days",
    default: int = 0,
    label: str = "Days",
    label_key: str = "schema.field.time_days",
) -> Dict[str, Dict[str, Any]]:
    """Days to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Days to add/subtract',
    )


def TIME_HOURS(
    *,
    key: str = "hours",
    default: int = 0,
    label: str = "Hours",
    label_key: str = "schema.field.time_hours",
) -> Dict[str, Dict[str, Any]]:
    """Hours to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Hours to add/subtract',
    )


def TIME_MINUTES(
    *,
    key: str = "minutes",
    default: int = 0,
    label: str = "Minutes",
    label_key: str = "schema.field.time_minutes",
) -> Dict[str, Dict[str, Any]]:
    """Minutes to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Minutes to add/subtract',
    )


def TIME_SECONDS(
    *,
    key: str = "seconds",
    default: int = 0,
    label: str = "Seconds",
    label_key: str = "schema.field.time_seconds",
) -> Dict[str, Dict[str, Any]]:
    """Seconds to add or subtract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Seconds to add/subtract',
    )


# ============================================
# HuggingFace Presets
# ============================================

def HF_MODEL_ID(
    *,
    task: str,
    key: str = "model_id",
    label: str = "Model",
    label_key: str = "schema.field.hf_model_id",
) -> Dict[str, Dict[str, Any]]:
    """HuggingFace installed model selector with task filter."""
    return field(
        key,
        type="installed_model",
        label=label,
        label_key=label_key,
        required=True,
        task=task,
    )


def HF_PROMPT(
    *,
    key: str = "prompt",
    required: bool = True,
    label: str = "Prompt",
    label_key: str = "schema.field.hf_prompt",
) -> Dict[str, Dict[str, Any]]:
    """Text prompt for LLM generation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        multiline=True,
    )


def HF_TEXT_INPUT(
    *,
    key: str = "text",
    required: bool = True,
    label: str = "Text",
    label_key: str = "schema.field.hf_text_input",
) -> Dict[str, Dict[str, Any]]:
    """Text input for HuggingFace models."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        multiline=True,
    )


def HF_MAX_NEW_TOKENS(
    *,
    key: str = "max_new_tokens",
    default: int = 256,
    label: str = "Max Tokens",
    label_key: str = "schema.field.hf_max_new_tokens",
) -> Dict[str, Dict[str, Any]]:
    """Maximum new tokens to generate."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_TEMPERATURE(
    *,
    key: str = "temperature",
    default: float = 0.7,
    label: str = "Temperature",
    label_key: str = "schema.field.hf_temperature",
) -> Dict[str, Dict[str, Any]]:
    """Sampling temperature for generation."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_TOP_P(
    *,
    key: str = "top_p",
    default: float = 0.95,
    label: str = "Top P",
    label_key: str = "schema.field.hf_top_p",
) -> Dict[str, Dict[str, Any]]:
    """Nucleus sampling probability."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_DO_SAMPLE(
    *,
    key: str = "do_sample",
    default: bool = True,
    label: str = "Do Sample",
    label_key: str = "schema.field.hf_do_sample",
) -> Dict[str, Dict[str, Any]]:
    """Enable sampling for generation."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_MAX_LENGTH(
    *,
    key: str = "max_length",
    default: int = 130,
    label: str = "Max Length",
    label_key: str = "schema.field.hf_max_length",
) -> Dict[str, Dict[str, Any]]:
    """Maximum output length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_MIN_LENGTH(
    *,
    key: str = "min_length",
    default: int = 30,
    label: str = "Min Length",
    label_key: str = "schema.field.hf_min_length",
) -> Dict[str, Dict[str, Any]]:
    """Minimum output length."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_TOP_K(
    *,
    key: str = "top_k",
    default: int = 5,
    label: str = "Top K",
    label_key: str = "schema.field.hf_top_k",
) -> Dict[str, Dict[str, Any]]:
    """Number of top results to return."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
    )


def HF_SOURCE_LANG(
    *,
    key: str = "source_lang",
    label: str = "Source Language",
    label_key: str = "schema.field.hf_source_lang",
) -> Dict[str, Dict[str, Any]]:
    """Source language code for translation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
    )


def HF_TARGET_LANG(
    *,
    key: str = "target_lang",
    label: str = "Target Language",
    label_key: str = "schema.field.hf_target_lang",
) -> Dict[str, Dict[str, Any]]:
    """Target language code for translation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
    )


def HF_AUDIO_PATH(
    *,
    key: str = "audio_path",
    label: str = "Audio File",
    label_key: str = "schema.field.hf_audio_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to audio file."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=True,
    )


def HF_IMAGE_PATH(
    *,
    key: str = "image_path",
    label: str = "Image Path",
    label_key: str = "schema.field.hf_image_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to image file."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=True,
    )


def HF_LANGUAGE(
    *,
    key: str = "language",
    label: str = "Language",
    label_key: str = "schema.field.hf_language",
) -> Dict[str, Dict[str, Any]]:
    """Language code for speech recognition."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Language code (e.g., "en", "zh"). Leave empty for auto-detection.',
    )


def HF_RETURN_TIMESTAMPS(
    *,
    key: str = "return_timestamps",
    default: bool = False,
    label: str = "Return Timestamps",
    label_key: str = "schema.field.hf_return_timestamps",
) -> Dict[str, Dict[str, Any]]:
    """Include timestamps in output."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
    )


def HF_NORMALIZE(
    *,
    key: str = "normalize",
    default: bool = True,
    label: str = "Normalize",
    label_key: str = "schema.field.hf_normalize",
) -> Dict[str, Dict[str, Any]]:
    """Normalize embedding vectors."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
    )


# ============================================
# Analysis/HTML Presets
# ============================================

def HTML_CONTENT(
    *,
    key: str = "html",
    required: bool = True,
    label: str = "HTML",
    label_key: str = "schema.field.html_content",
) -> Dict[str, Dict[str, Any]]:
    """HTML content to analyze."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='HTML content to analyze',
    )


# ============================================
# Database Presets
# ============================================

def DB_TYPE(
    *,
    key: str = "database_type",
    default: str = "postgresql",
    label: str = "Database Type",
    label_key: str = "schema.field.db_type",
) -> Dict[str, Dict[str, Any]]:
    """Database type selector."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["postgresql", "mysql", "sqlite"],
    )


def DB_CONNECTION_STRING(
    *,
    key: str = "connection_string",
    label: str = "Connection String",
    label_key: str = "schema.field.db_connection_string",
) -> Dict[str, Dict[str, Any]]:
    """Database connection string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        secret=True,
        description='Database connection string',
    )


def DB_HOST(
    *,
    key: str = "host",
    label: str = "Host",
    label_key: str = "schema.field.db_host",
) -> Dict[str, Dict[str, Any]]:
    """Database host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Database host',
    )


def DB_PORT(
    *,
    key: str = "port",
    default: int = None,
    label: str = "Port",
    label_key: str = "schema.field.db_port",
) -> Dict[str, Dict[str, Any]]:
    """Database port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Database port',
    )


def DB_NAME(
    *,
    key: str = "database",
    label: str = "Database Name",
    label_key: str = "schema.field.db_name",
) -> Dict[str, Dict[str, Any]]:
    """Database name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Database name',
    )


def DB_USER(
    *,
    key: str = "user",
    label: str = "Username",
    label_key: str = "schema.field.db_user",
) -> Dict[str, Dict[str, Any]]:
    """Database username."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Database username',
    )


def DB_PASSWORD(
    *,
    key: str = "password",
    label: str = "Password",
    label_key: str = "schema.field.db_password",
) -> Dict[str, Dict[str, Any]]:
    """Database password."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        secret=True,
        description='Database password',
    )


def DB_TABLE(
    *,
    key: str = "table",
    required: bool = True,
    label: str = "Table Name",
    label_key: str = "schema.field.db_table",
) -> Dict[str, Dict[str, Any]]:
    """Database table name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Name of the table',
    )


def SQL_QUERY(
    *,
    key: str = "query",
    required: bool = True,
    label: str = "SQL Query",
    label_key: str = "schema.field.sql_query",
    placeholder: str = "SELECT * FROM users WHERE active = true",
) -> Dict[str, Dict[str, Any]]:
    """SQL query to execute."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        multiline=True,
        description='SQL query to execute',
    )


def QUERY_PARAMS(
    *,
    key: str = "params",
    label: str = "Query Parameters",
    label_key: str = "schema.field.query_params",
) -> Dict[str, Dict[str, Any]]:
    """Parameters for parameterized queries."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        default=[],
        description='Parameters for parameterized queries (prevents SQL injection)',
    )


def FETCH_MODE(
    *,
    key: str = "fetch",
    default: str = "all",
    label: str = "Fetch Mode",
    label_key: str = "schema.field.fetch_mode",
) -> Dict[str, Dict[str, Any]]:
    """How to fetch query results."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["all", "one", "none"],
        description='How to fetch results: all, one, or none (for INSERT/UPDATE)',
    )


def DB_DATA(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.db_data",
) -> Dict[str, Dict[str, Any]]:
    """Data for insert/update operations."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='Data to insert or update',
    )


def WHERE_CONDITIONS(
    *,
    key: str = "where",
    required: bool = True,
    label: str = "Where Conditions",
    label_key: str = "schema.field.where_conditions",
) -> Dict[str, Dict[str, Any]]:
    """WHERE conditions for update/delete."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='WHERE conditions (column: value for equality)',
    )


def RETURNING_COLUMNS(
    *,
    key: str = "returning",
    label: str = "Returning Columns",
    label_key: str = "schema.field.returning_columns",
) -> Dict[str, Dict[str, Any]]:
    """Columns to return after insert (PostgreSQL)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Columns to return after insert (PostgreSQL)',
    )


# ============================================
# Redis Presets
# ============================================

def REDIS_KEY(
    *,
    key: str = "key",
    required: bool = True,
    label: str = "Key",
    label_key: str = "schema.field.redis_key",
) -> Dict[str, Dict[str, Any]]:
    """Redis key."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Redis key',
    )


def REDIS_VALUE(
    *,
    key: str = "value",
    required: bool = True,
    label: str = "Value",
    label_key: str = "schema.field.redis_value",
) -> Dict[str, Dict[str, Any]]:
    """Value to store in Redis."""
    return field(
        key,
        type="any",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to store',
    )


def REDIS_TTL(
    *,
    key: str = "ttl",
    label: str = "TTL (seconds)",
    label_key: str = "schema.field.redis_ttl",
) -> Dict[str, Dict[str, Any]]:
    """Time to live in seconds."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=False,
        description='Time to live in seconds (optional)',
    )


def REDIS_HOST(
    *,
    key: str = "host",
    label: str = "Host",
    label_key: str = "schema.field.redis_host",
    placeholder: str = "${env.REDIS_HOST}",
) -> Dict[str, Dict[str, Any]]:
    """Redis host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        description='Redis host (from env.REDIS_HOST or explicit)',
    )


def REDIS_PORT(
    *,
    key: str = "port",
    default: int = 6379,
    label: str = "Port",
    label_key: str = "schema.field.redis_port",
) -> Dict[str, Dict[str, Any]]:
    """Redis port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Redis port',
    )


def REDIS_DB(
    *,
    key: str = "db",
    default: int = 0,
    label: str = "Database",
    label_key: str = "schema.field.redis_db",
) -> Dict[str, Dict[str, Any]]:
    """Redis database number."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Redis database number',
    )


# ============================================
# MongoDB Presets
# ============================================

def MONGO_CONNECTION_STRING(
    *,
    key: str = "connection_string",
    label: str = "Connection String",
    label_key: str = "schema.field.mongo_connection_string",
    placeholder: str = "${env.MONGODB_URL}",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB connection string."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        placeholder=placeholder,
        secret=True,
        description='MongoDB connection string (defaults to env.MONGODB_URL)',
    )


def MONGO_DATABASE(
    *,
    key: str = "database",
    required: bool = True,
    label: str = "Database",
    label_key: str = "schema.field.mongo_database",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB database name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Database name',
    )


def MONGO_COLLECTION(
    *,
    key: str = "collection",
    required: bool = True,
    label: str = "Collection",
    label_key: str = "schema.field.mongo_collection",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB collection name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Collection name',
    )


def MONGO_FILTER(
    *,
    key: str = "filter",
    label: str = "Filter",
    label_key: str = "schema.field.mongo_filter",
) -> Dict[str, Dict[str, Any]]:
    """MongoDB query filter."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        default={},
        description='MongoDB query filter (empty object {} returns all)',
    )


def MONGO_PROJECTION(
    *,
    key: str = "projection",
    label: str = "Projection",
    label_key: str = "schema.field.mongo_projection",
) -> Dict[str, Dict[str, Any]]:
    """Fields to include/exclude in results."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Fields to include/exclude in results',
    )


def MONGO_LIMIT(
    *,
    key: str = "limit",
    default: int = 100,
    label: str = "Limit",
    label_key: str = "schema.field.mongo_limit",
) -> Dict[str, Dict[str, Any]]:
    """Maximum number of documents to return."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        min=1,
        max=10000,
        description='Maximum number of documents to return',
    )


def MONGO_SORT(
    *,
    key: str = "sort",
    label: str = "Sort",
    label_key: str = "schema.field.mongo_sort",
) -> Dict[str, Dict[str, Any]]:
    """Sort order (1 for ascending, -1 for descending)."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Sort order (1 for ascending, -1 for descending)',
    )


def MONGO_DOCUMENT(
    *,
    key: str = "document",
    label: str = "Document",
    label_key: str = "schema.field.mongo_document",
) -> Dict[str, Dict[str, Any]]:
    """Document to insert (for single insert)."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        description='Document to insert (for single insert)',
    )


def MONGO_DOCUMENTS(
    *,
    key: str = "documents",
    label: str = "Documents",
    label_key: str = "schema.field.mongo_documents",
) -> Dict[str, Dict[str, Any]]:
    """Array of documents to insert (for bulk insert)."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Array of documents to insert (for bulk insert)',
    )


# ============================================
# Document Common Presets
# ============================================

def DOC_INPUT_PATH(
    *,
    key: str = "input_path",
    required: bool = True,
    label: str = "Input Path",
    label_key: str = "schema.field.doc_input_path",
    placeholder: str = "/path/to/document",
) -> Dict[str, Dict[str, Any]]:
    """Input document file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path to the input document',
    )


def DOC_OUTPUT_PATH(
    *,
    key: str = "output_path",
    required: bool = False,
    label: str = "Output Path",
    label_key: str = "schema.field.doc_output_path",
    placeholder: str = "/path/to/output",
) -> Dict[str, Dict[str, Any]]:
    """Output document file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path for the output document',
    )


def DOC_PAGES(
    *,
    key: str = "pages",
    default: str = "all",
    label: str = "Pages",
    label_key: str = "schema.field.doc_pages",
) -> Dict[str, Dict[str, Any]]:
    """Page range to process."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Page range (e.g., "1-5", "1,3,5", or "all")',
    )


def DOC_EXTRACT_TABLES(
    *,
    key: str = "extract_tables",
    default: bool = False,
    label: str = "Extract Tables",
    label_key: str = "schema.field.doc_extract_tables",
) -> Dict[str, Dict[str, Any]]:
    """Extract tables from document."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Extract tables as structured data',
    )


def DOC_EXTRACT_IMAGES(
    *,
    key: str = "extract_images",
    default: bool = False,
    label: str = "Extract Images",
    label_key: str = "schema.field.doc_extract_images",
) -> Dict[str, Dict[str, Any]]:
    """Extract embedded images."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Extract embedded images',
    )


def DOC_PRESERVE_FORMATTING(
    *,
    key: str = "preserve_formatting",
    default: bool = True,
    label: str = "Preserve Formatting",
    label_key: str = "schema.field.doc_preserve_formatting",
) -> Dict[str, Dict[str, Any]]:
    """Preserve document formatting."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Preserve basic formatting',
    )


def DOC_IMAGES_OUTPUT_DIR(
    *,
    key: str = "images_output_dir",
    label: str = "Images Output Directory",
    label_key: str = "schema.field.doc_images_output_dir",
) -> Dict[str, Dict[str, Any]]:
    """Directory to save extracted images."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Directory to save extracted images',
    )


# ============================================
# Excel Presets
# ============================================

def EXCEL_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "Excel Path",
    label_key: str = "schema.field.excel_path",
    placeholder: str = "/path/to/file.xlsx",
) -> Dict[str, Dict[str, Any]]:
    """Excel file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path to the Excel file',
    )


def EXCEL_SHEET(
    *,
    key: str = "sheet",
    label: str = "Sheet Name",
    label_key: str = "schema.field.excel_sheet",
) -> Dict[str, Dict[str, Any]]:
    """Excel sheet name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Sheet name (default: first sheet)',
    )


def EXCEL_HEADER_ROW(
    *,
    key: str = "header_row",
    default: int = 1,
    label: str = "Header Row",
    label_key: str = "schema.field.excel_header_row",
) -> Dict[str, Dict[str, Any]]:
    """Header row number (1-based)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Row number for headers (1-based, 0 for no headers)',
    )


def EXCEL_RANGE(
    *,
    key: str = "range",
    label: str = "Cell Range",
    label_key: str = "schema.field.excel_range",
) -> Dict[str, Dict[str, Any]]:
    """Excel cell range."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Cell range to read (e.g., "A1:D10")',
    )


def EXCEL_AS_DICT(
    *,
    key: str = "as_dict",
    default: bool = True,
    label: str = "Return as Dict",
    label_key: str = "schema.field.excel_as_dict",
) -> Dict[str, Dict[str, Any]]:
    """Return rows as dictionaries."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Return rows as dictionaries (using headers as keys)',
    )


def EXCEL_DATA(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.excel_data",
) -> Dict[str, Dict[str, Any]]:
    """Data array for Excel."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Data to write (array of arrays or array of objects)',
    )


def EXCEL_HEADERS(
    *,
    key: str = "headers",
    label: str = "Headers",
    label_key: str = "schema.field.excel_headers",
) -> Dict[str, Dict[str, Any]]:
    """Column headers."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        description='Column headers (auto-detected from objects if not provided)',
    )


def EXCEL_SHEET_NAME(
    *,
    key: str = "sheet_name",
    default: str = "Sheet1",
    label: str = "Sheet Name",
    label_key: str = "schema.field.excel_sheet_name",
) -> Dict[str, Dict[str, Any]]:
    """Excel sheet name for writing."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Name of the worksheet',
    )


def EXCEL_AUTO_WIDTH(
    *,
    key: str = "auto_width",
    default: bool = True,
    label: str = "Auto Width",
    label_key: str = "schema.field.excel_auto_width",
) -> Dict[str, Dict[str, Any]]:
    """Auto-adjust column widths."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Automatically adjust column widths',
    )


# ============================================
# PDF Presets
# ============================================

def PDF_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "PDF Path",
    label_key: str = "schema.field.pdf_path",
    placeholder: str = "/path/to/document.pdf",
) -> Dict[str, Dict[str, Any]]:
    """PDF file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        placeholder=placeholder,
        description='Path to the PDF file',
    )


def PDF_CONTENT(
    *,
    key: str = "content",
    required: bool = True,
    label: str = "Content",
    label_key: str = "schema.field.pdf_content",
) -> Dict[str, Dict[str, Any]]:
    """HTML or text content for PDF."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='HTML or text content to convert to PDF',
    )


def PDF_TITLE(
    *,
    key: str = "title",
    label: str = "Title",
    label_key: str = "schema.field.pdf_title",
) -> Dict[str, Dict[str, Any]]:
    """Document title metadata."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Document title (metadata)',
    )


def PDF_AUTHOR(
    *,
    key: str = "author",
    label: str = "Author",
    label_key: str = "schema.field.pdf_author",
) -> Dict[str, Dict[str, Any]]:
    """Document author metadata."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Document author (metadata)',
    )


def PDF_PAGE_SIZE(
    *,
    key: str = "page_size",
    default: str = "A4",
    label: str = "Page Size",
    label_key: str = "schema.field.pdf_page_size",
) -> Dict[str, Dict[str, Any]]:
    """Page size format."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["A4", "Letter", "Legal", "A3", "A5"],
        description='Page size format',
    )


def PDF_ORIENTATION(
    *,
    key: str = "orientation",
    default: str = "portrait",
    label: str = "Orientation",
    label_key: str = "schema.field.pdf_orientation",
) -> Dict[str, Dict[str, Any]]:
    """Page orientation."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["portrait", "landscape"],
        description='Page orientation',
    )


def PDF_MARGIN(
    *,
    key: str = "margin",
    default: int = 20,
    label: str = "Margin (mm)",
    label_key: str = "schema.field.pdf_margin",
) -> Dict[str, Dict[str, Any]]:
    """Page margin in millimeters."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Page margin in millimeters',
    )


def PDF_HEADER(
    *,
    key: str = "header",
    label: str = "Header",
    label_key: str = "schema.field.pdf_header",
) -> Dict[str, Dict[str, Any]]:
    """Header text for each page."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Header text for each page',
    )


def PDF_FOOTER(
    *,
    key: str = "footer",
    label: str = "Footer",
    label_key: str = "schema.field.pdf_footer",
) -> Dict[str, Dict[str, Any]]:
    """Footer text for each page."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=False,
        description='Footer text for each page',
    )


def PDF_TEMPLATE(
    *,
    key: str = "template",
    required: bool = True,
    label: str = "Template PDF",
    label_key: str = "schema.field.pdf_template",
) -> Dict[str, Dict[str, Any]]:
    """PDF template file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Path to the PDF template file',
    )


def PDF_FORM_FIELDS(
    *,
    key: str = "fields",
    label: str = "Form Fields",
    label_key: str = "schema.field.pdf_form_fields",
) -> Dict[str, Dict[str, Any]]:
    """Form field key-value pairs."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=False,
        default={},
        description='Key-value pairs of form field names and values',
    )


def PDF_IMAGES(
    *,
    key: str = "images",
    label: str = "Images",
    label_key: str = "schema.field.pdf_images",
) -> Dict[str, Dict[str, Any]]:
    """Images to insert into PDF."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=False,
        default=[],
        description='List of images to insert with position info',
    )


def PDF_FLATTEN(
    *,
    key: str = "flatten",
    default: bool = True,
    label: str = "Flatten Form",
    label_key: str = "schema.field.pdf_flatten",
) -> Dict[str, Dict[str, Any]]:
    """Flatten form fields."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Flatten form fields (make them non-editable)',
    )


# ============================================
# Word Presets
# ============================================

def WORD_FILE_PATH(
    *,
    key: str = "file_path",
    required: bool = True,
    label: str = "File Path",
    label_key: str = "schema.field.word_file_path",
) -> Dict[str, Dict[str, Any]]:
    """Word document file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Path to the Word document (.docx)',
    )


def DOC_CONVERSION_METHOD(
    *,
    key: str = "method",
    default: str = "auto",
    label: str = "Conversion Method",
    label_key: str = "schema.field.doc_conversion_method",
) -> Dict[str, Dict[str, Any]]:
    """Document conversion method."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        options=[
            {"value": "auto", "label": "Auto (best available)"},
            {"value": "libreoffice", "label": "LibreOffice"},
            {"value": "docx2pdf", "label": "docx2pdf (Windows/Mac)"},
        ],
        description='Method to use for conversion',
    )


# ============================================
# Search Presets
# ============================================

def SEARCH_KEYWORD(
    *,
    key: str = "keyword",
    required: bool = True,
    placeholder: str = "search query",
    label: str = "Keyword",
    label_key: str = "schema.field.search_keyword",
) -> Dict[str, Dict[str, Any]]:
    """Search keyword."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Search keyword or query',
    )


def SEARCH_LIMIT(
    *,
    key: str = "limit",
    default: int = 10,
    min_val: int = 1,
    max_val: int = 100,
    label: str = "Limit",
    label_key: str = "schema.field.search_limit",
) -> Dict[str, Dict[str, Any]]:
    """Search result limit."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        required=False,
        description='Maximum number of results',
    )


# ============================================
# Webhook Presets
# ============================================

def WEBHOOK_URL(
    *,
    key: str = "url",
    required: bool = True,
    placeholder: str = "https://example.com/webhook",
    label: str = "Webhook URL",
    label_key: str = "schema.field.webhook_url",
) -> Dict[str, Dict[str, Any]]:
    """Webhook URL."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Target webhook URL',
    )


def WEBHOOK_PAYLOAD(
    *,
    key: str = "payload",
    required: bool = False,
    label: str = "Payload",
    label_key: str = "schema.field.webhook_payload",
) -> Dict[str, Dict[str, Any]]:
    """Webhook payload."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='JSON payload to send',
    )


def WEBHOOK_AUTH_TOKEN(
    *,
    key: str = "auth_token",
    required: bool = False,
    label: str = "Auth Token",
    label_key: str = "schema.field.webhook_auth_token",
) -> Dict[str, Dict[str, Any]]:
    """Webhook bearer auth token."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        secret=True,
        description='Bearer token for authorization',
    )


# ============================================
# Email Presets
# ============================================

def EMAIL_TO(
    *,
    key: str = "to",
    required: bool = True,
    placeholder: str = "recipient@example.com",
    label: str = "To",
    label_key: str = "schema.field.email_to",
) -> Dict[str, Dict[str, Any]]:
    """Email recipient."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Recipient email address(es), comma-separated for multiple',
    )


def EMAIL_SUBJECT(
    *,
    key: str = "subject",
    required: bool = True,
    label: str = "Subject",
    label_key: str = "schema.field.email_subject",
) -> Dict[str, Dict[str, Any]]:
    """Email subject."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Email subject line',
    )


def EMAIL_BODY(
    *,
    key: str = "body",
    required: bool = True,
    label: str = "Body",
    label_key: str = "schema.field.email_body",
) -> Dict[str, Dict[str, Any]]:
    """Email body content."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        multiline=True,
        description='Email body content',
    )


def EMAIL_HTML(
    *,
    key: str = "html",
    default: bool = False,
    label: str = "HTML Format",
    label_key: str = "schema.field.email_html",
) -> Dict[str, Dict[str, Any]]:
    """Send as HTML email."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Send as HTML email',
    )


def EMAIL_FROM(
    *,
    key: str = "from_email",
    required: bool = False,
    label: str = "From",
    label_key: str = "schema.field.email_from",
) -> Dict[str, Dict[str, Any]]:
    """Sender email address."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Sender email (uses SMTP_FROM_EMAIL env if not provided)',
    )


def EMAIL_CC(
    *,
    key: str = "cc",
    required: bool = False,
    label: str = "CC",
    label_key: str = "schema.field.email_cc",
) -> Dict[str, Dict[str, Any]]:
    """Email CC recipients."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='CC recipients, comma-separated',
    )


def EMAIL_BCC(
    *,
    key: str = "bcc",
    required: bool = False,
    label: str = "BCC",
    label_key: str = "schema.field.email_bcc",
) -> Dict[str, Dict[str, Any]]:
    """Email BCC recipients."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='BCC recipients, comma-separated',
    )


def EMAIL_ATTACHMENTS(
    *,
    key: str = "attachments",
    required: bool = False,
    label: str = "Attachments",
    label_key: str = "schema.field.email_attachments",
) -> Dict[str, Dict[str, Any]]:
    """Email file attachments."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        default=[],
        required=required,
        description='List of file paths to attach',
    )


def SMTP_HOST(
    *,
    key: str = "smtp_host",
    required: bool = False,
    placeholder: str = "${env.SMTP_HOST}",
    label: str = "SMTP Host",
    label_key: str = "schema.field.smtp_host",
) -> Dict[str, Dict[str, Any]]:
    """SMTP server host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='SMTP server host (uses SMTP_HOST env if not provided)',
    )


def SMTP_PORT(
    *,
    key: str = "smtp_port",
    default: int = 587,
    label: str = "SMTP Port",
    label_key: str = "schema.field.smtp_port",
) -> Dict[str, Dict[str, Any]]:
    """SMTP server port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='SMTP server port (uses SMTP_PORT env if not provided)',
    )


def SMTP_USER(
    *,
    key: str = "smtp_user",
    required: bool = False,
    label: str = "SMTP User",
    label_key: str = "schema.field.smtp_user",
) -> Dict[str, Dict[str, Any]]:
    """SMTP username."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='SMTP username (uses SMTP_USER env if not provided)',
    )


def SMTP_PASSWORD(
    *,
    key: str = "smtp_password",
    required: bool = False,
    label: str = "SMTP Password",
    label_key: str = "schema.field.smtp_password",
) -> Dict[str, Dict[str, Any]]:
    """SMTP password."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        secret=True,
        description='SMTP password (uses SMTP_PASSWORD env if not provided)',
    )


def USE_TLS(
    *,
    key: str = "use_tls",
    default: bool = True,
    label: str = "Use TLS",
    label_key: str = "schema.field.use_tls",
) -> Dict[str, Dict[str, Any]]:
    """Use TLS encryption."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Use TLS encryption',
    )


def IMAP_HOST(
    *,
    key: str = "imap_host",
    required: bool = False,
    placeholder: str = "${env.IMAP_HOST}",
    label: str = "IMAP Host",
    label_key: str = "schema.field.imap_host",
) -> Dict[str, Dict[str, Any]]:
    """IMAP server host."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='IMAP server host',
    )


def IMAP_PORT(
    *,
    key: str = "imap_port",
    default: int = 993,
    label: str = "IMAP Port",
    label_key: str = "schema.field.imap_port",
) -> Dict[str, Dict[str, Any]]:
    """IMAP server port."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='IMAP server port',
    )


def IMAP_USER(
    *,
    key: str = "imap_user",
    required: bool = False,
    label: str = "IMAP User",
    label_key: str = "schema.field.imap_user",
) -> Dict[str, Dict[str, Any]]:
    """IMAP username."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='IMAP username',
    )


def IMAP_PASSWORD(
    *,
    key: str = "imap_password",
    required: bool = False,
    label: str = "IMAP Password",
    label_key: str = "schema.field.imap_password",
) -> Dict[str, Dict[str, Any]]:
    """IMAP password."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        secret=True,
        description='IMAP password',
    )


def EMAIL_FOLDER(
    *,
    key: str = "folder",
    default: str = "INBOX",
    label: str = "Folder",
    label_key: str = "schema.field.email_folder",
) -> Dict[str, Dict[str, Any]]:
    """Email folder/mailbox."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Mailbox folder to read from',
    )


def EMAIL_LIMIT(
    *,
    key: str = "limit",
    default: int = 10,
    label: str = "Limit",
    label_key: str = "schema.field.email_limit",
) -> Dict[str, Dict[str, Any]]:
    """Email fetch limit."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Maximum number of emails to fetch',
    )


def EMAIL_UNREAD_ONLY(
    *,
    key: str = "unread_only",
    default: bool = False,
    label: str = "Unread Only",
    label_key: str = "schema.field.email_unread_only",
) -> Dict[str, Dict[str, Any]]:
    """Only fetch unread emails."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Only fetch unread emails',
    )


def EMAIL_SINCE_DATE(
    *,
    key: str = "since_date",
    required: bool = False,
    label: str = "Since Date",
    label_key: str = "schema.field.email_since_date",
) -> Dict[str, Dict[str, Any]]:
    """Fetch emails since date."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Fetch emails since this date (YYYY-MM-DD)',
    )


def EMAIL_FROM_FILTER(
    *,
    key: str = "from_filter",
    required: bool = False,
    label: str = "From Filter",
    label_key: str = "schema.field.email_from_filter",
) -> Dict[str, Dict[str, Any]]:
    """Filter by sender email."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Filter by sender email address',
    )


def EMAIL_SUBJECT_FILTER(
    *,
    key: str = "subject_filter",
    required: bool = False,
    label: str = "Subject Filter",
    label_key: str = "schema.field.email_subject_filter",
) -> Dict[str, Dict[str, Any]]:
    """Filter by subject."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Filter by subject (contains)',
    )


# ============================================
# Slack Presets
# ============================================

def SLACK_MESSAGE(
    *,
    key: str = "message",
    required: bool = True,
    label: str = "Message",
    label_key: str = "schema.field.slack_message",
) -> Dict[str, Dict[str, Any]]:
    """Slack message text."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Message text to send',
    )


def SLACK_WEBHOOK_URL(
    *,
    key: str = "webhook_url",
    required: bool = False,
    placeholder: str = "${env.SLACK_WEBHOOK_URL}",
    label: str = "Webhook URL",
    label_key: str = "schema.field.slack_webhook_url",
) -> Dict[str, Dict[str, Any]]:
    """Slack webhook URL."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        secret=True,
        description='Slack incoming webhook URL',
    )


def SLACK_CHANNEL(
    *,
    key: str = "channel",
    required: bool = False,
    label: str = "Channel",
    label_key: str = "schema.field.slack_channel",
) -> Dict[str, Dict[str, Any]]:
    """Slack channel override."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Override channel (optional)',
    )


def SLACK_USERNAME(
    *,
    key: str = "username",
    required: bool = False,
    label: str = "Username",
    label_key: str = "schema.field.slack_username",
) -> Dict[str, Dict[str, Any]]:
    """Slack bot username override."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Override bot username',
    )


def SLACK_ICON_EMOJI(
    *,
    key: str = "icon_emoji",
    required: bool = False,
    placeholder: str = ":robot_face:",
    label: str = "Icon Emoji",
    label_key: str = "schema.field.slack_icon_emoji",
) -> Dict[str, Dict[str, Any]]:
    """Slack bot icon emoji."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Emoji to use as icon (e.g., :robot_face:)',
    )


def SLACK_BLOCKS(
    *,
    key: str = "blocks",
    required: bool = False,
    label: str = "Blocks",
    label_key: str = "schema.field.slack_blocks",
) -> Dict[str, Dict[str, Any]]:
    """Slack Block Kit blocks."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Slack Block Kit blocks for rich formatting',
    )


def SLACK_ATTACHMENTS(
    *,
    key: str = "attachments",
    required: bool = False,
    label: str = "Attachments",
    label_key: str = "schema.field.slack_attachments",
) -> Dict[str, Dict[str, Any]]:
    """Slack message attachments."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Message attachments',
    )


# ============================================
# Browser Extended Presets
# ============================================

def SCROLL_DIRECTION(
    *,
    key: str = "direction",
    default: str = "down",
    label: str = "Direction",
    label_key: str = "schema.field.scroll_direction",
) -> Dict[str, Dict[str, Any]]:
    """Scroll direction."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["up", "down", "left", "right"],
        description='Scroll direction (up, down, left, right)',
    )


def SCROLL_AMOUNT(
    *,
    key: str = "amount",
    default: int = 500,
    label: str = "Amount (pixels)",
    label_key: str = "schema.field.scroll_amount",
) -> Dict[str, Dict[str, Any]]:
    """Scroll amount in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Pixels to scroll (ignored if selector is provided)',
    )


def SCROLL_BEHAVIOR(
    *,
    key: str = "behavior",
    default: str = "smooth",
    label: str = "Behavior",
    label_key: str = "schema.field.scroll_behavior",
) -> Dict[str, Dict[str, Any]]:
    """Scroll behavior."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["smooth", "instant"],
        description='Scroll behavior (smooth or instant)',
    )


def SELECT_VALUE(
    *,
    key: str = "value",
    required: bool = False,
    label: str = "Value",
    label_key: str = "schema.field.select_value",
) -> Dict[str, Dict[str, Any]]:
    """Select option value."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Option value attribute to select',
    )


def SELECT_LABEL(
    *,
    key: str = "label",
    required: bool = False,
    label: str = "Label",
    label_key: str = "schema.field.select_label",
) -> Dict[str, Dict[str, Any]]:
    """Select option label."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Option text content to select (alternative to value)',
    )


def SELECT_INDEX(
    *,
    key: str = "index",
    required: bool = False,
    label: str = "Index",
    label_key: str = "schema.field.select_index",
) -> Dict[str, Dict[str, Any]]:
    """Select option index."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='Option index to select (0-based)',
    )


def BROWSER_ACTION(
    *,
    key: str = "action",
    required: bool = True,
    options: List[str] = None,
    label: str = "Action",
    label_key: str = "schema.field.browser_action",
) -> Dict[str, Dict[str, Any]]:
    """Browser action type."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        enum=options or ["get", "set", "clear"],
        description='Action to perform',
    )


def COOKIE_NAME(
    *,
    key: str = "name",
    required: bool = False,
    label: str = "Cookie Name",
    label_key: str = "schema.field.cookie_name",
) -> Dict[str, Dict[str, Any]]:
    """Cookie name."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Name of the cookie',
    )


def COOKIE_VALUE(
    *,
    key: str = "value",
    required: bool = False,
    label: str = "Cookie Value",
    label_key: str = "schema.field.cookie_value",
) -> Dict[str, Dict[str, Any]]:
    """Cookie value."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Value of the cookie',
    )


def COOKIE_DOMAIN(
    *,
    key: str = "domain",
    required: bool = False,
    label: str = "Domain",
    label_key: str = "schema.field.cookie_domain",
) -> Dict[str, Dict[str, Any]]:
    """Cookie domain."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Cookie domain',
    )


def COOKIE_PATH(
    *,
    key: str = "path",
    default: str = "/",
    label: str = "Path",
    label_key: str = "schema.field.cookie_path",
) -> Dict[str, Dict[str, Any]]:
    """Cookie path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Cookie path',
    )


def COOKIE_SECURE(
    *,
    key: str = "secure",
    default: bool = False,
    label: str = "Secure",
    label_key: str = "schema.field.cookie_secure",
) -> Dict[str, Dict[str, Any]]:
    """Cookie secure flag."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Whether cookie is secure (HTTPS only)',
    )


def COOKIE_HTTP_ONLY(
    *,
    key: str = "httpOnly",
    default: bool = False,
    label: str = "HTTP Only",
    label_key: str = "schema.field.cookie_http_only",
) -> Dict[str, Dict[str, Any]]:
    """Cookie HTTP only flag."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Whether cookie is HTTP only',
    )


def COOKIE_EXPIRES(
    *,
    key: str = "expires",
    required: bool = False,
    label: str = "Expires",
    label_key: str = "schema.field.cookie_expires",
) -> Dict[str, Dict[str, Any]]:
    """Cookie expiration timestamp."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        description='Cookie expiration time (Unix timestamp)',
    )


def STORAGE_TYPE(
    *,
    key: str = "type",
    default: str = "local",
    label: str = "Storage Type",
    label_key: str = "schema.field.storage_type",
) -> Dict[str, Dict[str, Any]]:
    """Browser storage type."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["local", "session"],
        description='Type of storage to access',
    )


def STORAGE_KEY(
    *,
    key: str = "key",
    required: bool = False,
    label: str = "Key",
    label_key: str = "schema.field.storage_key",
) -> Dict[str, Dict[str, Any]]:
    """Storage key."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Storage key',
    )


def STORAGE_VALUE(
    *,
    key: str = "value",
    required: bool = False,
    label: str = "Value",
    label_key: str = "schema.field.storage_value",
) -> Dict[str, Dict[str, Any]]:
    """Storage value."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Value to store',
    )


def UPLOAD_FILE_PATH(
    *,
    key: str = "file_path",
    required: bool = True,
    placeholder: str = "/path/to/file.pdf",
    label: str = "File Path",
    label_key: str = "schema.field.upload_file_path",
) -> Dict[str, Dict[str, Any]]:
    """File path to upload."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Local path to the file to upload',
    )


def DOWNLOAD_SAVE_PATH(
    *,
    key: str = "save_path",
    required: bool = True,
    placeholder: str = "/path/to/save/file.pdf",
    label: str = "Save Path",
    label_key: str = "schema.field.download_save_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to save downloaded file."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Path where to save the downloaded file',
    )


def DIALOG_ACTION(
    *,
    key: str = "action",
    required: bool = True,
    label: str = "Action",
    label_key: str = "schema.field.dialog_action",
) -> Dict[str, Dict[str, Any]]:
    """Dialog action."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        enum=["accept", "dismiss", "listen"],
        description='How to handle the dialog',
    )


def DIALOG_PROMPT_TEXT(
    *,
    key: str = "prompt_text",
    required: bool = False,
    label: str = "Prompt Text",
    label_key: str = "schema.field.dialog_prompt_text",
) -> Dict[str, Dict[str, Any]]:
    """Text to enter in prompt dialog."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        description='Text to enter in prompt dialog (for accept action)',
    )


def JS_SCRIPT(
    *,
    key: str = "script",
    required: bool = True,
    placeholder: str = "return document.title",
    label: str = "JavaScript Code",
    label_key: str = "schema.field.js_script",
) -> Dict[str, Dict[str, Any]]:
    """JavaScript code to execute."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        multiline=True,
        description='JavaScript code to execute (can use return statement)',
    )


def JS_ARGS(
    *,
    key: str = "args",
    required: bool = False,
    label: str = "Arguments",
    label_key: str = "schema.field.js_args",
) -> Dict[str, Dict[str, Any]]:
    """JavaScript function arguments."""
    return field(
        key,
        type="array",
        label=label,
        label_key=label_key,
        required=required,
        description='Arguments to pass to the script function',
    )


def KEYBOARD_KEY(
    *,
    key: str = "key",
    required: bool = True,
    placeholder: str = "Enter",
    label: str = "Key",
    label_key: str = "schema.field.keyboard_key",
) -> Dict[str, Dict[str, Any]]:
    """Keyboard key to press."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='The key to press (e.g., Enter, Escape, Tab)',
    )


def EXTRACT_FIELDS(
    *,
    key: str = "fields",
    required: bool = False,
    label: str = "Fields to Extract",
    label_key: str = "schema.field.extract_fields",
) -> Dict[str, Dict[str, Any]]:
    """Fields to extract from elements."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='Define fields to extract from each item',
    )


def EXTRACT_LIMIT(
    *,
    key: str = "limit",
    required: bool = False,
    placeholder: str = "10",
    label: str = "Limit",
    label_key: str = "schema.field.extract_limit",
) -> Dict[str, Dict[str, Any]]:
    """Limit number of items to extract."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Maximum number of items to extract',
    )


def CONSOLE_LEVEL(
    *,
    key: str = "level",
    default: str = "all",
    label: str = "Log Level",
    label_key: str = "schema.field.console_level",
) -> Dict[str, Dict[str, Any]]:
    """Console log level filter."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        enum=["all", "error", "warning", "info", "log"],
        description='Filter by log level',
    )


def CONSOLE_CLEAR_EXISTING(
    *,
    key: str = "clear_existing",
    default: bool = False,
    label: str = "Clear Existing",
    label_key: str = "schema.field.console_clear_existing",
) -> Dict[str, Dict[str, Any]]:
    """Clear existing console messages."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        required=False,
        description='Clear existing messages before capturing',
    )


# ============================================
# Image Processing Presets
# ============================================

def IMAGE_INPUT_PATH(
    *,
    key: str = "input_path",
    required: bool = True,
    label: str = "Input Path",
    label_key: str = "schema.field.image_input_path",
    placeholder: str = "/path/to/image.png",
) -> Dict[str, Dict[str, Any]]:
    """Input image file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def IMAGE_OUTPUT_PATH(
    *,
    key: str = "output_path",
    required: bool = False,
    label: str = "Output Path",
    label_key: str = "schema.field.image_output_path",
    placeholder: str = "/path/to/output.png",
) -> Dict[str, Dict[str, Any]]:
    """Output image file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
    )


def IMAGE_WIDTH(
    *,
    key: str = "width",
    required: bool = False,
    label: str = "Width",
    label_key: str = "schema.field.image_width",
    min_val: int = 1,
    max_val: int = 10000,
) -> Dict[str, Dict[str, Any]]:
    """Image width in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=min_val,
        max=max_val,
        description='Target width in pixels',
    )


def IMAGE_HEIGHT(
    *,
    key: str = "height",
    required: bool = False,
    label: str = "Height",
    label_key: str = "schema.field.image_height",
    min_val: int = 1,
    max_val: int = 10000,
) -> Dict[str, Dict[str, Any]]:
    """Image height in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=min_val,
        max=max_val,
        description='Target height in pixels',
    )


def IMAGE_SCALE(
    *,
    key: str = "scale",
    required: bool = False,
    label: str = "Scale Factor",
    label_key: str = "schema.field.image_scale",
    min_val: float = 0.01,
    max_val: float = 10.0,
) -> Dict[str, Dict[str, Any]]:
    """Image scale factor."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=min_val,
        max=max_val,
        step=0.1,
        description='Scale factor (e.g., 0.5 for half, 2.0 for double)',
    )


def IMAGE_QUALITY(
    *,
    key: str = "quality",
    default: int = 85,
    min_val: int = 1,
    max_val: int = 100,
    label: str = "Quality",
    label_key: str = "schema.field.image_quality",
) -> Dict[str, Dict[str, Any]]:
    """Image quality (1-100)."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Quality level (1-100, higher is better)',
    )


def IMAGE_FORMAT(
    *,
    key: str = "format",
    required: bool = False,
    default: str = "png",
    label: str = "Output Format",
    label_key: str = "schema.field.image_format",
) -> Dict[str, Dict[str, Any]]:
    """Image output format."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        default=default,
        enum=["jpeg", "png", "webp", "gif", "bmp", "tiff"],
        description='Output image format',
    )


def IMAGE_RESIZE_ALGORITHM(
    *,
    key: str = "algorithm",
    default: str = "lanczos",
    label: str = "Algorithm",
    label_key: str = "schema.field.image_resize_algorithm",
) -> Dict[str, Dict[str, Any]]:
    """Image resize algorithm."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        enum=["lanczos", "bilinear", "bicubic", "nearest"],
        description='Resampling algorithm',
    )


def IMAGE_MAINTAIN_ASPECT(
    *,
    key: str = "maintain_aspect",
    default: bool = True,
    label: str = "Maintain Aspect Ratio",
    label_key: str = "schema.field.image_maintain_aspect",
) -> Dict[str, Dict[str, Any]]:
    """Maintain aspect ratio when resizing."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Maintain original aspect ratio',
    )


def IMAGE_OPTIMIZE(
    *,
    key: str = "optimize",
    default: bool = True,
    label: str = "Optimize",
    label_key: str = "schema.field.image_optimize",
) -> Dict[str, Dict[str, Any]]:
    """Apply additional image optimization."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Apply additional optimization',
    )


def IMAGE_MAX_SIZE_KB(
    *,
    key: str = "max_size_kb",
    required: bool = False,
    label: str = "Max Size (KB)",
    label_key: str = "schema.field.image_max_size_kb",
) -> Dict[str, Dict[str, Any]]:
    """Target maximum file size in KB."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        required=required,
        min=1,
        description='Target maximum file size in KB',
    )


def IMAGE_RESIZE_OPTIONS(
    *,
    key: str = "resize",
    required: bool = False,
    label: str = "Resize",
    label_key: str = "schema.field.image_resize_options",
) -> Dict[str, Dict[str, Any]]:
    """Resize options object."""
    return field(
        key,
        type="object",
        label=label,
        label_key=label_key,
        required=required,
        description='Resize options: {width, height, keep_aspect}',
    )


def IMAGE_URL(
    *,
    key: str = "url",
    required: bool = True,
    label: str = "Image URL",
    label_key: str = "schema.field.image_url",
    placeholder: str = "https://example.com/image.jpg",
) -> Dict[str, Dict[str, Any]]:
    """Image URL to download."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validators.URL_HTTP,
    )


def OUTPUT_DIRECTORY(
    *,
    key: str = "output_dir",
    required: bool = False,
    default: str = "/tmp",
    label: str = "Output Directory",
    label_key: str = "schema.field.output_directory",
) -> Dict[str, Dict[str, Any]]:
    """Output directory path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        default=default,
        format="path",
    )


# QR Code Presets
def QRCODE_DATA(
    *,
    key: str = "data",
    required: bool = True,
    label: str = "Data",
    label_key: str = "schema.field.qrcode_data",
    placeholder: str = "https://example.com",
) -> Dict[str, Dict[str, Any]]:
    """Data to encode in QR code."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        description='Text, URL, or data to encode',
    )


def QRCODE_SIZE(
    *,
    key: str = "size",
    default: int = 300,
    min_val: int = 100,
    max_val: int = 2000,
    label: str = "Size",
    label_key: str = "schema.field.qrcode_size",
) -> Dict[str, Dict[str, Any]]:
    """QR code size in pixels."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Size in pixels',
    )


def QRCODE_COLOR(
    *,
    key: str = "color",
    default: str = "#000000",
    label: str = "Foreground Color",
    label_key: str = "schema.field.qrcode_color",
) -> Dict[str, Dict[str, Any]]:
    """QR code foreground color."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Color of the QR code (hex or name)',
    )


def QRCODE_BACKGROUND(
    *,
    key: str = "background",
    default: str = "#FFFFFF",
    label: str = "Background Color",
    label_key: str = "schema.field.qrcode_background",
) -> Dict[str, Dict[str, Any]]:
    """QR code background color."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        description='Background color (hex or name)',
    )


def QRCODE_ERROR_CORRECTION(
    *,
    key: str = "error_correction",
    default: str = "M",
    label: str = "Error Correction",
    label_key: str = "schema.field.qrcode_error_correction",
) -> Dict[str, Dict[str, Any]]:
    """QR code error correction level."""
    return field(
        key,
        type="select",
        label=label,
        label_key=label_key,
        default=default,
        options=[
            {'value': 'L', 'label': 'Low (7%)'},
            {'value': 'M', 'label': 'Medium (15%)'},
            {'value': 'Q', 'label': 'Quartile (25%)'},
            {'value': 'H', 'label': 'High (30%)'},
        ],
        description='Error correction level',
    )


def QRCODE_LOGO_PATH(
    *,
    key: str = "logo_path",
    required: bool = False,
    label: str = "Logo Path",
    label_key: str = "schema.field.qrcode_logo_path",
) -> Dict[str, Dict[str, Any]]:
    """Path to logo image to embed in QR code."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        required=required,
        format="path",
        description='Path to logo image to embed in center',
    )


# ============================================
# Vision/AI Presets
# ============================================

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
        enum=["general", "ui_review", "accessibility", "bug_detection", "comparison", "data_extraction"],
        description='Type of analysis to perform',
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
        enum=["text", "structured", "json", "checklist"],
        description='Format of the analysis output',
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
        enum=["low", "high", "auto"],
        description='Level of detail for image analysis',
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
        enum=["visual_regression", "layout_diff", "content_diff", "full_analysis"],
        description='Type of comparison to perform',
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
    )


# ============================================
# Training/Practice Presets
# ============================================

def PRACTICE_URL(
    *,
    key: str = "url",
    required: bool = True,
    label: str = "URL",
    label_key: str = "schema.field.practice_url",
    placeholder: str = "https://example.com",
) -> Dict[str, Dict[str, Any]]:
    """URL for practice session."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        validation=validators.URL_HTTP,
    )


def PRACTICE_MAX_ITEMS(
    *,
    key: str = "max_items",
    default: int = 10,
    min_val: int = 1,
    max_val: int = 100,
    label: str = "Max Items",
    label_key: str = "schema.field.practice_max_items",
) -> Dict[str, Dict[str, Any]]:
    """Maximum items for practice."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Maximum items to process',
    )


def PRACTICE_SAMPLE_SIZE(
    *,
    key: str = "sample_size",
    default: int = 5,
    min_val: int = 1,
    max_val: int = 50,
    label: str = "Sample Size",
    label_key: str = "schema.field.practice_sample_size",
) -> Dict[str, Dict[str, Any]]:
    """Sample size for schema inference."""
    return field(
        key,
        type="number",
        label=label,
        label_key=label_key,
        default=default,
        min=min_val,
        max=max_val,
        description='Number of samples to analyze',
    )
