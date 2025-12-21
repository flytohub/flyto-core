"""
HuggingFace Image Classification Module

Classify images into categories.
"""
import logging
from typing import Any, Dict

from ...registry import register_module
from .constants import TaskType, ModuleDefaults, ModuleColors, ParamDefaults, Subcategory
from ._base import HuggingFaceTaskExecutor, normalize_classification_result


logger = logging.getLogger(__name__)

_executor = HuggingFaceTaskExecutor(TaskType.IMAGE_CLASSIFICATION)


@register_module(
    module_id='huggingface.image-classification',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.VISION,
    tags=['huggingface', 'image', 'classification', 'vision', 'cv'],
    label='Image Classification',
    label_key='huggingface.image_classification.label',
    description='Classify images into categories using ViT, ResNet, etc.',
    description_key='huggingface.image_classification.description',
    icon='Image',
    color=ModuleColors.IMAGE_CLASSIFICATION,

    input_types=['image', 'file'],
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
            'task': TaskType.IMAGE_CLASSIFICATION
        },
        'image_path': {
            'type': 'string',
            'label': 'Image Path',
            'required': True
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
async def huggingface_image_classification(context: Dict[str, Any]) -> Dict[str, Any]:
    """Classify images using HuggingFace models"""
    params = context['params']
    model_id = params['model_id']
    image_path = params['image_path']
    top_k = params.get('top_k', ParamDefaults.TOP_K)

    # Execute task - handles file path vs bytes automatically
    exec_result = await _executor.execute_with_file(
        model_id=model_id,
        file_path=image_path,
        file_type="Image",
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
