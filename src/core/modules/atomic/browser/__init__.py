# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Atomic Browser Operations
Browser automation modules using Playwright
"""

# Core browser operations
from .launch import *
from .goto import *
from .click import *
from .type import *
from .screenshot import *
from .wait import *
from .extract import *
from .press import *
from .close import *
from .find import *

# Smart session management (composable templates)
from .ensure import *
from .release import *

# New browser modules
from .console import *
from .scroll import *
from .hover import *
from .select import *
from .evaluate import *
from .cookies import *
from .storage import *
from .dialog import *
from .upload import *
from .download import *
from .frame import *
from .network import *
from .tab import *
from .pdf import *
from .drag import *
from .geolocation import *
from .navigation import *
from .record import *

# Higher-level browser operations (v2)
from .form import *
from .pagination import *
from .interact import *
from .readability import *
from .detect_list import *
from .challenge import *
from .response import *
from .table import *
from .extract_nested import *
from .cookies_file import *
from .pool import *
from .robots import *
from .sitemap import *
from .throttle import *
from .proxy_rotate import *
from .login import *
from .connect import *

# Performance & Debug modules (Chrome DevTools MCP compatible)
from .trace import *
from .performance import *
from .emulate import *
from .viewport import *
from .snapshot import *
from .pages import *
from .detect import *

__all__ = [
    # Browser modules will be auto-discovered by module registry
]
