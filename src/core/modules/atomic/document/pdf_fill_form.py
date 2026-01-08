"""
PDF Fill Form Module
Fill PDF form fields and insert images into PDF templates
"""
import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets


logger = logging.getLogger(__name__)


@register_module(
    module_id='pdf.fill_form',
    version='1.0.0',
    category='document',
    subcategory='pdf',
    tags=['pdf', 'form', 'fill', 'template', 'document', 'image', 'path_restricted'],
    label='Fill PDF Form',
    label_key='modules.pdf.fill_form.label',
    description='Fill PDF form fields with data and optionally insert images',
    description_key='modules.pdf.fill_form.description',
    icon='FileEdit',
    color='#D32F2F',

    input_types=['object', 'file'],
    output_types=['file'],
    can_connect_to=['file.*'],
    can_receive_from=['file.*', 'data.*', 'api.*', 'flow.*', 'start'],

    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'filesystem.write'],

    params_schema=compose(
        presets.PDF_TEMPLATE(),
        presets.DOC_OUTPUT_PATH(key="output", required=True),
        presets.PDF_FORM_FIELDS(),
        presets.PDF_IMAGES(),
        presets.PDF_FLATTEN(),
    ),
    output_schema={
        'output_path': {
            'type': 'string',
            'description': 'Path to the filled PDF'
        ,
                'description_key': 'modules.pdf.fill_form.output.output_path.description'},
        'fields_filled': {
            'type': 'number',
            'description': 'Number of fields filled'
        ,
                'description_key': 'modules.pdf.fill_form.output.fields_filled.description'},
        'images_inserted': {
            'type': 'number',
            'description': 'Number of images inserted'
        ,
                'description_key': 'modules.pdf.fill_form.output.images_inserted.description'},
        'file_size_bytes': {
            'type': 'number',
            'description': 'Size of the output PDF in bytes'
        ,
                'description_key': 'modules.pdf.fill_form.output.file_size_bytes.description'}
    },
    examples=[
        {
            'title': 'Fill form with text fields',
            'title_key': 'modules.pdf.fill_form.examples.text.title',
            'params': {
                'template': '/templates/form.pdf',
                'output': '/output/filled.pdf',
                'fields': {
                    'name': 'John Doe',
                    'id_number': 'A123456789',
                    'date': '2024-01-01'
                }
            }
        },
        {
            'title': 'Fill form with photo',
            'title_key': 'modules.pdf.fill_form.examples.photo.title',
            'params': {
                'template': '/templates/id_card.pdf',
                'output': '/output/id_card_filled.pdf',
                'fields': {
                    'name': 'Jane Doe'
                },
                'images': [
                    {
                        'file': '/photos/jane.jpg',
                        'page': 1,
                        'x': 50,
                        'y': 650,
                        'width': 100,
                        'height': 120
                    }
                ]
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def pdf_fill_form(context: Dict[str, Any]) -> Dict[str, Any]:
    """Fill PDF form fields and insert images"""
    params = context['params']
    template_path = params['template']
    output_path = params['output']
    fields = params.get('fields', {})
    images = params.get('images', [])
    flatten = params.get('flatten', True)

    if not os.path.exists(template_path):
        return {
            'ok': False,
            'error': f'Template file not found: {template_path}'
        }

    def _fill_form():
        try:
            import pypdf
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            raise ImportError("pypdf is required for pdf.fill_form. Install with: pip install pypdf")

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        reader = PdfReader(template_path)
        writer = PdfWriter()

        fields_filled = 0
        images_inserted = 0

        for page_num, page in enumerate(reader.pages):
            writer.add_page(page)

        if fields and reader.get_fields():
            for field_name, value in fields.items():
                try:
                    writer.update_page_form_field_values(
                        writer.pages[0],
                        {field_name: str(value)}
                    )
                    fields_filled += 1
                except Exception as e:
                    logger.warning(f"Could not fill field '{field_name}': {e}")

        if images:
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.utils import ImageReader
                from io import BytesIO
                import tempfile

                for img_config in images:
                    img_file = img_config.get('file')
                    if not img_file or not os.path.exists(img_file):
                        logger.warning(f"Image file not found: {img_file}")
                        continue

                    page_num = img_config.get('page', 1) - 1
                    if page_num < 0 or page_num >= len(writer.pages):
                        logger.warning(f"Invalid page number: {page_num + 1}")
                        continue

                    x = img_config.get('x', 0)
                    y = img_config.get('y', 0)
                    width = img_config.get('width', 100)
                    height = img_config.get('height', 100)

                    page = writer.pages[page_num]
                    page_width = float(page.mediabox.width)
                    page_height = float(page.mediabox.height)

                    packet = BytesIO()
                    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

                    try:
                        can.drawImage(
                            img_file,
                            x, y,
                            width=width,
                            height=height,
                            preserveAspectRatio=True,
                            mask='auto'
                        )
                        can.save()

                        packet.seek(0)
                        overlay_reader = PdfReader(packet)
                        overlay_page = overlay_reader.pages[0]

                        page.merge_page(overlay_page)
                        images_inserted += 1

                    except Exception as e:
                        logger.warning(f"Failed to insert image {img_file}: {e}")

            except ImportError:
                logger.warning("reportlab is required for image insertion. Install with: pip install reportlab")

        with open(output_path, 'wb') as f:
            writer.write(f)

        return fields_filled, images_inserted

    fields_filled, images_inserted = await asyncio.to_thread(_fill_form)

    file_size = os.path.getsize(output_path)

    logger.info(f"Filled PDF: {output_path} ({fields_filled} fields, {images_inserted} images)")

    return {
        'ok': True,
        'output_path': output_path,
        'fields_filled': fields_filled,
        'images_inserted': images_inserted,
        'file_size_bytes': file_size
    }
