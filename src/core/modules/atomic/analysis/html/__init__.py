"""
Atomic HTML Analysis Operations
"""

try:
    from ..structure import *
except ImportError:
    pass

try:
    from ..find_patterns import *
except ImportError:
    pass

try:
    from ..extract_tables import *
except ImportError:
    pass

try:
    from ..extract_forms import *
except ImportError:
    pass

try:
    from ..extract_metadata import *
except ImportError:
    pass

try:
    from ..analyze_readability import *
except ImportError:
    pass

__all__ = []
