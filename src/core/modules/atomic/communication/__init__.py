# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Communication modules
"""
try:
    from .email_send import *
except ImportError:
    pass
try:
    from .email_read import *
except ImportError:
    pass
try:
    from .slack_send import *
except ImportError:
    pass
try:
    from .webhook_trigger import *
except ImportError:
    pass
