"""
Shell/Process Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from ..constants import Visibility, FieldGroup
from .. import validators


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
        description="Shell command to execute",
        placeholder=placeholder,
        required=required,
        group=FieldGroup.BASIC,
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
        description="Directory to execute command in",
        placeholder=placeholder,
        required=False,
        format="path",
        pathMode="directory",
        group=FieldGroup.OPTIONS,
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
        description="Additional environment variables to set",
        required=False,
        ui={"widget": "key_value"},
        group=FieldGroup.OPTIONS,
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
        group=FieldGroup.ADVANCED,
        visibility=Visibility.EXPERT,
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
        description="Capture stderr separately from stdout",
        default=default,
        advanced=True,
        group=FieldGroup.ADVANCED,
        visibility=Visibility.EXPERT,
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
        description="Raise exception if command returns non-zero exit code",
        default=default,
        advanced=True,
        group=FieldGroup.ADVANCED,
        visibility=Visibility.EXPERT,
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
        description="Friendly name to identify the process",
        placeholder=placeholder,
        required=False,
        group=FieldGroup.OPTIONS,
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
        group=FieldGroup.OPTIONS,
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
        description="Capture stdout/stderr output from the process",
        default=default,
        group=FieldGroup.OPTIONS,
    )


def LOG_FILE(
    *,
    key: str = "log_file",
    label: str = "Log File",
    label_key: str = "schema.field.log_file",
    placeholder: str = "/tmp/process.log",
) -> Dict[str, Dict[str, Any]]:
    """File to write process output to."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description="File path to write process output to",
        placeholder=placeholder,
        required=False,
        format="path",
        advanced=True,
        group=FieldGroup.ADVANCED,
        visibility=Visibility.EXPERT,
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
        description="Automatically restart the process if it exits",
        default=default,
        advanced=True,
        group=FieldGroup.ADVANCED,
        visibility=Visibility.EXPERT,
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
        description="Signal to send to the process",
        default=default,
        options=[
            {"value": "SIGTERM", "label": "SIGTERM (graceful termination)"},
            {"value": "SIGKILL", "label": "SIGKILL (force kill)"},
            {"value": "SIGINT", "label": "SIGINT (interrupt)"},
        ],
        advanced=True,
        group=FieldGroup.ADVANCED,
        visibility=Visibility.EXPERT,
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
        description="Force kill the process immediately with SIGKILL",
        default=default,
        group=FieldGroup.OPTIONS,
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
        description="Stop all tracked processes",
        default=default,
        group=FieldGroup.OPTIONS,
    )


def PROCESS_ID(
    *,
    key: str = "process_id",
    label: str = "Process ID",
    label_key: str = "schema.field.process_id",
    placeholder: str = "dev-server-abc123",
) -> Dict[str, Dict[str, Any]]:
    """Internal process ID."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description="Internal process identifier (from process.start)",
        placeholder=placeholder,
        required=False,
        group=FieldGroup.OPTIONS,
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
        description="System process ID (PID) of the process",
        required=False,
        group=FieldGroup.OPTIONS,
    )


def FILTER_NAME(
    *,
    key: str = "filter_name",
    label: str = "Filter by Name",
    label_key: str = "schema.field.filter_name",
    placeholder: str = "server",
) -> Dict[str, Dict[str, Any]]:
    """Filter by name (substring match)."""
    return field(
        key,
        type="string",
        label=label,
        label_key=label_key,
        description="Filter processes by name (substring match)",
        placeholder=placeholder,
        required=False,
        group=FieldGroup.OPTIONS,
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
        description="Include running/stopped status check for each process",
        default=default,
        group=FieldGroup.OPTIONS,
    )
