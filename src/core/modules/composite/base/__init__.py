# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
