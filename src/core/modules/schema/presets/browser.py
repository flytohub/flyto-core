"""
Browser Presets / Additional Browser Presets / Browser Extended Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


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

