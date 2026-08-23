# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Atomic Utility Functions
Helper modules with no external dependencies
"""

import importlib

from .delay import *
from .random_number import *
from .random_string import *
from .datetime_now import *
from .hash_md5 import *

# `utility.not` lives in not.py, and no `from .not import *` can reach it: `not`
# is a keyword, so that line is a SyntaxError. The module was declared,
# documented and translated into every locale, and was never registered —
# `execute_module('utility.not', ...)` answered "Module not found". Importing it
# by name runs the decorator; nothing here needs its exported names.
importlib.import_module('.not', __name__)

__all__ = [
    # Utility modules will be auto-discovered by module registry
]
