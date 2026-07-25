# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Atomic Reverse-Engineering Operations

Phase 1: interactive JS debugger built on Chrome DevTools Protocol (CDP)
Debugger domain. Attach to a live page, inspect loaded scripts, set
breakpoints, pause execution, inspect call frames, evaluate expressions in
a paused scope, and step through code.

All modules in this category require the browser.debug permission (see
src/core/module_policy.py _DANGEROUS_PERMISSIONS) — evaluate_on_call_frame
can read in-memory locals/closures, and a paused debugger freezes the page.
"""

from .attach import *
from .detach import *
from .scripts import *
from .breakpoint import *
from .wait_paused import *
from .resume import *
from .step import *
from .call_frames import *
from .evaluate import *

__all__ = [
    # Reverse modules will be auto-discovered by module registry
]
