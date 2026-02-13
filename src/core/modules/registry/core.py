"""
Module Registry - Core Registration and Lookup

Manages all registered modules and their metadata.
Supports plugin discovery via entry_points for Open Core architecture.
"""
# Registry version for sync tracking
REGISTRY_VERSION = "1.0.5"

import logging
import hashlib
import sys
from typing import Dict, Type, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from ..base import BaseModule
from ...constants import ErrorMessages
from ..types import (
    StabilityLevel,
    ModuleTier,
    TIER_DISPLAY_ORDER,
    is_module_visible,
    get_current_env,
)


@dataclass
class PluginInfo:
    """Information about a discovered plugin package"""
    name: str
    version: str
    module_count: int
    loaded_at: datetime = field(default_factory=datetime.now)
    entry_point: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "module_count": self.module_count,
            "loaded_at": self.loaded_at.isoformat(),
            "entry_point": self.entry_point
        }


@dataclass
class RegistrySnapshot:
    """Snapshot of registry state for execution version binding"""
    registry_version: str
    plugins: Dict[str, str]  # plugin_name -> version
    module_count: int
    modules_hash: str
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry_version": self.registry_version,
            "plugins": self.plugins,
            "module_count": self.module_count,
            "modules_hash": self.modules_hash,
            "created_at": self.created_at.isoformat()
        }


def get_localized_value(value: Any, lang: str = 'en') -> str:
    """
    Extract localized string from value.

    Stub implementation - actual translations provided by flyto-i18n.
    Supports:
    1. String: returns as-is
    2. Dict: {"en": "...", "zh": "...", "ja": "..."}
    """
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        if lang in value:
            return value[lang]
        if 'en' in value:
            return value['en']
        return next(iter(value.values())) if value else ''
    return str(value) if value else ''


logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    Module Registry - Singleton Pattern

    Manages all registered modules and their metadata.
    Provides querying, filtering, and execution capabilities.

    Supports plugin discovery via entry_points:
    - flyto-core registers 'community' modules
    - flyto-modules-pro can register 'pro' modules
    - Any package can add modules via entry_points
    """

    _instance = None
    _modules: Dict[str, Type[BaseModule]] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}
    _plugins: Dict[str, PluginInfo] = {}
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, module_id: str, module_class: Type[BaseModule], metadata: Optional[Dict[str, Any]] = None):
        """
        Register a module

        Args:
            module_id: Unique module identifier (e.g., "browser.goto")
            module_class: Module class inheriting from BaseModule
            metadata: Module metadata (optional)
        """
        cls._modules[module_id] = module_class
        if metadata:
            # Ensure required fields
            metadata.setdefault('module_id', module_id)
            metadata.setdefault('version', '1.0.0')
            metadata.setdefault('category', module_id.split('.')[0])
            metadata.setdefault('tags', [])
            cls._metadata[module_id] = metadata
        logger.debug(f"Module registered: {module_id}")

    @classmethod
    def unregister(cls, module_id: str):
        """Remove a module from registry"""
        if module_id in cls._modules:
            del cls._modules[module_id]
            if module_id in cls._metadata:
                del cls._metadata[module_id]
            logger.debug(f"Module unregistered: {module_id}")

    @classmethod
    def get(cls, module_id: str) -> Type[BaseModule]:
        """
        Get module class by ID

        Args:
            module_id: Module identifier

        Returns:
            Module class

        Raises:
            ValueError: If module not found
        """
        if module_id not in cls._modules:
            raise ValueError(
                ErrorMessages.format(
                    ErrorMessages.MODULE_NOT_FOUND,
                    module_id=module_id
                )
            )
        return cls._modules[module_id]

    @classmethod
    def has(cls, module_id: str) -> bool:
        """Check if module exists"""
        return module_id in cls._modules

    @classmethod
    def module_count(cls) -> int:
        """Get number of registered modules"""
        return len(cls._modules)

    @classmethod
    def clear(cls):
        """Clear all registered modules and metadata (for hot-reload)"""
        cls._modules.clear()
        cls._metadata.clear()
        cls._plugins.clear()
        cls._initialized = False
        logger.debug("Registry cleared")

    @classmethod
    def list_all(
        cls,
        filter_by_stability: bool = False,
        env: Optional[str] = None
    ) -> Dict[str, Type[BaseModule]]:
        """
        List all registered module classes

        Args:
            filter_by_stability: If True, filter by stability level based on environment
            env: Environment override (production/staging/development/local)

        Returns:
            Dict of module_id -> module class
        """
        if not filter_by_stability:
            return cls._modules.copy()

        current_env = env or get_current_env()
        result = {}

        for module_id, module_class in cls._modules.items():
            metadata = cls._metadata.get(module_id, {})
            stability_str = metadata.get('stability', 'stable')
            try:
                stability = StabilityLevel(stability_str)
            except ValueError:
                stability = StabilityLevel.STABLE

            if is_module_visible(stability, current_env):
                result[module_id] = module_class

        return result

    @classmethod
    def get_all_metadata(
        cls,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all module metadata (with optional filtering)

        Args:
            category: Filter by category (e.g., "browser", "data")
            tags: Filter by tags (module must have at least one matching tag)
            lang: Language code for localized fields
            filter_by_stability: If True, filter modules by stability level based on environment
            env: Environment override (production/staging/development/local), defaults to FLYTO_ENV

        Returns:
            Dict of module_id -> metadata
        """
        result = {}
        current_env = env or get_current_env()

        for module_id, metadata in cls._metadata.items():
            # Filter by stability (environment-aware)
            if filter_by_stability:
                stability_str = metadata.get('stability', 'stable')
                try:
                    stability = StabilityLevel(stability_str)
                except ValueError:
                    stability = StabilityLevel.STABLE
                if not is_module_visible(stability, current_env):
                    continue

            # Filter by category
            if category and metadata.get('category') != category:
                continue

            # Filter by tags
            if tags:
                module_tags = metadata.get('tags', [])
                if not any(tag in module_tags for tag in tags):
                    continue

            # Localize fields
            localized_metadata = cls._localize_metadata(metadata, lang)
            result[module_id] = localized_metadata

        return result

    @classmethod
    def get_metadata(cls, module_id: str, lang: str = 'en') -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific module

        Args:
            module_id: Module identifier
            lang: Language code

        Returns:
            Localized metadata or None if not found
        """
        metadata = cls._metadata.get(module_id)
        if not metadata:
            return None
        return cls._localize_metadata(metadata, lang)

    @classmethod
    def _localize_metadata(cls, metadata: Dict[str, Any], lang: str) -> Dict[str, Any]:
        """
        Localize metadata fields based on language

        Fields that support i18n: label, description, and nested labels in params_schema
        """
        result = metadata.copy()

        # Localize top-level fields
        if 'label' in result:
            result['label'] = get_localized_value(result['label'], lang)
        if 'description' in result:
            result['description'] = get_localized_value(result['description'], lang)

        # Localize params_schema labels
        if 'params_schema' in result:
            params = result['params_schema'].copy()
            for param_name, param_def in params.items():
                if isinstance(param_def, dict):
                    param_copy = param_def.copy()
                    if 'label' in param_copy:
                        param_copy['label'] = get_localized_value(param_copy['label'], lang)
                    if 'description' in param_copy:
                        param_copy['description'] = get_localized_value(param_copy['description'], lang)
                    if 'placeholder' in param_copy:
                        param_copy['placeholder'] = get_localized_value(param_copy['placeholder'], lang)

                    # Localize select options
                    if 'options' in param_copy and isinstance(param_copy['options'], list):
                        localized_options = []
                        for opt in param_copy['options']:
                            if isinstance(opt, dict) and 'label' in opt:
                                opt_copy = opt.copy()
                                opt_copy['label'] = get_localized_value(opt['label'], lang)
                                localized_options.append(opt_copy)
                            else:
                                localized_options.append(opt)
                        param_copy['options'] = localized_options

                    params[param_name] = param_copy
            result['params_schema'] = params

        return result

    @classmethod
    async def execute(cls, module_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute a module

        Args:
            module_id: Module identifier
            params: Parameters to pass to module
            context: Execution context (shared state, browser instance, etc.)

        Returns:
            Module execution result
        """
        module_class = cls.get(module_id)
        module_instance = module_class(params, context)
        return await module_instance.execute()

    # ========================================
    # Plugin Discovery (Open Core Architecture)
    # ========================================

    @classmethod
    def discover_plugins(cls, force: bool = False) -> Dict[str, PluginInfo]:
        """
        Discover and load module plugins via entry_points.

        Uses Python's entry_points mechanism to find packages that provide
        flyto modules. Each plugin package should define:

            [project.entry-points."flyto.modules"]
            plugin_name = "package.module:register_all"

        The register_all function should call ModuleRegistry.register()
        for each module it provides.

        Args:
            force: If True, reload all plugins even if already initialized

        Returns:
            Dict of plugin_name -> PluginInfo
        """
        if cls._initialized and not force:
            return cls._plugins

        # Python 3.9+ uses importlib.metadata
        if sys.version_info >= (3, 10):
            from importlib.metadata import entry_points, version as get_version
            eps = entry_points(group='flyto.modules')
        else:
            from importlib.metadata import entry_points, version as get_version
            all_eps = entry_points()
            eps = all_eps.get('flyto.modules', [])

        for ep in eps:
            try:
                # Track module count before loading
                count_before = len(cls._modules)

                # Load the register_all function and call it
                register_func = ep.load()
                if callable(register_func):
                    register_func()

                # Track module count after loading
                count_after = len(cls._modules)
                modules_added = count_after - count_before

                # Get package version
                try:
                    pkg_version = get_version(ep.value.split(':')[0].split('.')[0])
                except Exception:
                    pkg_version = "unknown"

                # Record plugin info
                cls._plugins[ep.name] = PluginInfo(
                    name=ep.name,
                    version=pkg_version,
                    module_count=modules_added,
                    entry_point=f"{ep.value}"
                )

                logger.info(f"Plugin loaded: {ep.name} ({modules_added} modules, v{pkg_version})")

            except Exception as e:
                logger.error(f"Failed to load plugin {ep.name}: {e}")

        cls._initialized = True
        return cls._plugins

    @classmethod
    def refresh(cls) -> Dict[str, PluginInfo]:
        """
        Refresh the registry by re-discovering all plugins.

        This is used for hot-update scenarios where packages have been
        updated via pip. Note: This does NOT reload already-imported
        Python modules. For true hot-reload, the worker process should
        be restarted.

        Returns:
            Dict of plugin_name -> PluginInfo
        """
        logger.info("Refreshing module registry...")

        # Clear existing state
        cls._modules.clear()
        cls._metadata.clear()
        cls._plugins.clear()
        cls._initialized = False

        # Re-discover plugins
        return cls.discover_plugins(force=True)

    @classmethod
    def get_snapshot(cls) -> RegistrySnapshot:
        """
        Get a snapshot of current registry state.

        Used for execution version binding - each workflow execution
        should record the registry snapshot to ensure checkpoint/resume
        uses the same module versions.

        Returns:
            RegistrySnapshot with version info and module hash
        """
        # Ensure plugins are discovered
        if not cls._initialized:
            cls.discover_plugins()

        # Build plugins version dict
        plugins = {name: info.version for name, info in cls._plugins.items()}

        # Calculate modules hash (for detecting changes)
        module_ids = sorted(cls._modules.keys())
        hash_input = "|".join(module_ids)
        modules_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]

        return RegistrySnapshot(
            registry_version=REGISTRY_VERSION,
            plugins=plugins,
            module_count=len(cls._modules),
            modules_hash=modules_hash
        )

    @classmethod
    def get_plugins(cls) -> Dict[str, PluginInfo]:
        """Get information about all loaded plugins"""
        if not cls._initialized:
            cls.discover_plugins()
        return cls._plugins.copy()

    @classmethod
    def is_plugin_loaded(cls, plugin_name: str) -> bool:
        """Check if a specific plugin is loaded"""
        return plugin_name in cls._plugins

    @classmethod
    def get_plugin_modules(cls, plugin_name: str) -> List[str]:
        """
        Get list of module IDs provided by a specific plugin.

        Note: This requires modules to have 'plugin' in their metadata.
        """
        if not cls._initialized:
            cls.discover_plugins()

        return [
            module_id
            for module_id, metadata in cls._metadata.items()
            if metadata.get('plugin') == plugin_name
        ]

    # ========================================
    # Catalog Service (Frontend API)
    # ========================================

    @classmethod
    def get_catalog(
        cls,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None,
        include_internal: bool = False,
    ) -> Dict[str, Any]:
        """
        Get module catalog grouped by tier for frontend display.

        Returns a structured catalog optimized for node picker dialogs:
        - Modules grouped by tier (featured, standard, toolkit)
        - Within each tier, grouped by category
        - Sorted by tier display order

        Args:
            lang: Language code for localization
            filter_by_stability: Filter modules by stability/environment
            env: Environment override
            include_internal: Include INTERNAL tier modules (default False)

        Returns:
            {
                "tiers": [
                    {
                        "id": "featured",
                        "label": "Featured",
                        "display_order": 1,
                        "categories": [
                            {
                                "id": "browser",
                                "label": "Browser",
                                "modules": [...]
                            }
                        ]
                    },
                    ...
                ],
                "total_count": 305,
                "tier_counts": {"featured": 10, "standard": 200, "toolkit": 95}
            }
        """
        # Get all visible metadata
        all_metadata = cls.get_all_metadata(
            lang=lang,
            filter_by_stability=filter_by_stability,
            env=env,
        )

        # Group by tier
        tier_groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        tier_counts: Dict[str, int] = {}

        for module_id, metadata in all_metadata.items():
            tier_value = metadata.get('tier', 'standard')

            # Skip internal unless explicitly requested
            if tier_value == 'internal' and not include_internal:
                continue

            category = metadata.get('category', 'other')

            if tier_value not in tier_groups:
                tier_groups[tier_value] = {}
                tier_counts[tier_value] = 0

            if category not in tier_groups[tier_value]:
                tier_groups[tier_value][category] = []

            tier_groups[tier_value][category].append(metadata)
            tier_counts[tier_value] += 1

        # Build structured response
        tiers = []
        for tier_enum in ModuleTier:
            tier_value = tier_enum.value
            if tier_value not in tier_groups:
                continue
            if tier_value == 'internal' and not include_internal:
                continue

            categories = []
            for cat_id, modules in sorted(tier_groups[tier_value].items()):
                categories.append({
                    "id": cat_id,
                    "label": cat_id.replace('_', ' ').title(),
                    "modules": sorted(modules, key=lambda m: m.get('ui_label', m.get('module_id', ''))),
                })

            tiers.append({
                "id": tier_value,
                "label": tier_value.replace('_', ' ').title(),
                "display_order": TIER_DISPLAY_ORDER.get(tier_enum, 99),
                "categories": categories,
            })

        # Sort tiers by display order
        tiers.sort(key=lambda t: t['display_order'])

        return {
            "tiers": tiers,
            "total_count": sum(tier_counts.values()),
            "tier_counts": tier_counts,
        }

    @classmethod
    def get_start_modules(
        cls,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get modules that can be used as workflow start nodes.

        Filters catalog to only include modules where can_be_start=True.

        Args:
            lang: Language code
            filter_by_stability: Filter by stability level
            env: Environment override

        Returns:
            Same structure as get_catalog() but filtered
        """
        all_metadata = cls.get_all_metadata(
            lang=lang,
            filter_by_stability=filter_by_stability,
            env=env,
        )

        # Group by tier, only include start-capable modules
        tier_groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        tier_counts: Dict[str, int] = {}

        for module_id, metadata in all_metadata.items():
            # Skip non-start modules
            if not metadata.get('can_be_start', False):
                continue

            tier_value = metadata.get('tier', 'standard')
            # Skip internal for start modules
            if tier_value == 'internal':
                continue

            category = metadata.get('category', 'other')

            if tier_value not in tier_groups:
                tier_groups[tier_value] = {}
                tier_counts[tier_value] = 0

            if category not in tier_groups[tier_value]:
                tier_groups[tier_value][category] = []

            tier_groups[tier_value][category].append(metadata)
            tier_counts[tier_value] += 1

        # Build structured response
        tiers = []
        for tier_enum in ModuleTier:
            tier_value = tier_enum.value
            if tier_value not in tier_groups:
                continue

            categories = []
            for cat_id, modules in sorted(tier_groups[tier_value].items()):
                categories.append({
                    "id": cat_id,
                    "label": cat_id.replace('_', ' ').title(),
                    "modules": sorted(modules, key=lambda m: m.get('ui_label', m.get('module_id', ''))),
                })

            tiers.append({
                "id": tier_value,
                "label": tier_value.replace('_', ' ').title(),
                "display_order": TIER_DISPLAY_ORDER.get(tier_enum, 99),
                "categories": categories,
            })

        tiers.sort(key=lambda t: t['display_order'])

        return {
            "tiers": tiers,
            "total_count": sum(tier_counts.values()),
            "tier_counts": tier_counts,
        }
