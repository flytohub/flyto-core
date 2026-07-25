# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Atomic Reverse-Engineering Operations

Phase 1: interactive JS debugger built on Chrome DevTools Protocol (CDP)
Debugger domain. Attach to a live page, inspect loaded scripts, set
breakpoints, pause execution, inspect call frames, evaluate expressions in
a paused scope, and step through code.

Phase 2: function hooking (Page domain), network-initiator tracing, and
WebSocket capture (Network domain) — all sharing the same CDP session that
reverse.attach creates, so Debugger stays enabled and initiator stacks stay
rich.

Phase 3: reverse.code — beautify (jsbeautifier) and AST structural search
(tree-sitter) over a plain JS source string. Pure Python, no Node.js, no
browser/CDP access, so it carries none of the elevated risk the rest of this
category has and requires no permission (see DECISIONS.md). Real semantic
deobfuscation (control-flow-flattening reversal, string-array decoding)
remains a separate, later phase — see ROADMAP.md 0.5 (Phase 4).

Every other module in this category requires the browser.debug permission
(see src/core/module_policy.py _DANGEROUS_PERMISSIONS) — evaluate_on_call_frame,
hook records, and captured network/WebSocket traffic can all expose
in-memory secrets, and a paused debugger freezes the page.
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
from .hook import *
from .network import *
from .websocket import *
from .code import *

__all__ = [
    # Reverse modules will be auto-discovered by module registry
]
