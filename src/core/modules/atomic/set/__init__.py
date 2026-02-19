# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Atomic Set Operations
Union, intersection, difference, and unique operations
"""

try:
    from .union import *
except ImportError:
    pass

try:
    from .intersection import *
except ImportError:
    pass

try:
    from .difference import *
except ImportError:
    pass

try:
    from .unique import *
except ImportError:
    pass

__all__ = []
