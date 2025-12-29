"""
Composite Module Registry

Manages registration and lookup of composite modules.
"""
import logging
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

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
    def list_all(cls) -> Dict[str, Type['CompositeModule']]:
        """List all registered composite modules"""
        return cls._composites.copy()

    @classmethod
    def get_metadata(cls, module_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a composite module"""
        return cls._metadata.get(module_id)

    @classmethod
    def get_all_metadata(
        cls,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Get all composite metadata with optional filtering"""
        result = {}

        for module_id, metadata in cls._metadata.items():
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
