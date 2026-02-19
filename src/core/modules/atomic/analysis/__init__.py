# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Analysis Modules - HTML and Data Analysis

Modules for website and data structure analysis
"""

# Import all analysis modules to ensure registration
try:
    from .structure import *
except ImportError:
    pass

try:
    from .find_patterns import *
except ImportError:
    pass

try:
    from .extract_tables import *
except ImportError:
    pass

try:
    from .extract_forms import *
except ImportError:
    pass

try:
    from .extract_metadata import *
except ImportError:
    pass

try:
    from .analyze_readability import *
except ImportError:
    pass

try:
    from . import html
except ImportError:
    pass

__all__ = []
