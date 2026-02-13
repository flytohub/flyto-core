"""
Composite Module Registry

Manages registration and lookup of composite modules.
"""
import logging
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from ...types import StabilityLevel, is_module_visible, get_current_env

if TYPE_CHECKING:
    from .module import CompositeModule


logger = logging.getLogger(__name__)


class CompositeRegistry:
    """
    Registry for Composite Modules (Level 3)

    Manages high-level workflow templates that combine multiple atomic modules.
    """

    _instance = None
    _composites: Dict[str, Type['CompositeModule']] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls,
        module_id: str,
        module_class: Type['CompositeModule'],
        metadata: Dict[str, Any]
    ):
        """Register a composite module"""
        cls._composites[module_id] = module_class
        cls._metadata[module_id] = metadata
        logger.debug(f"Composite module registered: {module_id}")

    @classmethod
    def get(cls, module_id: str) -> Type['CompositeModule']:
        """Get composite module class by ID"""
        if module_id not in cls._composites:
            raise ValueError(f"Composite module not found: {module_id}")
        return cls._composites[module_id]

    @classmethod
    def has(cls, module_id: str) -> bool:
        """Check if composite module exists"""
        return module_id in cls._composites

    @classmethod
    def module_count(cls) -> int:
        """Get number of registered composite modules"""
        return len(cls._composites)

    @classmethod
    def clear(cls):
        """Clear all registered composites and metadata (for hot-reload)"""
        cls._composites.clear()
        cls._metadata.clear()
        logger.debug("Composite registry cleared")

    @classmethod
    def list_all(
        cls,
        filter_by_stability: bool = False,
        env: Optional[str] = None
    ) -> Dict[str, Type['CompositeModule']]:
        """
        List all registered composite modules

        Args:
            filter_by_stability: If True, filter by stability level
            env: Environment override
        """
        if not filter_by_stability:
            return cls._composites.copy()

        current_env = env or get_current_env()
        result = {}

        for module_id, module_class in cls._composites.items():
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
    def get_metadata(cls, module_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a composite module"""
        return cls._metadata.get(module_id)

    @classmethod
    def get_all_metadata(
        cls,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        filter_by_stability: bool = True,
        env: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all composite metadata with optional filtering

        Args:
            category: Filter by category
            tags: Filter by tags
            filter_by_stability: If True, filter by stability level
            env: Environment override
        """
        result = {}
        current_env = env or get_current_env()

        for module_id, metadata in cls._metadata.items():
            # Filter by stability
            if filter_by_stability:
                stability_str = metadata.get('stability', 'stable')
                try:
                    stability = StabilityLevel(stability_str)
                except ValueError:
                    stability = StabilityLevel.STABLE
                if not is_module_visible(stability, current_env):
                    continue

            if category and metadata.get('category') != category:
                continue

            if tags:
                module_tags = metadata.get('tags', [])
                if not any(tag in module_tags for tag in tags):
                    continue

            result[module_id] = metadata

        return result

    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """Get composite registry statistics"""
        all_composites = cls._metadata

        categories = {}
        for module_id, metadata in all_composites.items():
            cat = metadata.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_composites": len(all_composites),
            "categories": categories,
            "total_categories": len(categories)
        }
