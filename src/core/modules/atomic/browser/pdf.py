"""
Browser PDF Module

Generate PDF from current page.
"""
from typing import Any, Dict, Optional
from pathlib import Path
from ...base import BaseModule
from ...registry import register_module


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

    params_schema={
        'path': {
            'type': 'string',
            'label': 'Output Path',
            'label_key': 'modules.browser.pdf.params.path.label',
            'placeholder': '/path/to/output.pdf',
            'description': 'Path where to save the PDF file',
            'description_key': 'modules.browser.pdf.params.path.description',
            'required': True
        },
        'format': {
            'type': 'string',
            'label': 'Page Format',
            'label_key': 'modules.browser.pdf.params.format.label',
            'description': 'Page format (A4, Letter, Legal, etc)',
            'description_key': 'modules.browser.pdf.params.format.description',
            'default': 'A4',
            'required': False,
            'enum': ['A4', 'Letter', 'Legal', 'Tabloid', 'Ledger', 'A0', 'A1', 'A2', 'A3', 'A5', 'A6']
        },
        'landscape': {
            'type': 'boolean',
            'label': 'Landscape',
            'label_key': 'modules.browser.pdf.params.landscape.label',
            'description': 'Print in landscape orientation',
            'description_key': 'modules.browser.pdf.params.landscape.description',
            'default': False,
            'required': False
        },
        'print_background': {
            'type': 'boolean',
            'label': 'Print Background',
            'label_key': 'modules.browser.pdf.params.print_background.label',
            'description': 'Include background graphics',
            'description_key': 'modules.browser.pdf.params.print_background.description',
            'default': True,
            'required': False
        },
        'scale': {
            'type': 'number',
            'label': 'Scale',
            'label_key': 'modules.browser.pdf.params.scale.label',
            'description': 'Scale of the webpage rendering (0.1-2)',
            'description_key': 'modules.browser.pdf.params.scale.description',
            'default': 1,
            'required': False
        },
        'margin': {
            'type': 'object',
            'label': 'Margins',
            'label_key': 'modules.browser.pdf.params.margin.label',
            'description': 'Page margins {top, right, bottom, left} in CSS units',
            'description_key': 'modules.browser.pdf.params.margin.description',
            'required': False
        },
        'header_template': {
            'type': 'string',
            'label': 'Header Template',
            'label_key': 'modules.browser.pdf.params.header_template.label',
            'description': 'HTML template for page header',
            'description_key': 'modules.browser.pdf.params.header_template.description',
            'required': False
        },
        'footer_template': {
            'type': 'string',
            'label': 'Footer Template',
            'label_key': 'modules.browser.pdf.params.footer_template.label',
            'description': 'HTML template for page footer',
            'description_key': 'modules.browser.pdf.params.footer_template.description',
            'required': False
        }
    },
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
        self.format = self.params.get('format', 'A4')
        self.landscape = self.params.get('landscape', False)
        self.print_background = self.params.get('print_background', True)
        self.scale = self.params.get('scale', 1)
        self.margin = self.params.get('margin')
        self.header_template = self.params.get('header_template')
        self.footer_template = self.params.get('footer_template')

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
