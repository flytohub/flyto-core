"""
HuggingFace Text Generation Module

Generate text using LLMs like Llama, Mistral, Phi.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from .constants import TaskType, ModuleDefaults, ModuleColors, ParamDefaults, Subcategory
from ._base import HuggingFaceTaskExecutor, normalize_text_result


logger = logging.getLogger(__name__)

_executor = HuggingFaceTaskExecutor(TaskType.TEXT_GENERATION)


@register_module(
    module_id='huggingface.text-generation',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.TEXT,
    tags=['huggingface', 'text', 'generation', 'llm', 'llama', 'mistral'],
    label='Text Generation',
    label_key='huggingface.text_generation.label',
    description='Generate text using LLMs (Llama, Mistral, Phi, etc.)',
    description_key='huggingface.text_generation.description',
    icon='MessageSquare',
    color=ModuleColors.TEXT_GENERATION,

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
            'label_key': 'huggingface.text_generation.params.model_id.label',
            'description': 'HuggingFace LLM model to use',
            'description_key': 'huggingface.text_generation.params.model_id.description',
            'required': True,
            'task': TaskType.TEXT_GENERATION
        },
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'huggingface.text_generation.params.prompt.label',
            'description': 'Text prompt to generate from',
            'description_key': 'huggingface.text_generation.params.prompt.description',
            'required': True,
            'multiline': True
        },
        'max_new_tokens': {
            'type': 'number',
            'label': 'Max Tokens',
            'default': ParamDefaults.MAX_NEW_TOKENS
        },
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'default': ParamDefaults.TEMPERATURE
        },
        'top_p': {
            'type': 'number',
            'label': 'Top P',
            'default': ParamDefaults.TOP_P
        },
        'do_sample': {
            'type': 'boolean',
            'label': 'Do Sample',
            'default': ParamDefaults.DO_SAMPLE
        }
    },
    output_schema={
        'generated_text': {'type': 'string', 'description': 'Generated text'}
    },
    author=ModuleDefaults.AUTHOR,
    license=ModuleDefaults.LICENSE
)
async def huggingface_text_generation(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate text using HuggingFace LLMs"""
    params = context['params']
    model_id = params['model_id']
    prompt = params['prompt']

    exec_result = await _executor.execute(
        model_id=model_id,
        inputs=prompt,
        max_new_tokens=params.get('max_new_tokens', ParamDefaults.MAX_NEW_TOKENS),
        temperature=params.get('temperature', ParamDefaults.TEMPERATURE),
        top_p=params.get('top_p', ParamDefaults.TOP_P),
        do_sample=params.get('do_sample', ParamDefaults.DO_SAMPLE)
    )

    generated_text = normalize_text_result(exec_result['raw_result'])

    # Remove prompt from beginning if present
    if generated_text.startswith(prompt):
        generated_text = generated_text[len(prompt):].strip()

    logger.info(f"Generated {len(generated_text)} characters")

    return {
        'ok': True,
        'generated_text': generated_text,
        'model_id': model_id,
        'runtime': exec_result['runtime']
    }
