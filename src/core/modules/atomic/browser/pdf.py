# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Browser PDF Module

Generate PDF from current page.

``size = stat if exists else 0``, and ``status: success`` either way — the same
pattern `browser.download` carries, and the same fix. A 0 that came from the
filesystem and a 0 written in this file arrived under one key, so "the PDF is
empty" and "there is no PDF" were indistinguishable to every consumer.

    the file is on disk      st_size is a real read-back      -> OBSERVED
    the file is not there    page.pdf() returned and left
                             nothing we can find              -> INDETERMINATE

INDETERMINATE and not FAILED: no postcondition was declared about the output
path, ``page.pdf()`` did not raise, and something outside this process may have
moved the file. What is known is that we cannot find it.

Note what OBSERVED does NOT say here. A byte count is not a page count and not a
rendering: a PDF written from a page that failed to load is a valid, non-empty
file of a blank page. The rung claims the file exists with that many bytes in
it, and nothing about what is drawn inside.
"""
from typing import Any, Dict, Optional
from pathlib import Path

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field
from ....utils import validate_path_with_env_config


def _pdf_outcome(*, path: str, exists: bool, size: int) -> Dict[str, Any]:
    """The rung this PDF earned, decided by whether the file is there."""
    if not exists:
        return envelope(
            Outcome.INDETERMINATE,
            claim_by=ClaimBy.INFERRED,
            effects=[{
                'kind': 'pdf_file_missing',
                'path': path,
                'predicate': 'Path(path).exists()',
                'measured_by': 'Path.exists() on the output path after page.pdf()',
                'detail': (
                    'page.pdf() returned without raising and nothing is at the '
                    'output path. The 0 reported as size is a literal in this '
                    'module, not a measurement.'
                ),
            }],
        )
    return envelope(
        Outcome.OBSERVED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'pdf_file_written',
            'path': path,
            'bytes_on_disk': size,
            'measured_by': 'os.stat().st_size on the output path after page.pdf()',
            'detail': (
                'Size the filesystem reports for the file the browser wrote. A '
                'byte count is not a rendering: a PDF of a blank page is a valid '
                'non-empty file.'
            ),
        }],
    )


@register_module(
    module_id='browser.pdf',
    version='1.0.0',
    category='browser',
    tags=['browser', 'pdf', 'export', 'print', 'ssrf_protected', 'path_restricted'],
    label='Generate PDF',
    label_key='modules.browser.pdf.label',
    description='Generate PDF from current page',
    description_key='modules.browser.pdf.description',
    icon='FileText',
    color='#DC3545',

    # Connection types
    input_types=['page'],
    output_types=['file'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'flow.*', 'data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'llm.*', 'agent.*'],    params_schema=compose(
        presets.OUTPUT_PATH(placeholder='/path/to/output.pdf'),
        presets.PDF_PAGE_SIZE(default='A4'),
        presets.PDF_ORIENTATION(default='portrait'),
        field(
            'print_background',
            type='boolean',
            label='Print Background',
            label_key='modules.browser.pdf.params.print_background.label',
            description='Include background graphics',
            default=True,
        ),
        field(
            'scale',
            type='number',
            label='Scale',
            label_key='modules.browser.pdf.params.scale.label',
            description='Scale of the webpage rendering (0.1-2)',
            default=1,
            min=0.1,
            max=2,
        ),
        presets.PDF_MARGIN(),
        presets.PDF_HEADER(),
        presets.PDF_FOOTER(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.pdf.output.status.description'},
        'path': {'type': 'string', 'description': 'File or resource path',
                'description_key': 'modules.browser.pdf.output.path.description'},
        'size': {'type': 'number', 'description': (
                    'Size the filesystem reports for the written PDF. 0 when the '
                    'file is not there at all -- see outcome, which separates '
                    'that case from an empty file'
                ),
                'description_key': 'modules.browser.pdf.output.size.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this export was followed: observed when the PDF was '
                'read back off disk, indeterminate when nothing is at the '
                'output path'
            ),
            'description_key': 'modules.browser.pdf.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Generate A4 PDF',
            'params': {'path': '/output/page.pdf'}
        },
        {
            'name': 'Generate landscape PDF',
            'params': {'path': '/output/landscape.pdf', 'landscape': True}
        },
        {
            'name': 'PDF with custom margins',
            'params': {
                'path': '/output/custom.pdf',
                'margin': {'top': '1cm', 'bottom': '1cm', 'left': '2cm', 'right': '2cm'}
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserPdfModule(BaseModule):
    """Generate PDF Module"""

    module_name = "Generate PDF"
    module_description = "Generate PDF from current page"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'path' not in self.params:
            raise ValueError("Missing required parameter: path")

        # SECURITY: confine the PDF write to FLYTO_SANDBOX_DIR — the path is
        # caller-controlled and the rendered page decides the bytes.
        self.path = validate_path_with_env_config(self.params['path'])
        self.format = self.params.get('page_size', self.params.get('format', 'A4'))
        orientation = self.params.get('orientation', 'portrait')
        self.landscape = orientation == 'landscape'
        self.print_background = self.params.get('print_background', True)
        self.scale = self.params.get('scale', 1)
        self.margin = self.params.get('margin')
        self.header_template = self.params.get('header_template', self.params.get('header'))
        self.footer_template = self.params.get('footer_template', self.params.get('footer'))

        # Validate scale
        if self.scale < 0.1 or self.scale > 2:
            raise ValueError(f"Scale must be between 0.1 and 2, got: {self.scale}")

        # Ensure output directory exists
        output_dir = Path(self.path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        page = browser.real_page

        # Build PDF options
        pdf_options = {
            'path': self.path,
            'format': self.format,
            'landscape': self.landscape,
            'print_background': self.print_background,
            'scale': self.scale
        }

        if self.margin:
            pdf_options['margin'] = self.margin

        if self.header_template:
            pdf_options['header_template'] = self.header_template
            pdf_options['display_header_footer'] = True

        if self.footer_template:
            pdf_options['footer_template'] = self.footer_template
            pdf_options['display_header_footer'] = True

        # Generate PDF
        await page.pdf(**pdf_options)

        # Get file size. `exists` is kept rather than folded into the size:
        # "no file" and "empty file" are different facts.
        output_path = Path(self.path)
        exists = output_path.exists()
        size = output_path.stat().st_size if exists else 0

        return {
            "status": "success",
            "path": str(output_path.absolute()),
            "size": size,
            "format": self.format,
            "landscape": self.landscape,
            "outcome": _pdf_outcome(
                path=str(output_path.absolute()),
                exists=exists,
                size=size,
            ),
        }
