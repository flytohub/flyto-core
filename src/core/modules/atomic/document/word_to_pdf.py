# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Word to PDF Converter Module
Convert Word documents (.docx) to PDF files
"""
import logging
import os
import subprocess
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
    can_connect_to=['file.*', 'pdf.*', 'flow.*'],
    can_receive_from=['file.*', 'data.*', 'http.*', 'flow.*', 'start'],

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

    output_path = _resolve_output_path(params, input_path, '.pdf')
    _validate_input_and_prepare_output(input_path, output_path, 'Word')

    success, method_used = await _run_conversion(method, input_path, output_path)

    if not success:
        raise RuntimeError(
            "No conversion method available. Please install one of:\n"
            "- docx2pdf: pip install docx2pdf (requires MS Word on Mac/Windows)\n"
            "- LibreOffice: brew install libreoffice (Mac) or apt install libreoffice (Linux)"
        )

    file_size = os.path.getsize(output_path)

    logger.info(f"Converted Word to PDF: {input_path} -> {output_path} (method: {method_used})")

    return {
        'ok': True,
        'output_path': output_path,
        'file_size': file_size,
        'method_used': method_used,
        'message': f'Successfully converted Word document to PDF using {method_used}'
    }


def _resolve_output_path(params: Dict[str, Any], input_path: str, ext: str) -> str:
    output_path = params.get('output_path')
    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f"{base}{ext}"
    return output_path


def _validate_input_and_prepare_output(input_path: str, output_path: str, file_type: str):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"{file_type} file not found: {input_path}")
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)


async def _run_conversion(method: str, input_path: str, output_path: str) -> tuple:
    if method in ('auto', 'docx2pdf'):
        success, method_used = await _try_docx2pdf(input_path, output_path)
        if success:
            return success, method_used

    if method in ('auto', 'libreoffice'):
        success, method_used = await _try_libreoffice(input_path, output_path)
        if success:
            return success, method_used

    return await _try_fallback(input_path, output_path)


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
    lo_exe = _find_libreoffice()
    if not lo_exe:
        logger.debug("LibreOffice not found")
        return False, None

    try:
        output_dir = os.path.dirname(output_path) or '.'
        subprocess.run([
            lo_exe, '--headless',
            '--convert-to', 'pdf',
            '--outdir', output_dir,
            input_path
        ], capture_output=True, timeout=120)

        expected_output = os.path.join(
            output_dir,
            os.path.splitext(os.path.basename(input_path))[0] + '.pdf'
        )
        if os.path.exists(expected_output):
            if expected_output != output_path:
                os.rename(expected_output, output_path)
            return True, 'libreoffice'
    except subprocess.TimeoutExpired:
        logger.debug("LibreOffice conversion timed out")
    except Exception as e:
        logger.debug(f"LibreOffice conversion failed: {e}")

    return False, None


def _find_libreoffice():
    lo_paths = [
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        'libreoffice',
        'soffice'
    ]
    for path in lo_paths:
        if os.path.exists(path) or _which(path):
            return path
    return None


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
        doc = Document(input_path)
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        margin = inch
        y = height - margin

        y_top = height - margin
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                y -= 14
                continue
            y = _write_paragraph(c, text, y, y_top, width, margin)

        c.save()
        if os.path.exists(output_path):
            return True, 'fallback'
    except Exception as e:
        logger.debug(f"Fallback conversion failed: {e}")

    return False, None


def _write_paragraph(c, text: str, y: float, y_top: float, width: float, margin: float) -> float:
    line_height = 14
    words = text.split()
    line = ""
    for word in words:
        test_line = f"{line} {word}".strip()
        if c.stringWidth(test_line, "Helvetica", 11) < width - 2 * margin:
            line = test_line
        else:
            if y < margin:
                c.showPage()
                y = y_top
            c.drawString(margin, y, line)
            y -= line_height
            line = word
    if line:
        if y < margin:
            c.showPage()
            y = y_top
        c.drawString(margin, y, line)
        y -= line_height
    return y


def _which(program: str) -> str:
    """Find executable in PATH"""
    try:
        result = subprocess.run(['which', program], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Failed to find {program}: {e}")
    return None
