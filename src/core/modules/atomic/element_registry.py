"""
Element Registry - Manage Playwright Element references
Used to pass elements between steps instead of passing entire element object.

Architecture:
- Instance-based registry (not singleton) for testability and isolation
- Context-aware: can be passed through workflow context
- Factory function for getting registry from context
"""
import uuid
from typing import Dict, Optional, Any


# Context key for element registry
ELEMENT_REGISTRY_CONTEXT_KEY = '__element_registry__'


class ElementRegistry:
    """
    Element Registry - Instance-based Pattern

    Functionality:
    1. Store Playwright ElementHandle references
    2. Manage element lifecycle via UUID
    3. Avoid serialization issues

    Usage:
    - Create one registry per workflow execution
    - Pass through context using ELEMENT_REGISTRY_CONTEXT_KEY
    - Use get_element_registry(context) to retrieve
    """

    def __init__(self):
        """Initialize a new element registry instance."""
        self._elements: Dict[str, Any] = {}

    def register(self, element: Any) -> str:
        """
        Register element and return UUID.

        Args:
            element: Playwright ElementHandle

        Returns:
            element_id: UUID String
        """
        element_id = str(uuid.uuid4())
        self._elements[element_id] = element
        return element_id

    def register_many(self, elements: list) -> list:
        """
        Register multiple elements.

        Args:
            elements: ElementHandle list

        Returns:
            element_ids: UUID list
        """
        return [self.register(elem) for elem in elements]

    def get(self, element_id: str) -> Optional[Any]:
        """
        Get element by ID.

        Args:
            element_id: UUID

        Returns:
            element: ElementHandle or None
        """
        return self._elements.get(element_id)

    def remove(self, element_id: str) -> bool:
        """
        Remove element reference.

        Args:
            element_id: UUID

        Returns:
            success: Whether successfully removed
        """
        if element_id in self._elements:
            del self._elements[element_id]
            return True
        return False

    def clear(self):
        """Clear all element references."""
        self._elements.clear()

    def count(self) -> int:
        """Return the number of currently stored elements."""
        return len(self._elements)

    # ==========================================================================
    # Class methods for backward compatibility (deprecated)
    # ==========================================================================

    # Global instance for backward compatibility
    # WARNING: This will be removed in a future version
    _global_instance: Optional['ElementRegistry'] = None

    @classmethod
    def _get_global(cls) -> 'ElementRegistry':
        """Get or create global instance (for backward compatibility)."""
        if cls._global_instance is None:
            cls._global_instance = cls()
        return cls._global_instance

    @classmethod
    def register_global(cls, element: Any) -> str:
        """
        Register element using global instance (backward compatible).

        DEPRECATED: Use instance method or get_element_registry(context) instead.
        """
        return cls._get_global().register(element)

    @classmethod
    def register_many_global(cls, elements: list) -> list:
        """
        Register multiple elements using global instance (backward compatible).

        DEPRECATED: Use instance method or get_element_registry(context) instead.
        """
        return cls._get_global().register_many(elements)

    @classmethod
    def get_global(cls, element_id: str) -> Optional[Any]:
        """
        Get element from global instance (backward compatible).

        DEPRECATED: Use instance method or get_element_registry(context) instead.
        """
        return cls._get_global().get(element_id)

    @classmethod
    def remove_global(cls, element_id: str) -> bool:
        """
        Remove element from global instance (backward compatible).

        DEPRECATED: Use instance method or get_element_registry(context) instead.
        """
        return cls._get_global().remove(element_id)

    @classmethod
    def clear_global(cls):
        """
        Clear global instance (backward compatible).

        DEPRECATED: Use instance method or get_element_registry(context) instead.
        """
        cls._get_global().clear()

    @classmethod
    def count_global(cls) -> int:
        """
        Count elements in global instance (backward compatible).

        DEPRECATED: Use instance method or get_element_registry(context) instead.
        """
        return cls._get_global().count()


# =============================================================================
# Factory Functions
# =============================================================================

def get_element_registry(context: Dict[str, Any]) -> ElementRegistry:
    """
    Get or create element registry from context.

    This is the recommended way to access the element registry.
    It ensures each workflow execution has its own isolated registry.

    Args:
        context: Workflow execution context

    Returns:
        ElementRegistry instance for this context
    """
    if ELEMENT_REGISTRY_CONTEXT_KEY not in context:
        context[ELEMENT_REGISTRY_CONTEXT_KEY] = ElementRegistry()
    return context[ELEMENT_REGISTRY_CONTEXT_KEY]


def create_element_registry() -> ElementRegistry:
    """
    Create a new element registry instance.

    Use this when you need a fresh registry (e.g., for testing).

    Returns:
        New ElementRegistry instance
    """
    return ElementRegistry()
