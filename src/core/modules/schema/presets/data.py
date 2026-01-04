"""
Data Presets / JSON Presets / CSV Presets / Template Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


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
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
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
        group=FieldGroup.OPTIONS,
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
        visibility=Visibility.EXPERT,
        group=FieldGroup.ADVANCED,
    )

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
        group=FieldGroup.BASIC,
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
        group=FieldGroup.BASIC,
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
        group=FieldGroup.BASIC,
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
        group=FieldGroup.OPTIONS,
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
        group=FieldGroup.OPTIONS,
    )

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
        group=FieldGroup.OPTIONS,
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
        group=FieldGroup.OPTIONS,
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
        group=FieldGroup.OPTIONS,
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
        group=FieldGroup.OPTIONS,
    )

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
        group=FieldGroup.BASIC,
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
        group=FieldGroup.BASIC,
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
        group=FieldGroup.BASIC,
    )
