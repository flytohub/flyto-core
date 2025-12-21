"""
HuggingFace Summarization Module

Generate summaries of long text.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from .constants import TaskType, ModuleDefaults, ModuleColors, ParamDefaults, Subcategory
from ._base import HuggingFaceTaskExecutor, normalize_text_result


logger = logging.getLogger(__name__)

_executor = HuggingFaceTaskExecutor(TaskType.SUMMARIZATION)


@register_module(
    module_id='huggingface.summarization',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.TEXT,
    tags=['huggingface', 'text', 'summarization', 'summary', 'nlp'],
    label='Summarization',
    label_key='huggingface.summarization.label',
    description='Generate summaries of long text using BART, Pegasus, etc.',
    description_key='huggingface.summarization.description',
    icon='FileText',
    color=ModuleColors.SUMMARIZATION,

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
            'task': TaskType.SUMMARIZATION
        },
        'text': {
            'type': 'string',
            'label': 'Text',
            'required': True,
            'multiline': True
        },
        'max_length': {
            'type': 'number',
            'label': 'Max Length',
            'default': ParamDefaults.SUMMARY_MAX_LENGTH
        },
        'min_length': {
            'type': 'number',
            'label': 'Min Length',
            'default': ParamDefaults.SUMMARY_MIN_LENGTH
        }
    },
    output_schema={
        'summary_text': {'type': 'string', 'description': 'Generated summary'}
    },
    author=ModuleDefaults.AUTHOR,
    license=ModuleDefaults.LICENSE
)
async def huggingface_summarization(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate summaries using HuggingFace models"""
    params = context['params']
    model_id = params['model_id']
    text = params['text']

    exec_result = await _executor.execute(
        model_id=model_id,
        inputs=text,
        max_length=params.get('max_length', ParamDefaults.SUMMARY_MAX_LENGTH),
        min_length=params.get('min_length', ParamDefaults.SUMMARY_MIN_LENGTH)
    )

    summary_text = normalize_text_result(exec_result['raw_result'])
    logger.info(f"Generated summary of {len(summary_text)} characters")

    return {
        'ok': True,
        'summary_text': summary_text,
        'model_id': model_id,
        'runtime': exec_result['runtime']
    }
