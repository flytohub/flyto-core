"""
Word to PDF Converter Module
Convert Word documents (.docx) to PDF files
"""
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='word.to_pdf',
    version='1.0.0',
    category='document',
    subcategory='word',
    tags=['word', 'pdf', 'docx', 'convert', 'document', 'path_restricted'],
    label='Word to PDF',
    label_key='modules.word.to_pdf.label',
    description='Convert Word documents (.docx) to PDF files',
    description_key='modules.word.to_pdf.description',
    icon='FileOutput',
    color='#DC2626',

    # Connection types
    input_types=['file_path'],
    output_types=['file_path'],
    can_connect_to=['file.*', 'document.*'],
    can_receive_from=['file.*', 'data.*', 'api.*', 'flow.*', 'start'],

    # Execution settings
    timeout_ms=300000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.DOC_INPUT_PATH(placeholder='/path/to/document.docx'),
        presets.DOC_OUTPUT_PATH(placeholder='/path/to/output.pdf'),
        presets.DOC_CONVERSION_METHOD(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the generated PDF file'
        ,
                'description_key': 'modules.word.to_pdf.output.output_path.description'},
        'file_size': {
            'type': 'number',
            'description': 'Size of the output file in bytes'
        ,
                'description_key': 'modules.word.to_pdf.output.file_size.description'},
        'method_used': {
            'type': 'string',
            'description': 'Conversion method that was used'
        ,
                'description_key': 'modules.word.to_pdf.output.method_used.description'}
    },
    examples=[
        {
            'title': 'Convert Word to PDF',
            'title_key': 'modules.word.to_pdf.examples.basic.title',
            'params': {
                'input_path': '/tmp/document.docx'
            }
        },
        {
            'title': 'Convert with specific output path',
            'title_key': 'modules.word.to_pdf.examples.custom.title',
            'params': {
                'input_path': '/tmp/document.docx',
                'output_path': '/tmp/output.pdf'
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
async def word_to_pdf(context: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Word document to PDF"""
    params = context['params']
    input_path = params['input_path']
    method = params.get('method', 'auto')

    # Generate output path if not provided
    output_path = params.get('output_path')
    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}.pdf"

    # Validate input file exists
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Word file not found: {input_path}")

    # Create output directory if needed
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Try conversion methods
    method_used = None
    success = False

    if method in ('auto', 'docx2pdf'):
        # Try docx2pdf first (best quality on Windows/Mac)
        success, method_used = await _try_docx2pdf(input_path, output_path)

    if not success and method in ('auto', 'libreoffice'):
        # Try LibreOffice
        success, method_used = await _try_libreoffice(input_path, output_path)

    if not success:
        # Fallback: Use reportlab to create a basic PDF from text
        success, method_used = await _try_fallback(input_path, output_path)

    if not success:
        raise RuntimeError(
            "No conversion method available. Please install one of:\n"
            "- docx2pdf: pip install docx2pdf (requires MS Word on Mac/Windows)\n"
            "- LibreOffice: brew install libreoffice (Mac) or apt install libreoffice (Linux)"
        )

    # Get file size
    file_size = os.path.getsize(output_path)

    logger.info(f"Converted Word to PDF: {input_path} -> {output_path} (method: {method_used})")

    return {
        'ok': True,
        'output_path': output_path,
        'file_size': file_size,
        'method_used': method_used,
        'message': f'Successfully converted Word document to PDF using {method_used}'
    }


async def _try_docx2pdf(input_path: str, output_path: str) -> tuple:
    """Try conversion using docx2pdf"""
    try:
        from docx2pdf import convert
        convert(input_path, output_path)
        if os.path.exists(output_path):
            return True, 'docx2pdf'
    except ImportError:
        logger.debug("docx2pdf not available")
    except Exception as e:
        logger.debug(f"docx2pdf failed: {e}")
    return False, None


async def _try_libreoffice(input_path: str, output_path: str) -> tuple:
    """Try conversion using LibreOffice"""
    # Find LibreOffice executable
    lo_paths = [
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        'libreoffice',
        'soffice'
    ]

    lo_exe = None
    for path in lo_paths:
        if os.path.exists(path) or _which(path):
            lo_exe = path
            break

    if not lo_exe:
        logger.debug("LibreOffice not found")
        return False, None

    try:
        # LibreOffice outputs to directory, not specific file
        output_dir = os.path.dirname(output_path) or '.'

        result = subprocess.run([
            lo_exe,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            input_path
        ], capture_output=True, timeout=120)

        # LibreOffice creates file with same name but .pdf extension
        expected_output = os.path.join(
            output_dir,
            os.path.splitext(os.path.basename(input_path))[0] + '.pdf'
        )

        if os.path.exists(expected_output):
            # Rename if needed
            if expected_output != output_path:
                os.rename(expected_output, output_path)
            return True, 'libreoffice'

    except subprocess.TimeoutExpired:
        logger.debug("LibreOffice conversion timed out")
    except Exception as e:
        logger.debug(f"LibreOffice conversion failed: {e}")

    return False, None


async def _try_fallback(input_path: str, output_path: str) -> tuple:
    """Fallback: Extract text and create basic PDF"""
    try:
        from docx import Document
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
    except ImportError:
        logger.debug("Fallback libraries not available")
        return False, None

    try:
        # Read Word document
        doc = Document(input_path)

        # Create PDF
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        margin = inch
        y = height - margin
        line_height = 14

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                y -= line_height
                continue

            # Simple text wrapping
            words = text.split()
            line = ""
            for word in words:
                test_line = f"{line} {word}".strip()
                if c.stringWidth(test_line, "Helvetica", 11) < width - 2 * margin:
                    line = test_line
                else:
                    if y < margin:
                        c.showPage()
                        y = height - margin
                    c.drawString(margin, y, line)
                    y -= line_height
                    line = word

            if line:
                if y < margin:
                    c.showPage()
                    y = height - margin
                c.drawString(margin, y, line)
                y -= line_height

        c.save()

        if os.path.exists(output_path):
            return True, 'fallback'

    except Exception as e:
        logger.debug(f"Fallback conversion failed: {e}")

    return False, None


def _which(program: str) -> str:
    """Find executable in PATH"""
    try:
        result = subprocess.run(['which', program], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Failed to find {program}: {e}")
    return None
