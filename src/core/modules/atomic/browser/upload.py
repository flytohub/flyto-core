# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser Upload Module

Upload file to file input element.

WHAT `size` MEASURES, AND WHAT IT DOES NOT

``size`` here is ``path.stat().st_size`` on the LOCAL file — the file this
module was pointed at. It is the size of what was OFFERED. It is byte-identical
whether the page's file input picked the file up or the selector resolved to an
element with no FileList at all, because no browser call contributes to it. Same
shape as `file.write`'s ``bytes_written``: arithmetic on the input.

The measurement that is about the effect is the input's own FileList, read out
of the page after ``set_input_files``:

    ``el.files`` non-empty     the browser holds these files    -> OBSERVED
    ``el.files`` empty         the call returned, nothing stuck -> INDETERMINATE
    ``el.files`` unreadable    not a file input, or the read
                               itself failed                    -> ACCEPTED

``el.files`` is populated by the browser from its own file picker plumbing; a
name and byte count coming back from there could not be there if the file had
not been attached. The offered size stays in the output under its old key, with
the read-back beside it under ``attached_files`` so the two are never confused
again.
"""
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from ....engine.outcome import ClaimBy, Outcome, envelope
from ....utils import validate_path_with_env_config
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets


_READ_FILE_LIST = """
el => {
    if (!el || !el.files) return null;
    return Array.from(el.files).map(f => ({ name: f.name, size: f.size }));
}
"""


async def _observe_attached_files(page, selector: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """``(files, None)`` when the input's FileList could be read, ``(None, why)`` when not.

    A failure here is not a failure of the upload: ``set_input_files`` already
    returned without raising. All that is lost is our ability to look, and the
    rung falls to the ACCEPTED this module claimed before a read-back existed.
    """
    try:
        files = await page.locator(selector).evaluate(_READ_FILE_LIST)
    except Exception as error:  # noqa: BLE001 - any failure means "cannot look"
        return None, f"{type(error).__name__}: {str(error).splitlines()[0][:160]}"
    if files is None:
        return None, 'the element exposes no FileList (not a file input)'
    return files, None


def _upload_outcome(
    *,
    offered_name: str,
    offered_bytes: int,
    attached: Optional[List[Dict[str, Any]]],
    read_error: Optional[str],
    selector: str,
) -> Dict[str, Any]:
    """The rung this upload earned, and the read-back that earned it."""
    offered_effect = {
        'kind': 'file_offered',
        'filename': offered_name,
        'bytes': offered_bytes,
        'measured_by': 'os.stat() on the local file handed to this module',
        'detail': (
            'The size of the file on THIS host, not of anything the page '
            'received. It reads identically whether the input picked the file '
            'up or ignored it.'
        ),
    }

    if attached is None:
        return envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                offered_effect,
                {
                    'kind': 'file_list_not_observed',
                    'selector': selector,
                    'measured_by': None,
                    'reason': read_error or 'the file input could not be read back',
                    'detail': (
                        'set_input_files() returned without raising and nothing '
                        'followed the file into the page.'
                    ),
                },
            ],
        )

    if not attached:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[
                offered_effect,
                {
                    'kind': 'file_list_empty',
                    'selector': selector,
                    'predicate': 'el.files.length > 0',
                    'measured_by': 'el.files read from the input after set_input_files',
                    'detail': (
                        'The input exposes a FileList and it is empty. The call '
                        'did not raise, so we cannot say the upload failed — a '
                        'page script may have cleared the input — only that '
                        'nothing we can see is attached.'
                    ),
                },
            ],
        )

    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[
            offered_effect,
            {
                'kind': 'files_attached',
                'selector': selector,
                'count': len(attached),
                'files': attached,
                'measured_by': 'el.files read from the input after set_input_files',
                'detail': (
                    'Names and byte counts the browser reports for the files now '
                    'held by this input. Attached is not uploaded: nothing here '
                    'says the form was submitted or the server accepted it.'
                ),
            },
        ],
    )


@register_module(
    module_id='browser.upload',
    version='1.0.0',
    category='browser',
    tags=['browser', 'upload', 'file', 'input', 'ssrf_protected', 'path_restricted'],
    label='Upload File',
    label_key='modules.browser.upload.label',
    description='Upload file to file input element',
    description_key='modules.browser.upload.description',
    icon='Upload',
    color='#28A745',

    # Connection types
    input_types=['page'],
    output_types=['object'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.SELECTOR(required=True, placeholder='input[type="file"]'),
        presets.UPLOAD_FILE_PATH(),
        presets.TIMEOUT_MS(key='timeout_ms', default=30000),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.upload.output.status.description'},
        'filename': {'type': 'string', 'description': 'Name of the file',
                'description_key': 'modules.browser.upload.output.filename.description'},
        'size': {'type': 'number', 'description': (
                    'Size of the LOCAL file that was offered, from os.stat. Not '
                    'a measurement of what the page received -- see '
                    'attached_files'
                ),
                'description_key': 'modules.browser.upload.output.size.description'},
        'attached_files': {
            'type': 'array',
            'description': (
                'Name and byte count of each file the input actually holds, read '
                'from el.files after the call. null when the element exposes no '
                'FileList'
            ),
            'description_key': 'modules.browser.upload.output.attached_files.description'},
        'selector': {'type': 'string', 'description': 'CSS selector that was used',
                'description_key': 'modules.browser.upload.output.selector.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this upload was followed: observed when the input '
                'reports the file attached, indeterminate when its FileList came '
                'back empty, accepted when it could not be read'
            ),
            'description_key': 'modules.browser.upload.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Upload image',
            'params': {
                'selector': 'input[type="file"]',
                'file_path': '/path/to/image.png'
            }
        },
        {
            'name': 'Upload document',
            'params': {
                'selector': '#file-upload',
                'file_path': '/path/to/document.pdf'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserUploadModule(BaseModule):
    """Upload File Module"""

    module_name = "Upload File"
    module_description = "Upload file to file input element"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'selector' not in self.params:
            raise ValueError("Missing required parameter: selector")
        if 'file_path' not in self.params:
            raise ValueError("Missing required parameter: file_path")

        self.selector = self.params['selector']
        # SECURITY: the file's bytes are handed to the visited page, so an
        # unvalidated file_path exfiltrates any host file (~/.ssh/id_rsa,
        # .env) to whatever origin the workflow navigated to. Same read
        # boundary as GHSA-wc94-386q-5478, with a network egress attached.
        self.file_path = validate_path_with_env_config(self.params['file_path'])
        self.timeout = self.params.get('timeout_ms', 30000)

        # Verify file exists
        path = Path(self.file_path)
        if not path.exists():
            raise ValueError(f"File not found: {self.file_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {self.file_path}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.page
        path = Path(self.file_path)

        # Set file on the input element
        await page.set_input_files(
            self.selector,
            self.file_path,
            timeout=self.timeout
        )

        # The only line here that measures the page rather than this host.
        attached, read_error = await _observe_attached_files(page, self.selector)

        offered_bytes = path.stat().st_size

        return {
            "status": "success",
            "filename": path.name,
            "size": offered_bytes,
            "attached_files": attached,
            "selector": self.selector,
            "outcome": _upload_outcome(
                offered_name=path.name,
                offered_bytes=offered_bytes,
                attached=attached,
                read_error=read_error,
                selector=self.selector,
            ),
        }
