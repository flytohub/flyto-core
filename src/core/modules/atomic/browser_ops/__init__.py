"""
Atomic Browser Operations
Core browser automation modules with no external dependencies

NOTE: This module has been refactored. Browser modules are now in ../browser/
This file provides backward compatibility by importing from the new location.
"""

from ..browser import *

__all__ = [
    # Browser modules will be auto-discovered by module registry
]
