"""
Atomic Modules - Community Edition

Provides basic, composable operation units for workflow automation.
This is the open-source (MIT) module set for flyto-core.

Design Principles:
1. Single Responsibility - Each module does one thing
2. Completely Independent - Does not depend on other Atomic Modules
3. Composable - Can be freely combined to complete complex tasks
4. Testable - Each module can be tested independently

Plugin System:
- This module provides a `register_all()` function for entry_points discovery
- flyto-modules-pro can extend with additional modules
- See: pyproject.toml [project.entry-points."flyto.modules"]
"""

_registered = False


def register_all():
    """
    Register all community atomic modules.

    This function is called by ModuleRegistry.discover_plugins() via entry_points.
    It imports all module categories, which triggers registration via @register_module.

    Usage in pyproject.toml:
        [project.entry-points."flyto.modules"]
        community = "core.modules.atomic:register_all"
    """
    global _registered
    if _registered:
        return

    # Import all module categories (triggers @register_module decorators)
    from . import array  # noqa: F401
    from . import browser  # noqa: F401
    from . import communication  # noqa: F401
    from . import data  # noqa: F401
    from . import database  # noqa: F401
    from . import datetime  # noqa: F401
    from . import document  # noqa: F401
    from . import element  # noqa: F401
    from . import file  # noqa: F401
    from . import flow  # noqa: F401
    from . import image  # noqa: F401
    from . import math  # noqa: F401
    from . import meta  # noqa: F401
    from . import object  # noqa: F401
    from . import string  # noqa: F401
    from . import training  # noqa: F401
    from . import utility  # noqa: F401
    from . import vector  # noqa: F401

    # Testing infrastructure modules
    from . import shell  # noqa: F401
    from . import http  # noqa: F401
    from . import process  # noqa: F401
    from . import port  # noqa: F401
    from . import api  # noqa: F401

    # AI vision and LLM modules
    from . import vision  # noqa: F401
    from . import ui  # noqa: F401
    from . import llm  # noqa: F401
    from . import ai  # noqa: F401

    # HuggingFace AI modules (optional dependency)
    try:
        from . import huggingface  # noqa: F401
    except ImportError:
        pass  # Optional: transformers/huggingface_hub not installed

    # Legacy/helper imports
    from . import analysis  # noqa: F401
    from . import testing  # noqa: F401

    # Notification and storage modules
    from . import notification  # noqa: F401
    from . import storage  # noqa: F401
    from . import compare  # noqa: F401

    # New atomic modules (v2)
    from . import validate  # noqa: F401
    from . import encode  # noqa: F401
    from . import text  # noqa: F401
    from . import path  # noqa: F401
    from . import format  # noqa: F401
    from . import logic  # noqa: F401
    from . import set  # noqa: F401

    # New atomic modules (v3)
    from . import hash  # noqa: F401
    from . import random  # noqa: F401
    from . import convert  # noqa: F401
    from . import regex  # noqa: F401

    # New atomic modules (v4)
    from . import stats  # noqa: F401
    from . import check  # noqa: F401
    from . import crypto  # noqa: F401

    # Template as Node
    from . import template  # noqa: F401

    # Error handling modules (v5)
    from . import error  # noqa: F401

    # Design verification modules (v6)
    from . import verify  # noqa: F401

    _registered = True


# Auto-register on import (backwards compatibility)
register_all()


# Re-exports for direct access (backwards compatibility)
from .element_registry import (
    ElementRegistry,
    get_element_registry,
    create_element_registry,
    ELEMENT_REGISTRY_CONTEXT_KEY,
)

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
from . import shell
from . import http
from . import process
from . import port
from . import api
from . import vision
from . import ui
from . import llm
from . import ai
from . import analysis
from . import testing
from . import notification
from . import storage
from . import compare

# New atomic modules (v2)
from . import validate
from . import encode
from . import text
from . import path
from . import format
from . import logic
from . import set

# New atomic modules (v3)
from . import hash
from . import random
from . import convert
from . import regex

# New atomic modules (v4)
from . import stats
from . import check
from . import crypto

# Template as Node
from . import template

# Error handling modules (v5)
from . import error

# Design verification modules (v6)
from . import verify

# Re-export flow control modules
from .flow import LoopModule, BranchModule, SwitchModule, GotoModule

# Re-export element modules
from .element import ElementQueryModule, ElementTextModule, ElementAttributeModule

# Re-export browser find module
from .browser.find import BrowserFindModule

__all__ = [
    # Plugin registration function
    'register_all',
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
    'ai',
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
    # New atomic modules (v2)
    'validate',
    'encode',
    'text',
    'path',
    'format',
    'logic',
    'set',
    # New atomic modules (v3)
    'hash',
    'random',
    'convert',
    'regex',
    # New atomic modules (v4)
    'stats',
    'check',
    'crypto',
    # Template as Node
    'template',
    # Error handling modules (v5)
    'error',
    # Design verification modules (v6)
    'verify',
]
