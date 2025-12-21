"""
HuggingFace Translation Module

Translate text between languages.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from .constants import TaskType, ModuleDefaults, ModuleColors, Subcategory
from ._base import HuggingFaceTaskExecutor, normalize_text_result


logger = logging.getLogger(__name__)

_executor = HuggingFaceTaskExecutor(TaskType.TRANSLATION)


@register_module(
    module_id='huggingface.translation',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.TEXT,
    tags=['huggingface', 'text', 'translation', 'nlp', 'language'],
    label='Translation',
    label_key='huggingface.translation.label',
    description='Translate text between languages using Helsinki-NLP, mBART, etc.',
    description_key='huggingface.translation.description',
    icon='Languages',
    color=ModuleColors.TRANSLATION,

    input_types=['text'],
    output_types=['text'],
    can_connect_to=['string.*'],

    timeout=ModuleDefaults.TIMEOUT,
    retryable=ModuleDefaults.RETRYABLE,
    max_retries=ModuleDefaults.MAX_RETRIES,
    concurrent_safe=ModuleDefaults.CONCURRENT_SAFE,

    requires_credentials=ModuleDefaults.REQUIRES_CREDENTIALS,
    handles_sensitive_data=ModuleDefaults.HANDLES_SENSITIVE_DATA,

    params_schema={
        'model_id': {
            'type': 'installed_model',
            'label': 'Model',
            'required': True,
            'task': TaskType.TRANSLATION
        },
        'text': {
            'type': 'string',
            'label': 'Text',
            'required': True,
            'multiline': True
        },
        'source_lang': {
            'type': 'string',
            'label': 'Source Language',
            'required': False
        },
        'target_lang': {
            'type': 'string',
            'label': 'Target Language',
            'required': False
        }
    },
    output_schema={
        'translation_text': {'type': 'string', 'description': 'Translated text'}
    },
    author=ModuleDefaults.AUTHOR,
    license=ModuleDefaults.LICENSE
)
async def huggingface_translation(context: Dict[str, Any]) -> Dict[str, Any]:
    """Translate text using HuggingFace models"""
    params = context['params']
    model_id = params['model_id']
    text = params['text']

    kwargs = {}
    if params.get('source_lang'):
        kwargs['src_lang'] = params['source_lang']
    if params.get('target_lang'):
        kwargs['tgt_lang'] = params['target_lang']

    exec_result = await _executor.execute(
        model_id=model_id,
        inputs=text,
        **kwargs
    )

    translation_text = normalize_text_result(exec_result['raw_result'])
    logger.info(f"Translated to {len(translation_text)} characters")

    return {
        'ok': True,
        'translation_text': translation_text,
        'model_id': model_id,
        'runtime': exec_result['runtime']
    }
