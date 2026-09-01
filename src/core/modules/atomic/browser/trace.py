# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Trace Module - Performance tracing using CDP

Provides Chrome DevTools Protocol-level performance tracing.
Uses Playwright's browser.start_tracing() and browser.stop_tracing().

Note: This module only works with Chromium browsers.

START AND STOP ARE NOT THE SAME KIND OF ANSWER

``start`` returns ``"tracing": True`` and the categories it was handed. Both are
this file's own literals. Playwright exposes no way to ask a context whether
tracing is running, so there is nothing to read back and nothing to compare --
what is actually known is that ``context.tracing.start()`` round-tripped to the
browser and came back without raising. That is ACCEPTED, exactly: the other side
acknowledged taking it, not that it ran.

``stop`` is different, because it produces a file, and the file is read back
from the filesystem. ``size_bytes`` is the size of a trace zip Chromium wrote --
a number that cannot exist without the trace having been collected.

    stop, and the trace file is on disk                OBSERVED (size_bytes)
    stop, and nothing is at the path                   INDETERMINATE
    start, and Playwright accepted it                  ACCEPTED
    a precondition refused the call                    FAILED

THE FOUR REFUSALS ARE FAILED AND NOT INDETERMINATE. ``CHROMIUM_ONLY``,
``TRACING_ACTIVE``, ``NO_ACTIVE_TRACE`` and ``CDP_UNAVAILABLE`` all return
``status: "error"`` today with nothing a consumer can use to tell them from a
trace that might still be running. Each of them evaluated a real condition and
returned before anything was dispatched, so the effect definitively did not
happen -- that is FAILED, with ``claim_by=CALLER``, because the caller asked for
a trace and there is no trace. `outcome.py` reserves INDETERMINATE for the case
where the claim is our own inference and may be wrong; none of these is an
inference.

WHAT CHANGED IN THE PATH CASE, and why it is not only about the rung. It read
the whole trace back into memory -- ``trace_data = path.read_bytes()`` -- purely
to call ``len()`` on it, and a trace with screenshots is tens of megabytes. It
also had no branch for a missing file: ``read_bytes`` on a path Playwright did
not write raises ``FileNotFoundError`` out of a module that had already reported
success in its own local. ``os.stat`` answers the same question, costs nothing,
and gives the missing case somewhere to go. The base64 branch still reads the
bytes, because it returns them.

What OBSERVED does not say: a byte count is not a trace. A zip containing one
empty event stream is a valid, non-empty file.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


def _trace_started_outcome(*, categories: Any, screenshots: bool) -> Dict[str, Any]:
    """ACCEPTED for `start`. There is nothing to read back and nothing to compare."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'tracing_start_accepted',
            'categories': list(categories or []),
            'screenshots': bool(screenshots),
            'measured_by': None,
            'detail': (
                'context.tracing.start() returned without raising. The '
                '"tracing": True beside this is a literal in the module, not a '
                'reading: Playwright offers no way to ask a context whether '
                'tracing is running, so nothing followed the instruction into '
                'the browser. The trace file that stop() produces is the first '
                'evidence a trace was collected.'
            ),
        }],
    )


def _trace_stopped_outcome(
    *,
    bytes_on_disk: Optional[int],
    path: Optional[str],
    stat_error: Optional[str],
) -> Dict[str, Any]:
    """OBSERVED when the trace file is there, INDETERMINATE when it is not."""
    if bytes_on_disk is None:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'trace_file_missing',
                'path': path,
                'predicate': 'a trace file exists at the output path after tracing.stop()',
                'measured_by': 'os.stat() on the output path after context.tracing.stop()',
                'reason': stat_error or 'nothing is at the output path',
                'detail': (
                    'tracing.stop() returned without raising and there is no '
                    'file to measure. Indeterminate rather than failed: no '
                    'postcondition was declared about the path and something '
                    'outside this process may have moved it.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'trace_file_written',
            'path': path,
            'bytes_on_disk': bytes_on_disk,
            'measured_by': 'os.stat().st_size on the trace file after context.tracing.stop()',
            'detail': (
                'Size the filesystem reports for the archive Playwright wrote. '
                'A byte count is not a trace: a zip holding an empty event '
                'stream is a valid non-empty file.'
            ),
        }],
    )


def _trace_refused_outcome(*, action: str, error_code: str, reason: str) -> Dict[str, Any]:
    """FAILED for a precondition that returned before anything was dispatched."""
    return envelope(
        Outcome.FAILED,
        # CALLER: the caller asked for a trace and there is no trace. This is
        # not an inference of ours that might be wrong -- the module read the
        # condition and returned without touching the browser.
        claim_by=ClaimBy.CALLER,
        effects=[{
            'kind': 'tracing_refused',
            'action': action,
            'error_code': error_code,
            'reason': reason,
            'measured_by': 'the precondition named in error_code, evaluated before dispatch',
            'detail': (
                'Nothing was sent to the browser. This is a definite negative, '
                'not an unconfirmed positive: without it a consumer cannot tell '
                'a refused trace from one that may still be running.'
            ),
        }],
    )


def _stat_size(path: str) -> tuple:
    """``(st_size, None)`` when the file is there, ``(None, why)`` when it is not."""
    try:
        return os.stat(path).st_size, None
    except OSError as error:
        return None, f"{type(error).__name__}: {error.strerror or error}"


@register_module(
    module_id='browser.trace',
    version='1.0.0',
    category='browser',
    tags=['browser', 'performance', 'debug', 'trace', 'cdp', 'chromium'],
    label='Performance Trace',
    label_key='modules.browser.trace.label',
    description='Start/stop Chrome DevTools performance tracing (Chromium only)',
    description_key='modules.browser.trace.description',
    icon='Activity',
    color='#F97316',

    # Connection types
    input_types=['page'],
    output_types=['json', 'file'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field(
            'action',
            type='string',
            label='Action',
            label_key='modules.browser.trace.params.action.label',
            description='Start or stop tracing',
            required=True,
            options=[
                {'value': 'start', 'label': 'Start Tracing'},
                {'value': 'stop', 'label': 'Stop Tracing'},
            ],
        ),
        field(
            'categories',
            type='array',
            label='Trace Categories',
            label_key='modules.browser.trace.params.categories.label',
            description='CDP trace categories (default: devtools.timeline)',
            required=False,
            default=['devtools.timeline'],
            items={"type": "string"},
        ),
        field(
            'screenshots',
            type='boolean',
            label='Capture Screenshots',
            label_key='modules.browser.trace.params.screenshots.label',
            description='Include screenshots in trace (increases file size)',
            required=False,
            default=True,
        ),
        presets.OUTPUT_PATH(
            key='path',
            placeholder='/tmp/trace.json',
            label='Output Path',
            required=False,
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status (success/error)',
            'description_key': 'modules.browser.trace.output.status.description'
        },
        'tracing': {
            'type': 'boolean',
            'description': 'Whether tracing is active',
            'description_key': 'modules.browser.trace.output.tracing.description'
        },
        'path': {
            'type': 'string',
            'description': 'Path to trace file (when stopped)',
            'description_key': 'modules.browser.trace.output.path.description'
        },
        'size_bytes': {
            'type': 'number',
            'description': 'Trace file size in bytes',
            'description_key': 'modules.browser.trace.output.size_bytes.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed. Decided per return: stop is '
                '"observed" when the trace file is on disk and "indeterminate" '
                'when it is not; start is only "accepted" because nothing can '
                'be read back; a refused call is "failed".'
            ),
            'description_key': 'modules.browser.trace.output.outcome.description'
        },
    },
    examples=[
        {
            'name': 'Start tracing with screenshots',
            'params': {'action': 'start', 'screenshots': True}
        },
        {
            'name': 'Start tracing specific categories',
            'params': {
                'action': 'start',
                'categories': ['devtools.timeline', 'v8.execute'],
                'screenshots': False
            }
        },
        {
            'name': 'Stop tracing and save',
            'params': {'action': 'stop', 'path': '/tmp/performance-trace.json'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=60000,
    required_permissions=['browser.automation'],
)
class BrowserTraceModule(BaseModule):
    """Performance Trace Module using Chrome DevTools Protocol"""

    module_name = "Performance Trace"
    module_description = "Start/stop Chrome DevTools performance tracing"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'action' not in self.params:
            raise ValueError("Missing required parameter: action")

        self.action = self.params['action']
        if self.action not in ['start', 'stop']:
            raise ValueError(f"Invalid action: {self.action}. Must be 'start' or 'stop'")

        self.categories = self.params.get('categories', ['devtools.timeline'])
        self.screenshots = self.params.get('screenshots', True)
        self.output_path = self.params.get('path', '')
        if self.output_path:
            self.output_path = validate_path_with_env_config(self.output_path)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Check if browser is Chromium
        if browser.browser_type != 'chromium':
            reason = f"Tracing only supported on Chromium, got: {browser.browser_type}"
            return {
                "status": "error",
                "error": reason,
                "error_code": "CHROMIUM_ONLY",
                "outcome": _trace_refused_outcome(
                    action=self.action, error_code="CHROMIUM_ONLY", reason=reason,
                ),
            }

        if self.action == 'start':
            return await self._start_tracing(browser)
        else:
            return await self._stop_tracing(browser)

    async def _start_tracing(self, browser) -> Dict[str, Any]:
        """Start performance tracing"""
        # Check if already tracing
        if self.context.get('_tracing_active'):
            reason = "Tracing already active. Stop current trace before starting new one."
            return {
                "status": "error",
                "error": reason,
                "error_code": "TRACING_ACTIVE",
                "outcome": _trace_refused_outcome(
                    action='start', error_code="TRACING_ACTIVE", reason=reason,
                ),
            }

        try:
            # Use Playwright's context.tracing API which works with both
            # regular and persistent browser contexts (browser._browser
            # is None for persistent contexts).
            context = browser._context
            if not context:
                raise RuntimeError("No browser context available for tracing")
            await context.tracing.start(
                screenshots=self.screenshots,
                snapshots=True,
            )

            # Mark tracing as active in context
            self.context['_tracing_active'] = True
            self.context['_tracing_categories'] = self.categories
            self.context['_tracing_screenshots'] = self.screenshots

            return {
                "status": "success",
                "tracing": True,
                "categories": self.categories,
                "screenshots": self.screenshots,
                "message": "Performance tracing started",
                "outcome": _trace_started_outcome(
                    categories=self.categories, screenshots=self.screenshots,
                ),
            }

        except Exception as e:
            error_msg = str(e)
            if 'Target is not attached to CDP' in error_msg or 'Protocol error' in error_msg:
                reason = "CDP tracing not available. Ensure browser is Chromium."
                return {
                    "status": "error",
                    "error": reason,
                    "error_code": "CDP_UNAVAILABLE",
                    "outcome": _trace_refused_outcome(
                        action='start', error_code="CDP_UNAVAILABLE", reason=reason,
                    ),
                }
            raise

    async def _stop_tracing(self, browser) -> Dict[str, Any]:
        """Stop performance tracing and optionally save to file"""
        # Check if tracing is active
        if not self.context.get('_tracing_active'):
            reason = "No active trace. Start tracing first."
            return {
                "status": "error",
                "error": reason,
                "error_code": "NO_ACTIVE_TRACE",
                "outcome": _trace_refused_outcome(
                    action='stop', error_code="NO_ACTIVE_TRACE", reason=reason,
                ),
            }

        try:
            # Stop tracing via context.tracing API
            context = browser._context
            if not context:
                raise RuntimeError("No browser context available for tracing")

            # Clear tracing state
            self.context['_tracing_active'] = False

            # Save to file if path provided, otherwise to temp file
            if self.output_path:
                path = Path(validate_path_with_env_config(self.output_path))
                path.parent.mkdir(parents=True, exist_ok=True)
                await context.tracing.stop(path=str(path))
                # stat, not read_bytes: the only thing wanted here is the size,
                # a trace with screenshots runs to tens of megabytes, and
                # read_bytes on a path Playwright did not write raises out of a
                # branch that has no other way to say the file is missing.
                bytes_on_disk, stat_error = _stat_size(str(path))
                result = {
                    "status": "success",
                    "tracing": False,
                    "size_bytes": bytes_on_disk if bytes_on_disk is not None else 0,
                    "path": str(path.absolute()),
                    "message": f"Trace saved to {path.absolute()}",
                    "outcome": _trace_stopped_outcome(
                        bytes_on_disk=bytes_on_disk,
                        path=str(path.absolute()),
                        stat_error=stat_error,
                    ),
                }
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                    tmp_path = tmp.name
                await context.tracing.stop(path=tmp_path)
                bytes_on_disk, stat_error = _stat_size(tmp_path)
                trace_data = Path(tmp_path).read_bytes() if bytes_on_disk is not None else b''
                import base64
                result = {
                    "status": "success",
                    "tracing": False,
                    "size_bytes": len(trace_data),
                    "trace_base64": base64.b64encode(trace_data).decode('utf-8'),
                    "message": "Trace data returned as base64",
                    "outcome": _trace_stopped_outcome(
                        bytes_on_disk=bytes_on_disk,
                        path=None,
                        stat_error=stat_error,
                    ),
                }
                Path(tmp_path).unlink(missing_ok=True)

            return result

        except Exception:
            # Reset state on error
            self.context['_tracing_active'] = False
            raise
