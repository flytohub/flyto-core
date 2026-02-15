"""
File Operation Presets - File path and operation configurations
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


# Common file encodings
ENCODING_OPTIONS = [
    {"value": "utf-8", "label": "UTF-8 (Recommended)"},
    {"value": "utf-16", "label": "UTF-16"},
    {"value": "ascii", "label": "ASCII"},
    {"value": "latin-1", "label": "Latin-1 (ISO-8859-1)"},
    {"value": "cp1252", "label": "Windows-1252"},
    {"value": "big5", "label": "Big5 (繁體中文)"},
    {"value": "gb2312", "label": "GB2312 (简体中文)"},
    {"value": "gbk", "label": "GBK (简体中文擴展)"},
    {"value": "shift_jis", "label": "Shift-JIS (日文)"},
    {"value": "euc-kr", "label": "EUC-KR (韓文)"},
]


def SOURCE_PATH(
    *,
    key: str = "source",
    required: bool = True,
    label: str = "Source File",
    label_key: str = "schema.field.source_path",
    placeholder: str = "/path/to/file.txt",
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
        description='Path to the source file',
        group=FieldGroup.BASIC,
    )


def DESTINATION_PATH(
    *,
    key: str = "destination",
    required: bool = True,
    label: str = "Destination",
    label_key: str = "schema.field.destination_path",
    placeholder: str = "/path/to/output.txt",
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
        description='Path where the file will be saved',
        group=FieldGroup.BASIC,
    )


def FILE_PATH(
    *,
    key: str = "path",
    required: bool = True,
    label: str = "File Path",
    label_key: str = "schema.field.file_path",
    placeholder: str = "/path/to/file",
) -> Dict[str, Dict[str, Any]]:
    """Generic file path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
        description='Path to the file',
        group=FieldGroup.BASIC,
    )


def DIRECTORY_PATH(
    *,
    key: str = "directory",
    required: bool = True,
    label: str = "Directory",
    label_key: str = "schema.field.directory_path",
    placeholder: str = "/path/to/folder",
) -> Dict[str, Dict[str, Any]]:
    """Directory path."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        placeholder=placeholder,
        required=required,
        format="path",
        pathMode="directory",
        description='Path to the directory',
        group=FieldGroup.BASIC,
    )


def OVERWRITE(
    *,
    key: str = "overwrite",
    default: bool = False,
    label: str = "Overwrite Existing",
    label_key: str = "schema.field.overwrite",
) -> Dict[str, Dict[str, Any]]:
    """Overwrite destination if it exists."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Replace the file if it already exists',
        group=FieldGroup.OPTIONS,
    )


def IGNORE_MISSING(
    *,
    key: str = "ignore_missing",
    default: bool = False,
    label: str = "Ignore If Missing",
    label_key: str = "schema.field.ignore_missing",
) -> Dict[str, Dict[str, Any]]:
    """Do not raise error if file does not exist."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Skip without error if file does not exist',
        group=FieldGroup.OPTIONS,
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
        options=[
            {"value": "overwrite", "label": "Overwrite (replace content)"},
            {"value": "append", "label": "Append (add to end)"},
        ],
        description='How to write content to the file',
        group=FieldGroup.OPTIONS,
    )


def FILE_ENCODING(
    *,
    key: str = "encoding",
    default: str = "utf-8",
    label: str = "Encoding",
    label_key: str = "schema.field.file_encoding",
) -> Dict[str, Dict[str, Any]]:
    """File character encoding."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        options=ENCODING_OPTIONS,
        description='Character encoding for reading/writing text files',
        ui={'allowCustomValue': True},
        group=FieldGroup.OPTIONS,
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
        placeholder="Enter file content...",
        format="multiline",
        description='Text content to write to the file',
        group=FieldGroup.BASIC,
    )


def CREATE_DIRS(
    *,
    key: str = "create_dirs",
    default: bool = True,
    label: str = "Create Directories",
    label_key: str = "schema.field.create_dirs",
) -> Dict[str, Dict[str, Any]]:
    """Create parent directories if they don't exist."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Automatically create parent folders if needed',
        group=FieldGroup.OPTIONS,
    )


def FILE_PATTERN(
    *,
    key: str = "pattern",
    required: bool = False,
    default: str = "*",
    label: str = "File Pattern",
    label_key: str = "schema.field.file_pattern",
) -> Dict[str, Dict[str, Any]]:
    """Glob pattern for matching files."""
    common_patterns = [
        {"value": "*", "label": "* (All files)"},
        {"value": "*.txt", "label": "*.txt (Text files)"},
        {"value": "*.json", "label": "*.json (JSON files)"},
        {"value": "*.csv", "label": "*.csv (CSV files)"},
        {"value": "*.md", "label": "*.md (Markdown files)"},
        {"value": "*.py", "label": "*.py (Python files)"},
        {"value": "*.js", "label": "*.js (JavaScript files)"},
        {"value": "**/*", "label": "**/* (All files recursively)"},
    ]
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        default=default,
        required=required,
        options=common_patterns,
        placeholder="*.txt, *.json",
        description='Glob pattern to match files (e.g., *.txt, **/*.json)',
        ui={'allowCustomValue': True},
        group=FieldGroup.OPTIONS,
    )


def RECURSIVE(
    *,
    key: str = "recursive",
    default: bool = False,
    label: str = "Include Subdirectories",
    label_key: str = "schema.field.recursive",
) -> Dict[str, Dict[str, Any]]:
    """Process files in subdirectories."""
    return field(
        key,
        type="boolean",
        label=label,
        label_key=label_key,
        default=default,
        description='Also process files in subdirectories',
        group=FieldGroup.OPTIONS,
    )
