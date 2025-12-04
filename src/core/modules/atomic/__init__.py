"""
Atomic Modules - Atomic Modules

Provides basic, composable operation units

Design Principles:
1. Single Responsibility - Each module does one thing
2. Completely Independent - Does not depend on otherAtomic Modules
3. Composable - Can be freely combined to complete complex tasks
4. Testable - Each module can be tested independently

ImplementedAtomic Modules:
- browser.find: Find elements in page
- element.query: Find child elements within element
- element.text: Get element text
- element.attribute: Get element attribute
"""

# Import all atomic modules, trigger @register_module decorator
from .browser_find import BrowserFindModule
from .element_ops import (
    ElementQueryModule,
    ElementTextModule,
    ElementAttributeModule
)
from .loop import LoopModule
from .element_registry import ElementRegistry

# Import new atomic module categories
from . import file
from . import string
from . import array
from . import math
from . import datetime
from . import object
from . import meta_operations
from . import test_utilities
from . import meta
from . import training
from . import analysis
from . import competition
from . import image_modules  # Image processing modules
from . import browser_aliases  # Browser module aliases

__all__ = [
    'BrowserFindModule',
    'ElementQueryModule',
    'ElementTextModule',
    'ElementAttributeModule',
    'LoopModule',
    'ElementRegistry',
]
