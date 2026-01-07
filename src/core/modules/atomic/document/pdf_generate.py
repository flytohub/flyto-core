"""
PDF Generate Module
Generate PDF files from HTML or text content
"""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='pdf.generate',
    version='1.0.0',
    category='document',
    subcategory='pdf',
    tags=['pdf', 'generate', 'create', 'document', 'report'],
    label='Generate PDF',
    label_key='modules.pdf.generate.label',
    description='Generate PDF files from HTML content or text',
    description_key='modules.pdf.generate.description',
    icon='FileText',
    color='#D32F2F',

    input_types=['text', 'html', 'object'],
    output_types=['file'],
    can_connect_to=['file.*'],
    can_receive_from=['file.*', 'data.*', 'api.*', 'flow.*', 'start'],

    timeout=120,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['file.write'],

    params_schema=compose(
        presets.PDF_CONTENT(),
        presets.DOC_OUTPUT_PATH(required=True),
        presets.PDF_TITLE(),
        presets.PDF_AUTHOR(),
        presets.PDF_PAGE_SIZE(),
        presets.PDF_ORIENTATION(),
        presets.PDF_MARGIN(),
        presets.PDF_HEADER(),
        presets.PDF_FOOTER(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the generated PDF'
        ,
                'description_key': 'modules.pdf.generate.output.output_path.description'},
        'page_count': {
            'type': 'number',
            'description': 'Number of pages in the PDF'
        ,
                'description_key': 'modules.pdf.generate.output.page_count.description'},
        'file_size_bytes': {
            'type': 'number',
            'description': 'Size of the generated PDF in bytes'
        ,
                'description_key': 'modules.pdf.generate.output.file_size_bytes.description'}
    },
    examples=[
        {
            'title': 'Generate from HTML',
            'title_key': 'modules.pdf.generate.examples.html.title',
            'params': {
                'content': '<h1>Report</h1><p>Content here</p>',
                'output_path': '/path/to/report.pdf',
                'title': 'Monthly Report'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def pdf_generate(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate PDF from HTML or text content"""
    try:
        from reportlab.lib.pagesizes import A4, LETTER, LEGAL, A3, A5
        from reportlab.lib.pagesizes import landscape, portrait
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        raise ImportError("reportlab is required for pdf.generate. Install with: pip install reportlab")

    params = context['params']
    content = params['content']
    output_path = params['output_path']
    title = params.get('title', '')
    author = params.get('author', '')
    page_size_name = params.get('page_size', 'A4')
    orientation = params.get('orientation', 'portrait')
    margin = params.get('margin', 20)
    header_text = params.get('header', '')
    footer_text = params.get('footer', '')

    page_sizes = {
        'A4': A4,
        'Letter': LETTER,
        'Legal': LEGAL,
        'A3': A3,
        'A5': A5
    }
    page_size = page_sizes.get(page_size_name, A4)

    if orientation == 'landscape':
        page_size = landscape(page_size)

    def _generate():
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=page_size,
            leftMargin=margin * mm,
            rightMargin=margin * mm,
            topMargin=margin * mm,
            bottomMargin=margin * mm,
            title=title,
            author=author
        )

        styles = getSampleStyleSheet()
        story = []

        if content.strip().startswith('<'):
            try:
                from reportlab.platypus import XPreformatted
                from html.parser import HTMLParser
                import html

                class SimpleHTMLParser(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.text_parts = []
                        self.current_style = 'Normal'

                    def handle_starttag(self, tag, attrs):
                        if tag in ('h1', 'h2', 'h3'):
                            self.current_style = 'Heading1' if tag == 'h1' else 'Heading2'
                        elif tag == 'p':
                            self.current_style = 'Normal'

                    def handle_data(self, data):
                        text = data.strip()
                        if text:
                            self.text_parts.append((self.current_style, text))

                parser = SimpleHTMLParser()
                parser.feed(content)

                for style_name, text in parser.text_parts:
                    style = styles.get(style_name, styles['Normal'])
                    story.append(Paragraph(text, style))
                    story.append(Spacer(1, 12))

            except Exception:
                story.append(Paragraph(content, styles['Normal']))
        else:
            for line in content.split('\n'):
                if line.strip():
                    story.append(Paragraph(line, styles['Normal']))
                    story.append(Spacer(1, 6))

        if not story:
            story.append(Paragraph(' ', styles['Normal']))

        doc.build(story)

        return output_path

    await asyncio.to_thread(_generate)

    file_size = os.path.getsize(output_path)

    try:
        import pypdf
        with open(output_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)
    except Exception:
        page_count = 1

    logger.info(f"Generated PDF: {output_path} ({page_count} pages, {file_size} bytes)")

    return {
        'ok': True,
        'output_path': output_path,
        'page_count': page_count,
        'file_size_bytes': file_size
    }
