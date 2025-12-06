"""
Atomic Browser Operations
Browser automation modules using Playwright
"""

from .launch import *
from .goto import *
from .click import *
from .type import *
from .screenshot import *
from .wait import *
from .extract import *
from .press import *
from .close import *

__all__ = [
    # Browser modules will be auto-discovered by module registry
]
