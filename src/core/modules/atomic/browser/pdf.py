"""
Browser PDF Module

Generate PDF from current page.
"""
from typing import Any, Dict, Optional
from pathlib import Path
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='core.browser.pdf',
    version='1.0.0',
    category='browser',
    tags=['browser', 'pdf', 'export', 'print'],
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
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
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
        'status': {'type': 'string'},
        'path': {'type': 'string'},
        'size': {'type': 'number'}
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
    license='MIT'
)
class BrowserPdfModule(BaseModule):
    """Generate PDF Module"""

    module_name = "Generate PDF"
    module_description = "Generate PDF from current page"
    required_permission = "browser.interact"

    def validate_params(self):
        if 'path' not in self.params:
            raise ValueError("Missing required parameter: path")

        self.path = self.params['path']
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

        page = browser.page

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

        # Get file size
        output_path = Path(self.path)
        size = output_path.stat().st_size if output_path.exists() else 0

        return {
            "status": "success",
            "path": str(output_path.absolute()),
            "size": size,
            "format": self.format,
            "landscape": self.landscape
        }
