# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Screenshot Module - Take a screenshot of the current page

`filepath` WAS THE PATH WE ASKED FOR, NOT A FILE WE FOUND

``out = {"status": "success", "filepath": result.get('path', self.path)}``. The
driver puts ``path`` in its result by copying the argument it was handed, so
both sides of that ``get`` are the caller's own parameter. Nothing in this
module or the driver ever looked at the filesystem, and the string is the same
whether chromium wrote a PNG, wrote nothing, or wrote into a directory that
disappeared underneath it.

Two things here are measurements, and both come from outside this process:

  * the image bytes. ``page.screenshot()`` returns the encoded image, and the
    driver base64s it into the result. Its length is a count of bytes chromium
    produced by rendering — it cannot be non-zero without a capture.
  * the file, when a path was requested. ``os.stat`` after the driver returns
    reads the file that now exists.

    a path was asked for and the file is on disk    -> OBSERVED (bytes_on_disk)
    a path was asked for and it is not there        -> INDETERMINATE
    no path, and chromium returned image bytes      -> OBSERVED (image_bytes)
    no path, and it returned none                   -> ACCEPTED

The missing-file case is INDETERMINATE rather than FAILED for the usual reason:
no postcondition was declared about the path, ``page.screenshot`` did not raise,
and we cannot tell a failed write from a file something else moved.

What OBSERVED does not say: nothing here inspects the image. A screenshot of a
blank page, an error page, or a cookie banner is the same number of honest
bytes as a screenshot of the thing the caller wanted.
"""
import os
from typing import Any, Dict, Optional, Tuple

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config


def _decoded_length(encoded: Optional[str]) -> Optional[int]:
    """Byte count of a base64 payload, without materialising the bytes.

    Screenshots run to megabytes and this envelope is built on every capture;
    decoding a full-page PNG only to call ``len`` on it would be a real cost for
    an integer that base64's own arithmetic already gives exactly.
    """
    if not isinstance(encoded, str) or len(encoded) % 4 != 0:
        return None
    return len(encoded) // 4 * 3 - encoded.count('=', -2)


def _observe_file_on_disk(path: str) -> Tuple[Optional[int], Optional[str]]:
    """``(st_size, None)`` when the image could be read back, ``(None, why)`` when not."""
    try:
        return os.stat(path).st_size, None
    except OSError as error:
        return None, f"{type(error).__name__}: {error.strerror or error}"


def _screenshot_outcome(
    *,
    path: Optional[str],
    bytes_on_disk: Optional[int],
    stat_error: Optional[str],
    image_bytes: Optional[int],
) -> Dict[str, Any]:
    """The rung this capture earned, and the measurement that earned it."""
    captured_effect = {
        'kind': 'image_captured',
        'image_bytes': image_bytes,
        'measured_by': 'length of the encoded image chromium returned',
        'detail': (
            'Bytes produced by rendering the page. Says nothing about what is '
            'drawn in them: a blank page encodes to honest bytes too.'
        ),
    }

    if path:
        if bytes_on_disk is None:
            return envelope(
                Outcome.INDETERMINATE,
                claim_by=ClaimBy.INFERRED,
                effects=[
                    captured_effect,
                    {
                        'kind': 'image_file_missing',
                        'path': path,
                        'predicate': 'os.stat(path) succeeds',
                        'measured_by': 'os.stat() on the requested path after the capture',
                        'reason': stat_error,
                        'detail': (
                            'The capture returned without raising and the file '
                            'cannot be read back. `filepath` is the path that '
                            'was asked for, not a file that was found.'
                        ),
                    },
                ],
            )
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[
                captured_effect,
                {
                    'kind': 'image_file_written',
                    'path': path,
                    'bytes_on_disk': bytes_on_disk,
                    'measured_by': 'os.stat().st_size on the requested path after the capture',
                },
            ],
        )

    if image_bytes:
        return envelope(
            Outcome.OBSERVED,
            claim_by=ClaimBy.NONE,
            effects=[captured_effect],
        )

    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'image_not_observed',
            'measured_by': None,
            'detail': (
                'No path was requested and no image payload came back, so '
                'nothing measured the capture. The browser took the call and did '
                'not raise.'
            ),
        }],
    )


@register_module(
    module_id='browser.screenshot',
    version='1.0.0',
    category='browser',
    tags=['browser', 'screenshot', 'capture', 'image', 'ssrf_protected', 'path_restricted'],
    label='Take Screenshot',
    label_key='modules.browser.screenshot.label',
    description='Take a screenshot of the current page',
    description_key='modules.browser.screenshot.description',
    icon='Camera',
    color='#9B59B6',

    # Connection types
    input_types=['page'],
    output_types=['image', 'file'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    # Schema-driven params
    params_schema=compose(
        presets.OUTPUT_PATH(default='screenshot.png', placeholder='screenshot.png'),
        presets.SCREENSHOT_OPTIONS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.screenshot.output.status.description'},
        'filepath': {'type': 'string', 'description': (
                    'The path the capture was asked to write to. Not evidence a '
                    'file is there -- see bytes_on_disk'
                ),
                'description_key': 'modules.browser.screenshot.output.filepath.description'},
        'bytes_on_disk': {
            'type': 'number',
            'description': (
                'Size the filesystem reports for the written image, from '
                'os.stat. null when no path was requested or the file could not '
                'be read back'
            ),
            'description_key': 'modules.browser.screenshot.output.bytes_on_disk.description'},
        'image_bytes': {
            'type': 'number',
            'description': (
                'Number of encoded image bytes the browser produced for this '
                'capture'
            ),
            'description_key': 'modules.browser.screenshot.output.image_bytes.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this capture was followed: observed when the image was '
                'read back off disk or came back as bytes, indeterminate when a '
                'path was requested and nothing is there'
            ),
            'description_key': 'modules.browser.screenshot.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Take screenshot',
            'params': {'path': 'output/page.png'}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserScreenshotModule(BaseModule):
    """Screenshot Module"""

    module_name = "Take Screenshot"
    module_description = "Take a screenshot of the current page"
    required_permission = "browser.screenshot"

    def validate_params(self) -> None:
        # SECURITY: confine the image write to FLYTO_SANDBOX_DIR — the path is
        # caller-controlled and the rendered page decides the bytes.
        raw_path = self.params.get('path', 'screenshot.png')
        self.path = validate_path_with_env_config(raw_path) if raw_path else None
        self.full_page = self.params.get('full_page', False)
        self.format = self.params.get('format', 'png')
        self.quality = self.params.get('quality', None)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        # Build screenshot kwargs
        kwargs = {
            'full_page': self.full_page,
        }
        if self.format and self.format != 'png':
            kwargs['type'] = self.format
        if self.quality is not None and self.format in ('jpeg', 'webp'):
            kwargs['quality'] = self.quality

        result = await browser.screenshot(self.path, **kwargs)
        if isinstance(result, dict):
            # `path` in the driver's result is the argument it was handed, so
            # this is still the caller's own string. The stat below is what
            # turns it into a claim about a file.
            filepath = result.get('path', self.path)
            image_bytes = _decoded_length(result.get('base64'))
            bytes_on_disk, stat_error = (
                _observe_file_on_disk(filepath) if filepath else (None, None)
            )
            out = {
                "status": "success",
                "filepath": filepath,
                "bytes_on_disk": bytes_on_disk,
                "image_bytes": image_bytes,
                "outcome": _screenshot_outcome(
                    path=filepath,
                    bytes_on_disk=bytes_on_disk,
                    stat_error=stat_error,
                    image_bytes=image_bytes,
                ),
            }
            if 'base64' in result:
                out['_images'] = [{'base64': result['base64'], 'media_type': result.get('media_type', 'image/png')}]
            return out
        else:
            # The driver returns a dict on every path today; this branch survives
            # for a stubbed or older driver that hands back a bare path string.
            bytes_on_disk, stat_error = (
                _observe_file_on_disk(result)
                if isinstance(result, (str, bytes, os.PathLike)) and result
                else (None, None)
            )
            return {
                "status": "success",
                "filepath": result,
                "bytes_on_disk": bytes_on_disk,
                "image_bytes": None,
                "outcome": _screenshot_outcome(
                    path=result,
                    bytes_on_disk=bytes_on_disk,
                    stat_error=stat_error,
                    image_bytes=None,
                ),
            }


