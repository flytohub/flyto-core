# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Execute an approved MCP recipe contract and emit redacted evidence."""

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from ...base import BaseModule
from ...registry import register_module

_SECRET_KEY_RE = re.compile(
    r"(authorization|cookie|password|secret|session|bearer|"
    r"auth[_-]?token|access[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|private[_-]?key|client[_-]?secret|(^|[_-])pat([_-]|$)|(^|[_-])token([_-]|$))",
    re.IGNORECASE,
)

_RUNTIME_ARG_SOURCES = (
    "runtime_args",
    "variables",
    "inputs",
    "trigger_payload",
    "_trigger_payload",
)


def _is_secret_key(key: Optional[str]) -> bool:
    return bool(key and _SECRET_KEY_RE.search(str(key)))


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalize_arg_names(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    names: List[str] = []
    for item in value:
        name = ""
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            raw_name = item.get("name") or item.get("key") or item.get("id")
            if isinstance(raw_name, str):
                name = raw_name
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def _redact(value: Any, key: Optional[str] = None) -> Any:
    if _is_secret_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _merge_mapping(target: Dict[str, Any], source: Any) -> None:
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        if isinstance(key, str):
            target[key] = value


def _runtime_args_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    runtime_args: Dict[str, Any] = {}

    for source_key in _RUNTIME_ARG_SOURCES:
        _merge_mapping(runtime_args, context.get(source_key))

    trigger_payload = context.get("trigger_payload")
    if isinstance(trigger_payload, dict):
        _merge_mapping(runtime_args, trigger_payload.get("arguments"))
        _merge_mapping(runtime_args, trigger_payload.get("payload"))

    for key, value in context.items():
        if (
            isinstance(key, str)
            and not key.startswith("__")
            and key not in _RUNTIME_ARG_SOURCES
            and key not in ("params",)
            and isinstance(value, (str, int, float, bool, type(None)))
        ):
            runtime_args[key] = value

    return runtime_args


def _missing_arg_names(required_names: Iterable[str], values: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for name in required_names:
        value = values.get(name)
        if value is None or value == "":
            missing.append(name)
    return missing


@register_module(
    module_id="mcp.recipe",
    version="1.0.0",
    category="mcp",
    tags=["mcp", "recipe", "warroom", "evidence", "runtime-only"],
    label="MCP Recipe",
    description="Run an approved MCP recipe contract and emit redacted execution evidence",
    icon="PlugZap",
    color="#2563EB",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["flow.*", "mcp.*", "warroom.*", "testing.*", "start"],
    can_connect_to=["mcp.*", "warroom.*", "testing.*", "verify.*", "data.*", "output.*"],
    params_schema={
        "recipe_id": {"type": "string", "required": True},
        "scenario_id": {"type": "string", "required": True},
        "default_args": {"type": "object", "default": {}},
        "runtime_required_args": {"type": "array", "default": []},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "recipe_ok": {"type": "boolean"},
        "recipe_id": {"type": "string"},
        "scenario_id": {"type": "string"},
        "status": {"type": "string"},
        "runtime_args_present": {"type": "array"},
        "runtime_args_missing": {"type": "array"},
        "evidence": {"type": "object"},
    },
    handles_sensitive_data=True,
    timeout_ms=30000,
)
class McpRecipeModule(BaseModule):
    """Deterministic runtime bridge for approved MCP recipe bundles."""

    module_name = "MCP Recipe"
    module_description = "Run an approved MCP recipe contract"

    def validate_params(self) -> None:
        for key in ("recipe_id", "scenario_id"):
            value = self.params.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} is required")

        default_args = self.params.get("default_args", {})
        if default_args is not None and not isinstance(default_args, dict):
            raise ValueError("default_args must be an object")

        required_args = self.params.get("runtime_required_args", [])
        if required_args is not None and not isinstance(required_args, list):
            raise ValueError("runtime_required_args must be an array")

    async def execute(self) -> Dict[str, Any]:
        recipe_id = self.params["recipe_id"].strip()
        scenario_id = self.params["scenario_id"].strip()
        default_args = self.params.get("default_args") or {}
        required_arg_names = _normalize_arg_names(self.params.get("runtime_required_args", []))
        runtime_args = _runtime_args_from_context(self.context)
        effective_args = dict(default_args)
        effective_args.update(runtime_args)
        missing_args = _missing_arg_names(required_arg_names, effective_args)
        runtime_args_present = sorted(
            name for name in required_arg_names if name not in missing_args
        )
        invoked_at = _utc_now()
        recipe_ok = not missing_args
        status = "completed" if recipe_ok else "needs_runtime_args"

        evidence = {
            "contract": "flyto.mcp.recipe.execution.v1",
            "recipe_id": recipe_id,
            "scenario_id": scenario_id,
            "invoked_at": invoked_at,
            "runtime_args_policy": "runtime_only",
            "secret_values_stored": False,
            "default_args": _redact(default_args),
            "runtime_args_present": runtime_args_present,
            "runtime_args_missing": missing_args,
            "target": _redact(effective_args.get("target") or effective_args.get("base_url"), "target"),
        }

        return {
            "ok": True,
            "recipe_ok": recipe_ok,
            "recipe_id": recipe_id,
            "scenario_id": scenario_id,
            "status": status,
            "message": (
                "Recipe contract completed"
                if recipe_ok
                else "Recipe contract is missing required runtime arguments"
            ),
            "runtime_args_present": runtime_args_present,
            "runtime_args_missing": missing_args,
            "secret_values_stored": False,
            "evidence": evidence,
            "data": evidence,
        }
