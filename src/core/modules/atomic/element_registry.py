"""
Element Registry - Manage Playwright Element references
Used to pass elements between stepsInstead of passing entire element object
"""
import uuid
from typing import Dict, Optional, Any

class ElementRegistry:
    """
    Element Registry - Singleton Pattern

    functionality
    1. Store Playwright ElementHandle references
    2. Manage element lifecycle via UUID
    3. Avoid serialization issues
    """

    _instance = None
    _elements: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._elements = {}
        return cls._instance

    @classmethod
    def register(cls, element: Any) -> str:
        """
        Register element and return UUID

        Args:
            element: Playwright ElementHandle

        Returns:
            element_id: UUID String
        """
        element_id = str(uuid.uuid4())
        cls._elements[element_id] = element
        return element_id

    @classmethod
    def register_many(cls, elements: list) -> list:
        """
        Register multiple elements

        Args:
            elements: ElementHandle list

        Returns:
            element_ids: UUID list
        """
        return [cls.register(elem) for elem in elements]

    @classmethod
    def get(cls, element_id: str) -> Optional[Any]:
        """
        Getelement

        Args:
            element_id: UUID

        Returns:
            element: ElementHandle or None
        """
        return cls._elements.get(element_id)

    @classmethod
    def remove(cls, element_id: str) -> bool:
        """
        Remove element reference

        Args:
            element_id: UUID

        Returns:
            success: Whether successfully removed
        """
        if element_id in cls._elements:
            del cls._elements[element_id]
            return True
        return False

    @classmethod
    def clear(cls):
        """Clear all element references"""
        cls._elements.clear()

    @classmethod
    def count(cls) -> int:
        """Return the number of currently stored elements"""
        return len(cls._elements)
