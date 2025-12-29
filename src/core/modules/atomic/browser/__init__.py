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
from .record import *

__all__ = [
    # Browser modules will be auto-discovered by module registry
]
