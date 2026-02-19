# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Atomic GraphQL Operations
Execute GraphQL queries and mutations.
"""

try:
    from .query import *
except ImportError:
    pass

try:
    from .mutation import *
except ImportError:
    pass

__all__ = []
