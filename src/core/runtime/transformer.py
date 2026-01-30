"""
Manifest-to-Module Transformer

Transforms plugin manifests into the exact ModuleItem format expected by the frontend.
This ensures zero frontend changes are needed to support plugins.

The frontend expects modules in this exact shape (from Addendum Section 13.2):
{
    "module_id": "database.query",
    "label": "Execute SQL Query",
    "label_key": "modules.database.query.label",
    "description": "...",
    "description_key": "modules.database.query.description",
    "category": "database",
    "icon": "Database",
    "color": "#6366F1",
    "level": 1,
    "version": "1.0.0",
    "params_schema": {...},
    "output_schema": {...},
    "input_types": ["*"],
    "output_types": ["object"],
    "can_receive_from": ["*"],
    "can_connect_to": ["*"],
    "ui": {...},
    "tags": [...],
    "source": "plugin",
    "plugin_id": "flyto-official_database"
}
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def transform_manifest_to_modules(
    manifest: Dict[str, Any],
    plugin_status: str = "active",
) -> List[Dict[str, Any]]:
    """
    Transform a plugin manifest into a list of ModuleItem objects.

    Each step in the manifest becomes a separate module.

    Args:
        manifest: Plugin manifest dict
        plugin_status: Plugin status (active, deprecated, disabled)

    Returns:
        List of ModuleItem dicts matching frontend expected format
    """
    plugin_id = manifest.get("id", "unknown")
    plugin_version = manifest.get("version", "1.0.0")
    plugin_vendor = manifest.get("vendor", "unknown")
    plugin_meta = manifest.get("meta", {})

    # Extract category from plugin ID
    # e.g., "flyto-official_database" -> "database"
    category = _extract_category(plugin_id)

    modules = []

    for step in manifest.get("steps", []):
        module = transform_step_to_module(
            step=step,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            plugin_vendor=plugin_vendor,
            plugin_meta=plugin_meta,
            category=category,
            plugin_status=plugin_status,
        )
        modules.append(module)

    return modules


def transform_step_to_module(
    step: Dict[str, Any],
    plugin_id: str,
    plugin_version: str,
    plugin_vendor: str,
    plugin_meta: Dict[str, Any],
    category: str,
    plugin_status: str = "active",
) -> Dict[str, Any]:
    """
    Transform a single step definition into a ModuleItem.

    Args:
        step: Step definition from manifest
        plugin_id: Plugin ID
        plugin_version: Plugin version
        plugin_vendor: Plugin vendor
        plugin_meta: Plugin metadata
        category: Module category
        plugin_status: Plugin status

    Returns:
        ModuleItem dict matching frontend expected format
    """
    step_id = step.get("id", "unknown")
    module_id = f"{category}.{step_id}"

    # Get step UI settings or fallback to plugin meta
    step_ui = step.get("ui", {})
    icon = step_ui.get("icon") or plugin_meta.get("icon", "Box")
    color = step_ui.get("color") or plugin_meta.get("color", "#6B7280")

    # Build i18n keys
    label_key = f"modules.{category}.{step_id}.label"
    description_key = f"modules.{category}.{step_id}.description"

    # Get cost info
    cost = step.get("cost", {})
    cost_points = cost.get("points", 1)
    cost_class = cost.get("class", "standard")

    # Get schemas
    input_schema = step.get("inputSchema", {"type": "object", "properties": {}})
    output_schema = step.get("outputSchema", {"type": "object", "properties": {}})

    # Build params_schema from inputSchema
    params_schema = _convert_input_schema_to_params(input_schema)

    # Determine input/output types
    input_types = _infer_input_types(input_schema)
    output_types = _infer_output_types(output_schema)

    # Build standard input/output ports
    input_ports = [
        {
            "id": "input",
            "label": "Input",
            "label_key": f"modules.{category}.{step_id}.ports.input",
            "data_type": "any",
            "edge_type": "data",
            "max_connections": 1,
            "required": False,
        }
    ]

    output_ports = [
        {
            "id": "output",
            "label": "Output",
            "label_key": f"modules.{category}.{step_id}.ports.output",
            "data_type": "object",
            "edge_type": "data",
        },
        {
            "id": "error",
            "label": "Error",
            "label_key": "common.ports.error",
            "event": "error",
            "color": "#EF4444",
            "edge_type": "control",
        }
    ]

    # Build module item with all frontend-required fields
    module = {
        # Core identifiers (both formats for compatibility)
        "module_id": module_id,
        "moduleId": module_id,
        "category": category,
        "version": plugin_version,

        # Type info for frontend
        "type": f"{category}_{step_id}",
        "node_type": "module",
        "nodeType": "module",
        "action": step_id,
        "level": "plugin",

        # Display
        "label": step.get("label", step_id.replace("_", " ").title()),
        "label_key": label_key,
        "description": step.get("description", ""),
        "description_key": description_key,

        # Visual
        "icon": icon,
        "color": color,
        "group": plugin_meta.get("category", category).title(),
        "visibility": step_ui.get("visibility", "default"),

        # Ports for node connections
        "input_ports": input_ports,
        "output_ports": output_ports,

        # Handles for React Flow
        "input_handles": [
            {"id": "target", "position": "left", "color": "#6B7280"}
        ],
        "output_handles": [
            {"id": "source", "position": "right", "color": color}
        ],

        # Schemas
        "params_schema": params_schema,
        "output_schema": output_schema,

        # Connection types
        "input_types": input_types,
        "output_types": output_types,
        "can_receive_from": ["*"],
        "can_connect_to": ["*"],

        # UI settings
        "ui": {
            "icon": icon,
            "color": color,
            "visibility": step_ui.get("visibility", "default"),
            "group": plugin_meta.get("category", category),
        },

        # Tags and metadata
        "tags": step.get("tags", [category, step_id]),

        # Plugin source info
        "source": "plugin",
        "plugin_id": plugin_id,
        "plugin_vendor": plugin_vendor,
        "plugin_status": plugin_status,

        # Cost info
        "cost": {
            "points": cost_points,
            "class": cost_class,
        },

        # Permissions required
        "permissions": step.get("permissions", []),

        # Deprecation info
        "deprecated": plugin_status == "deprecated",
        "deprecated_message": step.get("deprecatedMessage"),

        # Additional frontend compatibility fields
        "tier": "standard",
        "stability": "stable",
        "requires_context": [],
        "provides_context": [],
        "concurrent_safe": True,
        "retryable": True,
        "max_retries": 3,
        "timeout": 30.0,
    }

    return module


def transform_modules_for_tiered_response(
    modules: List[Dict[str, Any]],
    tier: str = "free",
) -> List[Dict[str, Any]]:
    """
    Transform modules for the /modules/tiered API response.

    Filters and transforms modules based on user tier.

    Args:
        modules: List of module items
        tier: User tier (free, pro, team, enterprise)

    Returns:
        List of modules filtered and transformed for the tier
    """
    result = []

    for module in modules:
        # Check tier access (simplified - real logic would check permissions)
        cost_class = module.get("cost", {}).get("class", "standard")

        # Free tier can only access free modules
        if tier == "free" and cost_class not in ("free", "standard"):
            continue

        # Add tier-specific info
        module_copy = module.copy()
        module_copy["tier_access"] = True
        module_copy["tier_info"] = {
            "current_tier": tier,
            "required_tier": _get_required_tier(cost_class),
        }

        result.append(module_copy)

    return result


def merge_plugin_modules_with_core(
    core_modules: List[Dict[str, Any]],
    plugin_modules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge plugin modules with core modules for the catalog.

    Plugin modules are added alongside core modules, not replacing them.
    If a plugin provides the same module_id as core, plugin takes precedence
    (based on routing preference).

    Args:
        core_modules: List of core module items
        plugin_modules: List of plugin module items

    Returns:
        Merged list with plugin modules included
    """
    # Build index of core modules
    core_index = {m["module_id"]: m for m in core_modules}

    # Build index of plugin modules
    plugin_index = {m["module_id"]: m for m in plugin_modules}

    # Merge: plugin modules override core modules with same ID
    merged = {}

    # Add core modules first
    for module_id, module in core_index.items():
        module["source"] = module.get("source", "core")
        merged[module_id] = module

    # Add/override with plugin modules
    for module_id, module in plugin_index.items():
        if module_id in merged:
            # Plugin overrides core - mark the core as having plugin alternative
            module["has_core_fallback"] = True
        merged[module_id] = module

    return list(merged.values())


def _extract_category(plugin_id: str) -> str:
    """
    Extract category from plugin ID.

    Examples:
        "flyto-official_database" -> "database"
        "flyto-official_llm" -> "llm"
        "third-party_slack" -> "slack"
    """
    if "_" in plugin_id:
        return plugin_id.split("_", 1)[-1]
    if "/" in plugin_id:
        return plugin_id.split("/")[-1]
    return plugin_id


def _convert_input_schema_to_params(input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert JSON Schema inputSchema to params_schema format.

    The frontend expects a specific params_schema format.
    """
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])

    params = {}

    for name, prop in properties.items():
        param = {
            "type": prop.get("type", "string"),
            "description": prop.get("description", ""),
            "required": name in required,
        }

        # Copy additional schema properties
        for key in ("default", "enum", "minimum", "maximum", "minLength", "maxLength", "pattern"):
            if key in prop:
                param[key] = prop[key]

        # Handle items for array type
        if prop.get("type") == "array" and "items" in prop:
            param["items"] = prop["items"]

        params[name] = param

    return {
        "type": "object",
        "properties": params,
        "required": required,
    }


def _infer_input_types(input_schema: Dict[str, Any]) -> List[str]:
    """Infer input types from schema."""
    # Default to accepting anything
    return ["*"]


def _infer_output_types(output_schema: Dict[str, Any]) -> List[str]:
    """Infer output types from schema."""
    schema_type = output_schema.get("type", "object")

    if schema_type == "array":
        return ["array"]
    elif schema_type == "object":
        return ["object"]
    elif schema_type == "string":
        return ["string"]
    elif schema_type in ("number", "integer"):
        return ["number"]
    else:
        return ["*"]


def _get_required_tier(cost_class: str) -> str:
    """Get minimum required tier for a cost class."""
    tier_map = {
        "free": "free",
        "standard": "free",
        "premium": "pro",
        "enterprise": "enterprise",
    }
    return tier_map.get(cost_class, "free")
