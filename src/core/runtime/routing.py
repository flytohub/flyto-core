"""
Module Routing

Determines whether to route module invocations to plugins or legacy in-process modules.

Routing Strategy:
1. Check if plugin exists for the module
2. If plugin exists and is healthy → use plugin
3. If plugin fails and fallback enabled → use legacy
4. If force_plugin=true → no fallback, error on plugin failure

Configuration Hierarchy:
1. Per-module overrides (highest priority)
2. Global routing config
3. Defaults (prefer plugin, fallback to legacy)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class RoutingPreference(str, Enum):
    """Routing preference for module invocation."""
    PLUGIN = "plugin"      # Prefer plugin, may fallback
    LEGACY = "legacy"      # Prefer legacy, may fallback
    PLUGIN_ONLY = "plugin_only"  # Plugin only, no fallback
    LEGACY_ONLY = "legacy_only"  # Legacy only, no fallback


class RoutingDecision(str, Enum):
    """Result of routing decision."""
    USE_PLUGIN = "use_plugin"
    USE_LEGACY = "use_legacy"
    FALLBACK_TO_LEGACY = "fallback_to_legacy"
    FALLBACK_TO_PLUGIN = "fallback_to_plugin"
    NO_HANDLER = "no_handler"


@dataclass
class ModuleRoutingOverride:
    """Per-module routing configuration override."""
    module_pattern: str  # e.g., "database.*", "llm.chat", "*"
    prefer: RoutingPreference = RoutingPreference.PLUGIN
    fallback_enabled: bool = True
    force_plugin: bool = False
    force_legacy: bool = False
    disabled: bool = False  # Disable module entirely
    reason: Optional[str] = None  # Why this override exists

    def matches(self, module_id: str) -> bool:
        """Check if this override matches the module ID."""
        if self.module_pattern == "*":
            return True

        if self.module_pattern.endswith(".*"):
            # Category wildcard: "database.*" matches "database.query"
            prefix = self.module_pattern[:-2]
            return module_id.startswith(prefix + ".")

        # Exact match
        return module_id == self.module_pattern


@dataclass
class RoutingConfig:
    """Global routing configuration."""
    # Default behavior
    default_prefer: RoutingPreference = RoutingPreference.PLUGIN
    default_fallback_enabled: bool = True
    force_plugin_default: bool = False

    # Per-module overrides (processed in order, first match wins)
    overrides: List[ModuleRoutingOverride] = field(default_factory=list)

    # Plugin availability (set by PluginManager)
    available_plugins: Set[str] = field(default_factory=set)

    # Legacy module availability (set from ModuleRegistry)
    available_legacy: Set[str] = field(default_factory=set)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoutingConfig":
        """Create from dictionary (e.g., from config file)."""
        overrides = []
        for override_data in data.get("overrides", []):
            overrides.append(ModuleRoutingOverride(
                module_pattern=override_data.get("module", "*"),
                prefer=RoutingPreference(override_data.get("prefer", "plugin")),
                fallback_enabled=override_data.get("fallback", True),
                force_plugin=override_data.get("forcePlugin", False),
                force_legacy=override_data.get("forceLegacy", False),
                disabled=override_data.get("disabled", False),
                reason=override_data.get("reason"),
            ))

        return cls(
            default_prefer=RoutingPreference(data.get("defaultPrefer", "plugin")),
            default_fallback_enabled=data.get("defaultFallback", True),
            force_plugin_default=data.get("forcePluginDefault", False),
            overrides=overrides,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "defaultPrefer": self.default_prefer.value,
            "defaultFallback": self.default_fallback_enabled,
            "forcePluginDefault": self.force_plugin_default,
            "overrides": [
                {
                    "module": o.module_pattern,
                    "prefer": o.prefer.value,
                    "fallback": o.fallback_enabled,
                    "forcePlugin": o.force_plugin,
                    "forceLegacy": o.force_legacy,
                    "disabled": o.disabled,
                    "reason": o.reason,
                }
                for o in self.overrides
            ],
        }


@dataclass
class RoutingResult:
    """Result of routing decision."""
    decision: RoutingDecision
    use_plugin: bool
    plugin_id: Optional[str] = None
    legacy_module_id: Optional[str] = None
    fallback_available: bool = False
    reason: str = ""


class ModuleRouter:
    """
    Routes module invocations to plugins or legacy modules.

    Usage:
        router = ModuleRouter(config)
        router.set_available_plugins({"database", "llm"})
        router.set_available_legacy({"database.query", "string.uppercase"})

        result = router.route("database.query")
        if result.use_plugin:
            # invoke via plugin
        else:
            # invoke via legacy
    """

    def __init__(self, config: Optional[RoutingConfig] = None):
        self.config = config or RoutingConfig()
        self._plugin_health: Dict[str, bool] = {}  # plugin_id -> is_healthy

    def set_available_plugins(self, plugins: Set[str]):
        """Set the list of available plugins."""
        self.config.available_plugins = plugins

    def set_available_legacy(self, modules: Set[str]):
        """Set the list of available legacy modules."""
        self.config.available_legacy = modules

    def set_plugin_health(self, plugin_id: str, is_healthy: bool):
        """Update plugin health status."""
        self._plugin_health[plugin_id] = is_healthy

    def route(
        self,
        module_id: str,
        plugin_id: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> RoutingResult:
        """
        Determine how to route a module invocation.

        Args:
            module_id: Legacy module ID (e.g., "database.query")
            plugin_id: Optional explicit plugin ID
            step_id: Optional step ID within plugin

        Returns:
            RoutingResult with decision and handler info
        """
        # Parse module ID if needed
        if not plugin_id:
            plugin_id, step_id = self._parse_module_id(module_id)

        # Check for overrides
        override = self._find_override(module_id)

        # Check if module is disabled
        if override and override.disabled:
            return RoutingResult(
                decision=RoutingDecision.NO_HANDLER,
                use_plugin=False,
                reason=f"Module disabled: {override.reason or 'no reason given'}",
            )

        # Determine preference
        prefer = override.prefer if override else self.config.default_prefer
        fallback_enabled = override.fallback_enabled if override else self.config.default_fallback_enabled
        force_plugin = (override.force_plugin if override else False) or self.config.force_plugin_default
        force_legacy = override.force_legacy if override else False

        # Check availability
        plugin_available = self._is_plugin_available(plugin_id)
        plugin_healthy = self._is_plugin_healthy(plugin_id)
        legacy_available = module_id in self.config.available_legacy

        logger.debug(
            f"Routing {module_id}: prefer={prefer.value}, "
            f"plugin_available={plugin_available}, plugin_healthy={plugin_healthy}, "
            f"legacy_available={legacy_available}, force_plugin={force_plugin}"
        )

        # Force plugin mode
        if force_plugin:
            if plugin_available and plugin_healthy:
                return RoutingResult(
                    decision=RoutingDecision.USE_PLUGIN,
                    use_plugin=True,
                    plugin_id=plugin_id,
                    legacy_module_id=module_id,
                    fallback_available=False,  # No fallback in force mode
                    reason="Force plugin mode",
                )
            else:
                return RoutingResult(
                    decision=RoutingDecision.NO_HANDLER,
                    use_plugin=False,
                    plugin_id=plugin_id,
                    reason=f"Plugin required but {'unhealthy' if plugin_available else 'not available'}",
                )

        # Force legacy mode
        if force_legacy:
            if legacy_available:
                return RoutingResult(
                    decision=RoutingDecision.USE_LEGACY,
                    use_plugin=False,
                    legacy_module_id=module_id,
                    fallback_available=False,
                    reason="Force legacy mode",
                )
            else:
                return RoutingResult(
                    decision=RoutingDecision.NO_HANDLER,
                    use_plugin=False,
                    legacy_module_id=module_id,
                    reason="Legacy required but not available",
                )

        # Prefer plugin
        if prefer in (RoutingPreference.PLUGIN, RoutingPreference.PLUGIN_ONLY):
            if plugin_available and plugin_healthy:
                return RoutingResult(
                    decision=RoutingDecision.USE_PLUGIN,
                    use_plugin=True,
                    plugin_id=plugin_id,
                    legacy_module_id=module_id,
                    fallback_available=fallback_enabled and legacy_available,
                    reason="Plugin preferred and available",
                )
            elif fallback_enabled and legacy_available:
                return RoutingResult(
                    decision=RoutingDecision.FALLBACK_TO_LEGACY,
                    use_plugin=False,
                    plugin_id=plugin_id,
                    legacy_module_id=module_id,
                    fallback_available=False,
                    reason=f"Plugin {'unhealthy' if plugin_available else 'not available'}, falling back to legacy",
                )
            elif legacy_available:
                return RoutingResult(
                    decision=RoutingDecision.USE_LEGACY,
                    use_plugin=False,
                    legacy_module_id=module_id,
                    reason="Plugin not available, using legacy (fallback disabled)",
                )
            else:
                return RoutingResult(
                    decision=RoutingDecision.NO_HANDLER,
                    use_plugin=False,
                    reason="Neither plugin nor legacy available",
                )

        # Prefer legacy
        if prefer in (RoutingPreference.LEGACY, RoutingPreference.LEGACY_ONLY):
            if legacy_available:
                return RoutingResult(
                    decision=RoutingDecision.USE_LEGACY,
                    use_plugin=False,
                    legacy_module_id=module_id,
                    fallback_available=fallback_enabled and plugin_available and plugin_healthy,
                    reason="Legacy preferred and available",
                )
            elif fallback_enabled and plugin_available and plugin_healthy:
                return RoutingResult(
                    decision=RoutingDecision.FALLBACK_TO_PLUGIN,
                    use_plugin=True,
                    plugin_id=plugin_id,
                    legacy_module_id=module_id,
                    fallback_available=False,
                    reason="Legacy not available, falling back to plugin",
                )
            elif plugin_available and plugin_healthy:
                return RoutingResult(
                    decision=RoutingDecision.USE_PLUGIN,
                    use_plugin=True,
                    plugin_id=plugin_id,
                    reason="Legacy not available, using plugin (fallback disabled)",
                )
            else:
                return RoutingResult(
                    decision=RoutingDecision.NO_HANDLER,
                    use_plugin=False,
                    reason="Neither legacy nor plugin available",
                )

        # Fallback: no handler
        return RoutingResult(
            decision=RoutingDecision.NO_HANDLER,
            use_plugin=False,
            reason="No routing decision could be made",
        )

    def route_with_fallback(
        self,
        module_id: str,
        primary_failed: bool = False,
    ) -> RoutingResult:
        """
        Get fallback routing after primary handler failed.

        Args:
            module_id: Module ID
            primary_failed: Whether the primary handler failed

        Returns:
            RoutingResult for fallback handler
        """
        initial_result = self.route(module_id)

        if not primary_failed:
            return initial_result

        if not initial_result.fallback_available:
            return RoutingResult(
                decision=RoutingDecision.NO_HANDLER,
                use_plugin=False,
                reason="No fallback available",
            )

        # Swap to fallback
        if initial_result.use_plugin:
            # Was using plugin, fall back to legacy
            return RoutingResult(
                decision=RoutingDecision.FALLBACK_TO_LEGACY,
                use_plugin=False,
                plugin_id=initial_result.plugin_id,
                legacy_module_id=initial_result.legacy_module_id,
                fallback_available=False,
                reason="Plugin failed, using legacy fallback",
            )
        else:
            # Was using legacy, fall back to plugin
            plugin_id, _ = self._parse_module_id(module_id)
            return RoutingResult(
                decision=RoutingDecision.FALLBACK_TO_PLUGIN,
                use_plugin=True,
                plugin_id=plugin_id,
                legacy_module_id=module_id,
                fallback_available=False,
                reason="Legacy failed, using plugin fallback",
            )

    def _find_override(self, module_id: str) -> Optional[ModuleRoutingOverride]:
        """Find matching override for module."""
        for override in self.config.overrides:
            if override.matches(module_id):
                return override
        return None

    def _is_plugin_available(self, plugin_id: str) -> bool:
        """Check if plugin is available."""
        # Check various forms of the plugin ID
        if plugin_id in self.config.available_plugins:
            return True

        # Try without vendor prefix
        if "/" in plugin_id:
            short_id = plugin_id.split("/")[-1]
            if short_id in self.config.available_plugins:
                return True

        # Try category name
        if plugin_id.startswith("flyto-official/"):
            category = plugin_id.replace("flyto-official/", "")
            if category in self.config.available_plugins:
                return True
            if f"flyto-official_{category}" in self.config.available_plugins:
                return True

        return False

    def _is_plugin_healthy(self, plugin_id: str) -> bool:
        """Check if plugin is healthy."""
        # Default to healthy if not tracked
        return self._plugin_health.get(plugin_id, True)

    def _parse_module_id(self, module_id: str) -> tuple:
        """Parse module ID into plugin_id and step_id."""
        parts = module_id.split(".")
        if len(parts) >= 2:
            category = parts[0]
            step = ".".join(parts[1:])
            return (f"flyto-official/{category}", step)
        return (f"flyto-official/{module_id}", "execute")


# Global singleton
_router: Optional[ModuleRouter] = None


def get_router(config: Optional[RoutingConfig] = None) -> ModuleRouter:
    """Get global module router instance."""
    global _router
    if _router is None:
        _router = ModuleRouter(config)
    return _router


def reset_router():
    """Reset global router (for testing)."""
    global _router
    _router = None
