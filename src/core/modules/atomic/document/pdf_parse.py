"""
PDF Parse Module
Extract text and metadata from PDF files
"""
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='pdf.parse',
    version='1.0.0',
    category='document',
    subcategory='pdf',
    tags=['pdf', 'document', 'parse', 'extract', 'text', 'path_restricted'],
    label='Parse PDF',
    label_key='modules.pdf.parse.label',
    description='Extract text and metadata from PDF files',
    description_key='modules.pdf.parse.description',
    icon='FileText',
    color='#DC2626',

    # Connection types
    input_types=['file_path'],
    output_types=['text', 'object'],
    can_connect_to=['string.*', 'data.*', 'ai.*'],
    can_receive_from=['file.*', 'data.*', 'api.*', 'flow.*', 'start'],

    # Execution settings
    timeout_ms=120000,
    retryable=False,
    concurrent_safe=True,

    # Security settings
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.PDF_PATH(),
        presets.DOC_PAGES(),
        presets.DOC_EXTRACT_IMAGES(),
        presets.DOC_EXTRACT_TABLES(),
    ),
    output_schema={
        'text': {
            'type': 'string',
            'description': 'Extracted text content'
        ,
                'description_key': 'modules.pdf.parse.output.text.description'},
        'pages': {
            'type': 'array',
            'description': 'Text content per page'
        ,
                'description_key': 'modules.pdf.parse.output.pages.description'},
        'metadata': {
            'type': 'object',
            'description': 'PDF metadata (title, author, etc.)'
        ,
                'description_key': 'modules.pdf.parse.output.metadata.description'},
        'page_count': {
            'type': 'number',
            'description': 'Total number of pages'
        ,
                'description_key': 'modules.pdf.parse.output.page_count.description'}
    },
    examples=[
        {
            'title': 'Extract all text from PDF',
            'title_key': 'modules.pdf.parse.examples.basic.title',
            'params': {
                'path': '/tmp/document.pdf',
                'pages': 'all'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def pdf_parse(context: Dict[str, Any]) -> Dict[str, Any]:
    """Parse PDF and extract text"""
    try:
        import pypdf
    except ImportError:
        raise ImportError("pypdf is required for PDF parsing. Install with: pip install pypdf")

    params = context['params']
    path = params['path']
    pages_param = params.get('pages', 'all')
    extract_images = params.get('extract_images', False)
    extract_tables = params.get('extract_tables', False)

    # Validate file exists
    if not os.path.exists(path):
        raise FileNotFoundError(f"PDF file not found: {path}")

    # Open and parse PDF
    with open(path, 'rb') as f:
        reader = pypdf.PdfReader(f)
        total_pages = len(reader.pages)

        # Determine pages to extract
        page_indices = _parse_page_range(pages_param, total_pages)

        # Extract text from each page
        page_texts: List[str] = []
        for idx in page_indices:
            if 0 <= idx < total_pages:
                page = reader.pages[idx]
                text = page.extract_text() or ""
                page_texts.append(text)

        # Combine all text
        full_text = "\n\n".join(page_texts)

        # Extract metadata
        metadata = {}
        if reader.metadata:
            metadata = {
                'title': reader.metadata.get('/Title', ''),
                'author': reader.metadata.get('/Author', ''),
                'subject': reader.metadata.get('/Subject', ''),
                'creator': reader.metadata.get('/Creator', ''),
                'producer': reader.metadata.get('/Producer', ''),
                'creation_date': str(reader.metadata.get('/CreationDate', '')),
                'modification_date': str(reader.metadata.get('/ModDate', '')),
            }

    logger.info(f"Parsed PDF: {path} ({total_pages} pages)")

    result = {
        'ok': True,
        'text': full_text,
        'pages': page_texts,
        'metadata': metadata,
        'page_count': total_pages,
        'extracted_pages': len(page_texts)
    }

    return result


def _parse_page_range(pages: str, total: int) -> List[int]:
    """Parse page range string to list of indices (0-based)"""
    if pages.lower() == 'all':
        return list(range(total))

    indices = []
    parts = pages.replace(' ', '').split(',')

    for part in parts:
        if '-' in part:
            start, end = part.split('-')
            start_idx = int(start) - 1
            end_idx = int(end)
            indices.extend(range(start_idx, min(end_idx, total)))
        else:
            idx = int(part) - 1
            if 0 <= idx < total:
                indices.append(idx)

    return sorted(set(indices))
