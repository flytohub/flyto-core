"""
Atomic Modules - Atomic Modules

Provides basic, composable operation units

Design Principles:
1. Single Responsibility - Each module does one thing
2. Completely Independent - Does not depend on other Atomic Modules
3. Composable - Can be freely combined to complete complex tasks
4. Testable - Each module can be tested independently

Implemented Atomic Modules:
- browser.find: Find elements in page
- element.query: Find child elements within element
- element.text: Get element text
- element.attribute: Get element attribute
"""

# Import element registry (utility for browser/element modules)
from .element_registry import (
    ElementRegistry,
    get_element_registry,
    create_element_registry,
    ELEMENT_REGISTRY_CONTEXT_KEY,
)

# Import module categories (all subdirectories with modules)
from . import array
from . import browser
from . import communication
from . import data
from . import database
from . import datetime
from . import document
from . import element
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

# New testing infrastructure modules
from . import shell
from . import http
from . import process
from . import port
from . import api

# AI vision and LLM modules
from . import vision
from . import ui
from . import llm

# HuggingFace AI modules
try:
    from . import huggingface
except ImportError:
    pass  # Optional: transformers/huggingface_hub not installed

# Legacy/helper imports
from . import analysis
from . import testing

# Re-export flow control modules
from .flow import LoopModule, BranchModule, SwitchModule, GotoModule

# Re-export element modules
from .element import ElementQueryModule, ElementTextModule, ElementAttributeModule

# Re-export browser find module
from .browser.find import BrowserFindModule

__all__ = [
    # Shell/Process/Port/API modules (testing infrastructure)
    'shell',
    'http',
    'process',
    'port',
    'api',
    # AI vision and LLM modules
    'vision',
    'ui',
    'llm',
    # Browser modules
    'BrowserFindModule',
    # Element modules
    'ElementQueryModule',
    'ElementTextModule',
    'ElementAttributeModule',
    # Element registry (context-aware pattern)
    'ElementRegistry',
    'get_element_registry',
    'create_element_registry',
    'ELEMENT_REGISTRY_CONTEXT_KEY',
    # Flow control modules
    'LoopModule',
    'BranchModule',
    'SwitchModule',
    'GotoModule',
]
