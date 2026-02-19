# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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

# All module category names (alphabetical)
_ALL_CATEGORIES = [
    'ai', 'analysis', 'archive', 'array',
    'browser', 'cache', 'check', 'communication', 'compare', 'convert', 'crypto',
    'data', 'database', 'datetime', 'dns', 'docker', 'document',
    'element', 'encode', 'env', 'error',
    'file', 'flow', 'format',
    'git', 'graphql',
    'hash', 'http',
    'image',
    'k8s', 'llm', 'logic',
    'markdown', 'math', 'meta', 'monitor',
    'network', 'notification',
    'object', 'output',
    'path', 'port', 'process',
    'queue', 'random', 'regex',
    'sandbox', 'scheduler', 'set', 'shell', 'stats', 'storage', 'string',
    'template', 'testing', 'text', 'training',
    'ui', 'utility',
    'validate', 'vector', 'verify', 'vision',
]

_OPTIONAL_CATEGORIES = ['huggingface', 'ssh']


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

    import importlib
    for name in _ALL_CATEGORIES:
        importlib.import_module(f'.{name}', __package__)

    for name in _OPTIONAL_CATEGORIES:
        try:
            importlib.import_module(f'.{name}', __package__)
        except ImportError:
            pass

    _registered = True


# Auto-register on import
register_all()

# Re-exports for direct attribute access (modules already in sys.modules)
from . import (  # noqa: F401
    ai, analysis, archive, array,
    browser, cache, check, communication, compare, convert, crypto,
    data, database, datetime, dns, docker, document,
    element, encode, env, error,
    file, flow, format,
    git, graphql,
    hash, http,
    image,
    k8s, llm, logic,
    markdown, math, meta, monitor,
    network, notification,
    object, output,
    path, port, process,
    queue, random, regex,
    sandbox, scheduler, set, shell, stats, storage, string,
    template, testing, text, training,
    ui, utility,
    validate, vector, verify, vision,
)

# Re-export element registry
from .element_registry import (
    ElementRegistry,
    get_element_registry,
    create_element_registry,
    ELEMENT_REGISTRY_CONTEXT_KEY,
)

# Re-export flow control modules
from .flow import LoopModule, BranchModule, SwitchModule, GotoModule

# Re-export element modules
from .element import ElementQueryModule, ElementTextModule, ElementAttributeModule

# Re-export browser find module
from .browser.find import BrowserFindModule

__all__ = [
    'register_all',
    *_ALL_CATEGORIES,
    'ElementRegistry', 'get_element_registry', 'create_element_registry',
    'ELEMENT_REGISTRY_CONTEXT_KEY',
    'LoopModule', 'BranchModule', 'SwitchModule', 'GotoModule',
    'ElementQueryModule', 'ElementTextModule', 'ElementAttributeModule',
    'BrowserFindModule',
]
