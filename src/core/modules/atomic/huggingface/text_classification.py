"""
HuggingFace Text Classification Module

Classify text into categories (sentiment, topic, etc.).
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from .constants import TaskType, ModuleDefaults, ModuleColors, ParamDefaults, Subcategory
from ._base import HuggingFaceTaskExecutor, normalize_classification_result


logger = logging.getLogger(__name__)

_executor = HuggingFaceTaskExecutor(TaskType.TEXT_CLASSIFICATION)


@register_module(
    module_id='huggingface.text-classification',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.TEXT,
    tags=['huggingface', 'text', 'classification', 'sentiment', 'nlp'],
    label='Text Classification',
    label_key='huggingface.text_classification.label',
    description='Classify text into categories (sentiment, topic, etc.)',
    description_key='huggingface.text_classification.description',
    icon='Tags',
    color=ModuleColors.TEXT_CLASSIFICATION,

    input_types=['text'],
    output_types=['json'],
    can_connect_to=['data.*', 'object.*'],

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
            'task': TaskType.TEXT_CLASSIFICATION
        },
        'text': {
            'type': 'string',
            'label': 'Text',
            'required': True,
            'multiline': True
        },
        'top_k': {
            'type': 'number',
            'label': 'Top K',
            'default': ParamDefaults.TOP_K
        }
    },
    output_schema={
        'labels': {'type': 'array', 'description': 'Classification results'},
        'top_label': {'type': 'string', 'description': 'Top predicted label'},
        'top_score': {'type': 'number', 'description': 'Confidence score'}
    },
    author=ModuleDefaults.AUTHOR,
    license=ModuleDefaults.LICENSE
)
async def huggingface_text_classification(context: Dict[str, Any]) -> Dict[str, Any]:
    """Classify text using HuggingFace models"""
    params = context['params']
    model_id = params['model_id']
    text = params['text']
    top_k = params.get('top_k', ParamDefaults.TOP_K)

    exec_result = await _executor.execute(
        model_id=model_id,
        inputs=text,
        top_k=top_k
    )

    result = normalize_classification_result(exec_result['raw_result'])
    logger.info(f"Classified as '{result['top_label']}' with score {result['top_score']:.4f}")

    return {
        'ok': True,
        'labels': result['labels'],
        'top_label': result['top_label'],
        'top_score': result['top_score'],
        'model_id': model_id,
        'runtime': exec_result['runtime']
    }
