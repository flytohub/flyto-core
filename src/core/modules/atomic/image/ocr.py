# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Image OCR Module
Extract text from images using Tesseract OCR.
"""
import asyncio
import logging
import os
from typing import Any, Dict

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError


logger = logging.getLogger(__name__)


def _ocr_text(img, language, custom_config):
    import pytesseract
    text = pytesseract.image_to_string(img, lang=language, config=custom_config)
    try:
        data = pytesseract.image_to_data(
            img, lang=language, config=custom_config, output_type=pytesseract.Output.DICT
        )
        confidences = [int(c) for c in data['conf'] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    except Exception:
        avg_confidence = 0.0
    return {
        'text': text.strip(),
        'confidence': round(avg_confidence, 2),
        'language': language,
    }


def _ocr_data(img, language, custom_config):
    import pytesseract
    data = pytesseract.image_to_data(
        img, lang=language, config=custom_config, output_type=pytesseract.Output.DICT
    )
    confidences = [int(c) for c in data['conf'] if int(c) > 0]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    words = []
    for i, word in enumerate(data['text']):
        if word.strip():
            words.append({
                'text': word,
                'confidence': int(data['conf'][i]),
                'x': data['left'][i],
                'y': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i],
            })
    full_text = ' '.join(w['text'] for w in words)
    return {
        'text': full_text,
        'confidence': round(avg_confidence, 2),
        'language': language,
        'words': words,
    }


def _ocr_boxes(img, language, custom_config):
    import pytesseract
    boxes = pytesseract.image_to_boxes(img, lang=language, config=custom_config)
    text = pytesseract.image_to_string(img, lang=language, config=custom_config)
    return {
        'text': text.strip(),
        'confidence': 0.0,
        'language': language,
        'boxes': boxes,
    }


@register_module(
    module_id='image.ocr',
    version='1.0.0',
    category='image',
    subcategory='analysis',
    tags=['image', 'ocr', 'text', 'extract', 'tesseract'],
    label='OCR - Extract Text',
    label_key='modules.image.ocr.label',
    description='Extract text from images using Tesseract OCR',
    description_key='modules.image.ocr.description',
    icon='FileText',
    color='#3B82F6',
    input_types=['file'],
    output_types=['string'],

    can_receive_from=['file.*', 'image.*', 'browser.*', 'http.*', 'flow.*', 'start'],
    can_connect_to=['text.*', 'string.*', 'data.*', 'flow.*'],

    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    timeout_ms=120000,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'image_path',
            type='string',
            format='path',
            label='Image Path',
            label_key='modules.image.ocr.params.image_path.label',
            description='Path to the image file',
            description_key='modules.image.ocr.params.image_path.description',
            required=True,
            placeholder='/path/to/image.png',
            group=FieldGroup.BASIC,
        ),
        field(
            'language',
            type='string',
            label='Language',
            label_key='modules.image.ocr.params.language.label',
            description='OCR language code (e.g. eng, chi_tra, jpn)',
            description_key='modules.image.ocr.params.language.description',
            default='eng',
            placeholder='eng',
            group=FieldGroup.OPTIONS,
        ),
        field(
            'psm',
            type='number',
            label='Page Segmentation Mode',
            label_key='modules.image.ocr.params.psm.label',
            description='Tesseract page segmentation mode (0-13)',
            description_key='modules.image.ocr.params.psm.description',
            default=3,
            group=FieldGroup.ADVANCED,
        ),
        field(
            'output_type',
            type='select',
            label='Output Type',
            label_key='modules.image.ocr.params.output_type.label',
            description='Type of OCR output',
            description_key='modules.image.ocr.params.output_type.description',
            default='text',
            options=[
                {'value': 'text', 'label': 'Plain Text'},
                {'value': 'data', 'label': 'Structured Data'},
                {'value': 'boxes', 'label': 'Bounding Boxes'},
            ],
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'text': {
            'type': 'string',
            'description': 'Extracted text from the image',
            'description_key': 'modules.image.ocr.output.text.description',
        },
        'confidence': {
            'type': 'number',
            'description': 'Average OCR confidence score (0-100)',
            'description_key': 'modules.image.ocr.output.confidence.description',
        },
        'language': {
            'type': 'string',
            'description': 'Language used for OCR',
            'description_key': 'modules.image.ocr.output.language.description',
        },
    },
    examples=[
        {
            'title': 'Extract text from image',
            'title_key': 'modules.image.ocr.examples.basic.title',
            'params': {
                'image_path': '/path/to/document.png',
                'language': 'eng',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def image_ocr(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract text from images using OCR."""
    params = context['params']
    image_path = params.get('image_path')
    language = params.get('language', 'eng')
    psm = params.get('psm', 3)
    output_type = params.get('output_type', 'text')

    if not image_path:
        raise ValidationError("Missing required parameter: image_path", field="image_path")

    if not os.path.exists(image_path):
        raise ModuleError(f"Image file not found: {image_path}")

    def _ocr():
        try:
            import pytesseract  # noqa: F401
            from PIL import Image
        except ImportError:
            raise ModuleError(
                "pytesseract and Pillow are required for image.ocr. "
                "Install with: pip install pytesseract Pillow"
            )

        img = Image.open(image_path)
        custom_config = f'--psm {psm}'

        handlers = {
            'text': _ocr_text,
            'data': _ocr_data,
            'boxes': _ocr_boxes,
        }
        handler = handlers.get(output_type)
        if not handler:
            raise ValidationError(f"Unsupported output_type: {output_type}", field="output_type")
        return handler(img, language, custom_config)

    result = await asyncio.to_thread(_ocr)
    logger.info(f"OCR extracted {len(result['text'])} characters from {image_path}")

    return {
        'ok': True,
        'data': result,
    }
