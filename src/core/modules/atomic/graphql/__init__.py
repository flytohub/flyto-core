# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
