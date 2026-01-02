"""
Flyto Core Catalog API

Module catalog for LLM consumption.
Three-layer structure: Outline -> Category -> Module

Usage:
    from core.catalog import (
        get_outline,
        get_category_detail,
        get_module_detail,
    )
"""

from .outline import get_outline, get_categories
from .category import get_category_detail
from .module import get_module_detail, get_modules_batch

__all__ = [
    # Outline (Layer 1)
    'get_outline',
    'get_categories',

    # Category (Layer 2)
    'get_category_detail',

    # Module (Layer 3)
    'get_module_detail',
    'get_modules_batch',
]
