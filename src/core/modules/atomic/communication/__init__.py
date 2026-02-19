# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

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
