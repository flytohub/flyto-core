# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Invoke one host-provided capability through an opaque runtime dispatcher.

The workflow names only a canonical capability, a commanded resource, and
bounded JSON-safe arguments.  The runtime object that can actually reach the
device is injected by the host and never serialised into workflow data.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field
from ...schema.constants import FieldGroup


RUNTIME_DISPATCHER_CONTEXT_KEY = "_flyto_runtime_external_capability_dispatcher"
MAX_ARGUMENTS = 32
MAX_TEXT = 1000


def _bounded_scalar(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, int) and not isinstance(value, bool):
        return -(2**53) <= value <= 2**53
    if isinstance(value, float):
        return math.isfinite(value) and abs(value) <= 1e12
    if isinstance(value, str):
        return len(value) <= MAX_TEXT
    return False


@register_module(
    module_id="capability.invoke",
    version="1.0.0",
    category="capability",
    tags=["capability", "device", "robotics", "runtime", "adapter"],
    label="Invoke Capability",
    label_key="modules.capability.invoke.label",
    description=(
        "Invoke one approved host-provided capability through the execution-scoped "
        "runtime adapter."
    ),
    description_key="modules.capability.invoke.description",
    icon="PlugZap",
    color="#64748B",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["*"],
    can_connect_to=["*"],
    retryable=False,
    concurrent_safe=False,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],
    params_schema=compose(
        field(
            "resource_id",
            type="string",
            required=True,
            label="Resource ID",
            description="Commanded resource selected by the control plane.",
            group=FieldGroup.BASIC,
        ),
        field(
            "capability_id",
            type="string",
            required=True,
            label="Capability ID",
            description="Canonical capability approved for the selected resource.",
            group=FieldGroup.BASIC,
        ),
        field(
            "arguments",
            type="object",
            required=False,
            default={},
            label="Arguments",
            description="Already-bounded capability arguments compiled by the control plane.",
            group=FieldGroup.OPTIONS,
        ),
    ),
)
class CapabilityInvokeModule(BaseModule):
    """Bridge a canonical workflow step to the host's opaque adapter authority."""

    module_id = "capability.invoke"

    def validate_params(self) -> None:
        resource_id = self.params.get("resource_id")
        capability_id = self.params.get("capability_id")
        arguments = self.params.get("arguments", {})

        if not isinstance(resource_id, str) or not resource_id.strip() or len(resource_id) > 128:
            raise ValueError("resource_id must be a non-empty bounded string")
        if not isinstance(capability_id, str) or not capability_id.strip() or len(capability_id) > 128:
            raise ValueError("capability_id must be a non-empty bounded string")
        if not isinstance(arguments, Mapping):
            raise ValueError("arguments must be an object")
        if len(arguments) > MAX_ARGUMENTS:
            raise ValueError("arguments contains too many fields")
        for key, value in arguments.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 128:
                raise ValueError("argument names must be bounded non-empty strings")
            if not _bounded_scalar(value):
                raise ValueError(f"argument {key!r} must be a bounded JSON scalar")

    async def execute(self) -> Any:
        dispatcher = self.context.get(RUNTIME_DISPATCHER_CONTEXT_KEY)
        if (
            getattr(type(dispatcher), "_flyto_runtime_opaque", False) is not True
            or not callable(getattr(dispatcher, "invoke", None))
        ):
            return {
                "ok": False,
                "error": {
                    "code": "CAPABILITY_RUNTIME_UNAVAILABLE",
                    "message": "This execution has no trusted host capability dispatcher.",
                },
            }

        request = {
            "resource_id": self.params["resource_id"].strip(),
            "capability_id": self.params["capability_id"].strip(),
            "arguments": dict(self.params.get("arguments") or {}),
        }
        result = await dispatcher.invoke(request)
        if not isinstance(result, Mapping):
            return {
                "ok": False,
                "error": {
                    "code": "CAPABILITY_RESULT_INVALID",
                    "message": "The host capability dispatcher returned an invalid result.",
                },
            }
        payload = dict(result)
        if str(payload.get("outcome") or "") != "completed":
            return {
                "ok": False,
                "error": {
                    "code": "CAPABILITY_CALL_FAILED",
                    "message": str(
                        payload.get("detail")
                        or payload.get("outcome")
                        or "Capability call failed"
                    )[:500],
                },
                "data": payload,
            }
        return self.success(payload)
