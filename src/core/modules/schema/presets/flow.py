"""
Flow Control Presets
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..builders import field, compose
from .. import validators


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

