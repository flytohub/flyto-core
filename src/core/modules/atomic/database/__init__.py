"""
Database modules
"""
try:
    from .query import *
except ImportError:
    pass
try:
    from .insert import *
except ImportError:
    pass
try:
    from .update import *
except ImportError:
    pass
