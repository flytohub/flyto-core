# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Download Module

Download file from browser.

THE MISSING FILE THAT REPORTED SUCCESS

``size = path.stat().st_size if path.exists() else 0`` and then
``"status": "success"`` unconditionally. When the save produced no file, this
module reported success with a size of 0 — and 0 is also the honest size of a
genuinely empty download, so no consumer could tell the two apart. The literal
written in this file and the number read off the filesystem arrived under the
same key.

The rung splits them, from the same `exists()` this module already called:

    the file is on disk      st_size is a real read-back      -> OBSERVED
    the file is not there    save_as() returned and left
                             nothing we can find              -> INDETERMINATE

INDETERMINATE, not FAILED: nobody declared a postcondition about the saved path,
``save_as`` did not raise, and the file may have been moved or removed by
something else between the save and the stat. We cannot say the download failed
— only that we cannot find what it wrote. That is the textbook use of the second
axis in `outcome.py`.

A zero-byte file that EXISTS is OBSERVED, and correctly so: the browser wrote a
file at that path, and its emptiness is a fact about the download rather than a
gap in our looking.
"""
from typing import Any, Dict, Optional
from pathlib import Path
import asyncio

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_path_with_env_config


def _download_outcome(
    *,
    save_path: str,
    exists: bool,
    size: int,
    suggested_filename: Optional[str],
) -> Dict[str, Any]:
    """The rung this download earned, decided by whether the file is there."""
    if not exists:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'saved_file_missing',
                'path': save_path,
                'suggested_filename': suggested_filename,
                'predicate': 'Path(save_path).exists()',
                'measured_by': 'Path.exists() on the save path after save_as()',
                'detail': (
                    'The browser reported a download and save_as() returned '
                    'without raising, but nothing is at the save path. The 0 '
                    'reported as size is a literal in this module, not a '
                    'measurement.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'file_saved',
            'path': save_path,
            'bytes_on_disk': size,
            'suggested_filename': suggested_filename,
            'measured_by': 'os.stat().st_size on the save path after save_as()',
            'detail': (
                'Size the filesystem reports for the file the browser wrote. Not '
                'fsync-ed, and nothing here checks the bytes against what the '
                'server intended to send.'
            ),
        }],
    )


@register_module(
    module_id='browser.download',
    version='1.0.0',
    category='browser',
    tags=['browser', 'download', 'file', 'ssrf_protected', 'path_restricted'],
    label='Download File',
    label_key='modules.browser.download.label',
    description='Download file from browser',
    description_key='modules.browser.download.description',
    icon='Download',
    color='#DC3545',

    # Connection types
    input_types=['page'],
    output_types=['file'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.SELECTOR(required=False, placeholder='a.download-link'),
        presets.DOWNLOAD_SAVE_PATH(),
        presets.TIMEOUT_MS(key='timeout_ms', default=60000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.download.output.status.description'},
        'path': {'type': 'string', 'description': 'File or resource path',
                'description_key': 'modules.browser.download.output.path.description'},
        'filename': {'type': 'string', 'description': 'Name of the file',
                'description_key': 'modules.browser.download.output.filename.description'},
        'size': {'type': 'number', 'description': (
                    'Size the filesystem reports for the saved file. 0 when the '
                    'file is not there at all -- see outcome, which separates '
                    'that case from an empty download'
                ),
                'description_key': 'modules.browser.download.output.size.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this download was followed: observed when the saved '
                'file was read back off disk, indeterminate when nothing is at '
                'the save path'
            ),
            'description_key': 'modules.browser.download.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Click download button and save',
            'params': {
                'selector': '#download-btn',
                'save_path': '/downloads/report.pdf'
            }
        },
        {
            'name': 'Download with custom timeout',
            'params': {
                'selector': 'a.download',
                'save_path': '/downloads/large-file.zip',
                'timeout_ms': 120000
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserDownloadModule(BaseModule):
    """Download File Module"""

    module_name = "Download File"
    module_description = "Download file from browser"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'save_path' not in self.params:
            raise ValueError("Missing required parameter: save_path")

        self.selector = self.params.get('selector')
        # SECURITY: confine the write to FLYTO_SANDBOX_DIR. save_path is
        # caller-controlled and the bytes are attacker-controlled (whatever the
        # visited page serves), so an unvalidated path here is an arbitrary
        # file write — the module's 'path_restricted' tag is metadata, it
        # enforces nothing on its own.
        self.save_path = validate_path_with_env_config(self.params['save_path'])
        self.timeout = self.params.get('timeout_ms', 60000)

        # Ensure directory exists (validated path only)
        save_dir = Path(self.save_path).parent
        save_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        # expect_download is a Page-only API; use real_page
        real_page = browser.real_page

        # Wait for download event
        async with real_page.expect_download(timeout=self.timeout) as download_info:
            if self.selector:
                await page.click(self.selector)
            # If no selector, assume download is already being triggered

        download = await download_info.value

        # Save the file
        await download.save_as(self.save_path)

        # Get file info. `exists` is kept rather than folded into the size,
        # because "no file" and "empty file" are different facts and the size
        # alone cannot carry both.
        path = Path(self.save_path)
        exists = path.exists()
        size = path.stat().st_size if exists else 0

        return {
            "status": "success",
            "path": str(path.absolute()),
            "filename": path.name,
            "size": size,
            "suggested_filename": download.suggested_filename,
            "outcome": _download_outcome(
                save_path=str(path.absolute()),
                exists=exists,
                size=size,
                suggested_filename=download.suggested_filename,
            ),
        }
