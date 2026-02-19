# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Composite Module Base Classes and Utilities

Re-exports all public APIs for backward compatibility.
"""

from .registry import CompositeRegistry
from .module import CompositeModule
from .decorator import register_composite
from .executor import CompositeExecutor
from ...types import UIVisibility

__all__ = [
    'CompositeRegistry',
    'CompositeModule',
    'register_composite',
    'CompositeExecutor',
    'UIVisibility',
]
