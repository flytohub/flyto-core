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
from .element_registry import ElementRegistry

# Import module categories (all subdirectories with modules)
from . import api
from . import array
from . import browser
from . import browser_ops
from . import communication
from . import competition
from . import data
from . import database
from . import datetime
from . import document
from . import file
from . import flow
from . import image
from . import math
from . import meta
from . import object
from . import string
from . import training
from . import utility
from . import vector

# HuggingFace AI modules
try:
    from . import huggingface
except ImportError:
    pass  # Optional: transformers/huggingface_hub not installed

# Legacy/helper imports
from . import analysis
from . import browser_aliases
from . import image_modules
from . import meta_operations
from . import test_utilities

# Re-export flow control modules
from .flow import LoopModule, BranchModule, SwitchModule, GotoModule

__all__ = [
    'BrowserFindModule',
    'ElementQueryModule',
    'ElementTextModule',
    'ElementAttributeModule',
    'ElementRegistry',
    'LoopModule',
    'BranchModule',
    'SwitchModule',
    'GotoModule',
]
