"""
Module Registry - Core Registration and Lookup

Manages all registered modules and their metadata.
"""
# Registry version for sync tracking
REGISTRY_VERSION = "1.0.4"

import logging
from typing import Dict, Type, Any, Optional, List

from ..base import BaseModule
from ...constants import ErrorMessages
from .localization import get_localized_value
from ..types import StabilityLevel, is_module_visible, get_current_env


logger = logging.getLogger(__name__)


class ModuleRegistry:
    """
    Module Registry - Singleton Pattern

    Manages all registered modules and their metadata.
    Provides querying, filtering, and execution capabilities.
    """

    _instance = None
    _modules: Dict[str, Type[BaseModule]] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

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
