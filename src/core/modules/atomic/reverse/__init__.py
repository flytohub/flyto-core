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

reverse.sourcemap strengthens Phase 1-3 rather than adding a new phase:
resolves a generated (minified/bundled) code location to its original
source file/line/column/name via a hand-rolled Source Map v3 VLQ decoder.
Session-independent and permission-free like reverse.code — it never
fetches an external .map file itself (that's a normal http.get step in the
calling workflow, already SSRF-guarded).

reverse.request_breakpoint strengthens Phase 1: pauses execution on a
matching XHR/fetch request via CDP's DOMDebugger domain, surfacing through
the same Debugger.paused event as a script breakpoint so wait_paused/resume/
get_call_frames/evaluate_on_call_frame all apply unchanged. reverse.attach
also gained session-snapshot reuse: reattaching to a page that already has
an enabled session returns its existing snapshot (script cache, breakpoints,
request breakpoints, hooks) instead of discarding it, unless force_new=True.

Phase 4: reverse.deobfuscate delivers real semantic deobfuscation
(control-flow-flattening reversal, string-array decoding, self-defending-code
bypass, webpack/browserify unpacking) via `webcrack`, run in a dedicated
Node.js sidecar worker (deobfuscate_worker/worker.mjs) rather than the
generic JSON-RPC plugin runtime (src/core/runtime/manager.py) or Playwright's
private/fragile bundled Node — see DECISIONS.md for why both of those were
rejected. Unlike reverse.code, webcrack unconditionally evaluates the input
inside its own isolated-vm sandbox, so this module requires the new
code.execute permission instead of being permission-free.

Every other module in this category requires the browser.debug permission
(see src/core/module_policy.py _DANGEROUS_PERMISSIONS) — evaluate_on_call_frame,
hook records, and captured network/WebSocket traffic can all expose
in-memory secrets, and a paused debugger freezes the page.
"""

from .attach import *
from .detach import *
from .scripts import *
from .breakpoint import *
from .request_breakpoint import *
from .wait_paused import *
from .resume import *
from .step import *
from .call_frames import *
from .evaluate import *
from .hook import *
from .network import *
from .websocket import *
from .code import *
from .sourcemap import *
from .deobfuscate import *

__all__ = [
    # Reverse modules will be auto-discovered by module registry
]
