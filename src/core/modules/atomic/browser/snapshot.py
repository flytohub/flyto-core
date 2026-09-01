# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Snapshot Module - DOM snapshot capture

Capture DOM snapshots in various formats:
- HTML: Full page HTML source
- MHTML: Single-file archive (Chromium only)
- Text: Plain text content

Works across all browsers, with MHTML limited to Chromium.

HOW FAR THIS MODULE FOLLOWS REALITY

Two effects, and this module used to report an echo for the second one.

The CAPTURE is real. ``size_bytes`` is ``len()`` over the bytes the browser
handed back from ``page.content()``, ``page.inner_text('body')`` or the CDP
``Page.captureSnapshot`` call. No parameter contributes to it: point this module
at an empty document and it is 0. A non-zero capture is an observation of the
page.

The WRITE was not. When ``path`` is set the module wrote the file and returned
``str(path.absolute())`` -- the path it had been HANDED, byte-identical whether
the file exists, is empty, or was truncated by a full disk. That is
`file.write`'s ``bytes_written`` in the shape `browser.screenshot` had it in.
The fix is `file.write`'s fix: ``os.stat`` after the handle closed, compared
against the byte count that went in.

    nothing captured                          ACCEPTED
    captured, returned inline                 OBSERVED (the capture)
    captured, written, size on disk matches   OBSERVED (the capture and the file)
    captured, written, size disagrees         INDETERMINATE
    captured, written, could not stat         ACCEPTED

The disagreement is INDETERMINATE rather than FAILED for `file.write`'s reason:
nobody declared a size contract, the equality is this module's own inference,
and an inference of ours that may be wrong is exactly what `outcome.py` splits
off from a broken caller contract.

THE MHTML REFUSAL is the one FAILED here, and the only claim in this file made
by the caller rather than by us: ``format='mhtml'`` on a non-Chromium browser
cannot happen, we know it cannot, and no snapshot was taken. Note that this
branch returns ``status: 'error'`` with no ``ok`` key, so `wrap_legacy_result`
is never reached and the step still completes; before this envelope existed, a
refused snapshot was indistinguishable from a successful one anywhere but in
the payload. The rung is now what makes it visible.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, field, presets


def _observe_size_on_disk(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` when the file could be read back, ``(None, why)`` when not.

    A failure here is not a failure of the capture. The bytes were already in
    hand and the write already returned; all that is lost is our ability to
    look, and the rung is lowered to match.
    """
    try:
        return os.stat(path).st_size, None
    except OSError as error:
        return None, f"{type(error).__name__}: {error.strerror or error}"


def _snapshot_outcome(
    *,
    fmt: str,
    captured_bytes: int,
    path: Optional[str] = None,
    size_on_disk: Optional[int] = None,
    stat_error: Optional[str] = None,
) -> Dict[str, Any]:
    """The rung this snapshot earned, and the readings that earned it."""
    captured_effect = {
        'kind': 'content_captured',
        'format': fmt,
        'bytes': captured_bytes,
        'measured_by': 'len() over the bytes the browser returned for this page',
        'detail': (
            'The size of what came BACK from the browser, not of anything '
            'passed in. An empty document produces 0 here.'
        ),
    }

    if captured_bytes <= 0:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[{
                'kind': 'no_content_captured',
                'format': fmt,
                'measured_by': None,
                'detail': (
                    'The browser answered with nothing. An empty capture reads '
                    'the same whether the document is empty, the selector '
                    'resolved to an empty node, or the page had not rendered, '
                    'so it is not an observation of the page.'
                ),
            }],
        )

    if path is None:
        return envelope(Outcome.OBSERVED, claim_by=ClaimBy.NONE, effects=[captured_effect])

    if size_on_disk is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                captured_effect,
                {
                    'kind': 'file_size_not_observed',
                    'path': path,
                    'measured_by': None,
                    'reason': stat_error or 'the file could not be read back',
                    'detail': (
                        'The write returned without raising and the file was '
                        'not read back, so nothing followed the bytes onto '
                        'disk. The path in the result is the one this module '
                        'was handed, not evidence of anything.'
                    ),
                },
            ],
        )

    file_effect = {
        'kind': 'file_size_observed',
        'path': path,
        'bytes_on_disk': size_on_disk,
        'measured_by': 'os.stat(path).st_size, after the file handle closed',
        'detail': (
            'Size the kernel reports for the file that now exists. Not '
            'fsync-ed: durability across power loss is not observed.'
        ),
    }

    if size_on_disk == captured_bytes:
        return envelope(
            Outcome.OBSERVED,
            # INFERRED: a predicate was evaluated and it was ours. No caller
            # asked for "the file is exactly as large as the capture".
            claim_by=ClaimBy.INFERRED,
            effects=[captured_effect, file_effect],
        )

    return envelope(
        Outcome.INDETERMINATE,
        claim_by=ClaimBy.INFERRED,
        effects=[
            captured_effect,
            file_effect,
            {
                'kind': 'file_size_disagrees',
                'predicate': 'os.stat(path).st_size == len(captured bytes)',
                'expected_bytes': captured_bytes,
                'actual_bytes': size_on_disk,
                'detail': (
                    'The file is not the size of the capture. That may be a '
                    'short write, or it may be this module\'s inference being '
                    'wrong -- newline translation makes a correct write land '
                    'at a different length. We cannot say which, so this is '
                    'indeterminate rather than failed.'
                ),
            },
        ],
    )


def _mhtml_unsupported_outcome(browser_type: str) -> Dict[str, Any]:
    """FAILED, and by the caller's claim: they asked for a format this browser has not."""
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.CALLER,
        effects=[{
            'kind': 'snapshot_refused',
            'format': 'mhtml',
            'browser_type': browser_type,
            'measured_by': 'browser.browser_type, compared against the format requested',
            'detail': (
                'MHTML is captured through the Chromium DevTools protocol and '
                'this session is not Chromium. No snapshot was taken and none '
                'could have been: this is failed rather than indeterminate '
                'because the caller named the format and we know it did not '
                'happen.'
            ),
        }],
    )


@register_module(
    module_id='browser.snapshot',
    version='1.0.0',
    category='browser',
    tags=['browser', 'snapshot', 'dom', 'html', 'mhtml', 'debug'],
    label='DOM Snapshot',
    label_key='modules.browser.snapshot.label',
    description='Capture DOM snapshot in HTML, MHTML, or text format',
    description_key='modules.browser.snapshot.description',
    icon='FileCode',
    color='#0EA5E9',

    # Connection types
    input_types=['page'],
    output_types=['string', 'file'],

    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],

    params_schema=compose(
        field(
            'format',
            type='select',
            label='Format',
            label_key='modules.browser.snapshot.params.format.label',
            description='Snapshot format',
            required=False,
            default='html',
            options=[
                {'value': 'html', 'label': 'HTML (page source)'},
                {'value': 'mhtml', 'label': 'MHTML (single file archive, Chromium only)'},
                {'value': 'text', 'label': 'Text (plain text content)'},
            ],
        ),
        presets.SELECTOR(
            key='selector',
            required=False,
            label='Element Selector',
            placeholder='#content, .main-article',
        ),
        presets.OUTPUT_PATH(
            key='path',
            required=False,
            placeholder='/tmp/snapshot.html',
        ),
    ),
    output_schema={
        'status': {
            'type': 'string',
            'description': 'Operation status',
            'description_key': 'modules.browser.snapshot.output.status.description'
        },
        'format': {
            'type': 'string',
            'description': 'Snapshot format used',
            'description_key': 'modules.browser.snapshot.output.format.description'
        },
        'content': {
            'type': 'string',
            'description': 'Snapshot content (if no path specified)',
            'description_key': 'modules.browser.snapshot.output.content.description'
        },
        'path': {
            'type': 'string',
            'description': 'Path to saved file',
            'description_key': 'modules.browser.snapshot.output.path.description'
        },
        'size_bytes': {
            'type': 'number',
            'description': 'Content size in bytes',
            'description_key': 'modules.browser.snapshot.output.size_bytes.description'
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far this snapshot was followed: "observed" when the '
                'browser returned bytes (and, when a path was given, the file '
                'on disk is that size), "indeterminate" when the file size '
                'disagrees, "accepted" when nothing was captured or the file '
                'could not be read back, "failed" when MHTML was refused.'
            ),
            'description_key': 'modules.browser.snapshot.output.outcome.description'
        },
    },
    examples=[
        {
            'name': 'Get page HTML',
            'params': {'format': 'html'}
        },
        {
            'name': 'Save page as MHTML archive',
            'params': {'format': 'mhtml', 'path': '/tmp/page.mhtml'}
        },
        {
            'name': 'Extract text from specific element',
            'params': {'format': 'text', 'selector': 'article.main-content'}
        },
        {
            'name': 'Save HTML of specific section',
            'params': {'format': 'html', 'selector': '#main', 'path': '/tmp/section.html'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=['browser.automation'],
)
class BrowserSnapshotModule(BaseModule):
    """DOM Snapshot Module"""

    module_name = "DOM Snapshot"
    module_description = "Capture DOM snapshot"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        self.format = self.params.get('format', 'html')
        self.selector = self.params.get('selector')
        self.output_path = self.params.get('path', '')
        if self.output_path:
            self.output_path = validate_path_with_env_config(self.output_path)

        if self.format not in ['html', 'mhtml', 'text']:
            raise ValueError(f"Invalid format: {self.format}. Must be html, mhtml, or text")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        browser._snapshot_since_nav = True
        page = browser.page

        # MHTML requires Chromium
        if self.format == 'mhtml' and browser.browser_type != 'chromium':
            return {
                "status": "error",
                "error": f"MHTML format only supported on Chromium, got: {browser.browser_type}",
                "error_code": "CHROMIUM_ONLY",
                "outcome": _mhtml_unsupported_outcome(browser.browser_type),
            }

        # Capture content based on format
        if self.format == 'html':
            content = await self._capture_html(page)
        elif self.format == 'mhtml':
            content = await self._capture_mhtml(page)
        else:  # text
            content = await self._capture_text(page)

        # Build result — put selectors and text BEFORE content so they
        # survive JSON truncation (flyto-ai caps results at 8000 chars).
        result = {
            "status": "success",
            "format": self.format,
            "url": page.url,
        }

        # Extract interactive elements and text summary for AI callers.
        # These appear early in the JSON and survive truncation.
        if not self.output_path and not self.selector:
            hints = await browser.get_hints(force=True)
            if hints.get('text'):
                result["text"] = hints["text"]
            for key in ('inputs', 'checkboxes', 'radios', 'switches', 'buttons', 'links', 'selects', 'file_inputs'):
                if hints.get(key):
                    result[key] = hints[key]

        captured_bytes = len(content.encode('utf-8') if isinstance(content, str) else content)
        result["size_bytes"] = captured_bytes

        # Save to file or return content
        if self.output_path:
            path = Path(validate_path_with_env_config(self.output_path))
            path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding='utf-8')

            result["path"] = str(path.absolute())
            # The only line here that measures the filesystem. `write_text`
            # returning is an acknowledgement of receipt; the file that now
            # exists is a different question, and this is the one that asks it.
            size_on_disk, stat_error = _observe_size_on_disk(result["path"])
            result["outcome"] = _snapshot_outcome(
                fmt=self.format,
                captured_bytes=captured_bytes,
                path=result["path"],
                size_on_disk=size_on_disk,
                stat_error=stat_error,
            )
        else:
            result["outcome"] = _snapshot_outcome(
                fmt=self.format, captured_bytes=captured_bytes,
            )
            # For MHTML (bytes), encode to base64 for JSON compatibility
            if isinstance(content, bytes):
                import base64
                result["content_base64"] = base64.b64encode(content).decode('utf-8')
            else:
                # Truncate large content in response
                if len(content) > 100000:
                    result["content"] = content[:100000]
                    result["truncated"] = True
                    result["full_size_chars"] = len(content)
                else:
                    result["content"] = content

        return result

    async def _capture_html(self, page) -> str:
        """Capture HTML content"""
        if self.selector:
            # Get HTML of specific element
            element = await page.query_selector(self.selector)
            if not element:
                raise ValueError(f"Element not found: {self.selector}")
            return await element.evaluate("el => el.outerHTML")
        else:
            # Get full page HTML
            return await page.content()

    async def _capture_mhtml(self, page) -> bytes:
        """Capture MHTML archive using CDP"""
        # MHTML always captures full page, selector is ignored
        cdp_session = await page.context.new_cdp_session(page)
        try:
            result = await cdp_session.send('Page.captureSnapshot', {'format': 'mhtml'})
            return result['data'].encode('utf-8')
        finally:
            await cdp_session.detach()

    async def _capture_text(self, page) -> str:
        """Capture text content"""
        if self.selector:
            # Get text of specific element
            element = await page.query_selector(self.selector)
            if not element:
                raise ValueError(f"Element not found: {self.selector}")
            return await element.inner_text()
        else:
            # Get full page text
            return await page.inner_text('body')
