# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Build deterministic site graphs from browser/page evidence."""

from ...registry import register_module
from ..warroom.discover import WarroomDiscoverModule


@register_module(
    module_id="verification.discover",
    version="1.0.0",
    category="verification",
    tags=["verification", "discovery", "deterministic", "browser", "evidence"],
    label="Verification Discover",
    description="Build a deterministic site graph from browser state or supplied page snapshots",
    icon="Radar",
    color="#0EA5E9",
    input_types=["object"],
    output_types=["object"],
    can_receive_from=["browser.*", "data.*", "flow.*", "start"],
    can_connect_to=["verification.*", "testing.*", "verify.*", "data.*", "file.*"],
    params_schema={
        "target": {"type": "string", "required": True, "description": "Target base URL or page URL"},
        "pages": {"type": "array", "required": False, "description": "Optional pre-collected page observations"},
        "use_browser": {"type": "boolean", "default": True, "description": "Read current browser page when available"},
    },
    output_schema={
        "ok": {"type": "boolean"},
        "site_graph": {"type": "object"},
        "scores": {"type": "object"},
    },
    timeout_ms=120000,
)
class VerificationDiscoverModule(WarroomDiscoverModule):
    """Build a deterministic site graph."""

    module_name = "Verification Discover"
    module_description = "Build deterministic site graph from browser evidence"

