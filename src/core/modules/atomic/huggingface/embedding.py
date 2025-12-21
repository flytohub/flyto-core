"""
HuggingFace Embedding Module

Generate text embeddings for semantic search, RAG, etc.
"""
import logging
import math
from typing import Any, Dict, List

from ...registry import register_module
from .constants import TaskType, ModuleDefaults, ModuleColors, ParamDefaults, Subcategory
from ._base import HuggingFaceTaskExecutor


logger = logging.getLogger(__name__)

_executor = HuggingFaceTaskExecutor(TaskType.FEATURE_EXTRACTION)


def normalize_embedding(embedding: List[float]) -> List[float]:
    """Normalize embedding vector to unit length"""
    magnitude = math.sqrt(sum(x * x for x in embedding))
    if magnitude > 0:
        return [x / magnitude for x in embedding]
    return embedding


def extract_embedding(result: Any) -> List[float]:
    """Extract embedding from various result formats"""
    if isinstance(result, list):
        if len(result) > 0:
            if isinstance(result[0], list):
                if isinstance(result[0][0], list):
                    # Mean pooling of token embeddings
                    import numpy as np
                    token_embeddings = np.array(result[0])
                    return np.mean(token_embeddings, axis=0).tolist()
                return result[0]
            return result
    if hasattr(result, 'tolist'):
        return result.tolist()
    return []


@register_module(
    module_id='huggingface.embedding',
    version=ModuleDefaults.VERSION,
    category=ModuleDefaults.CATEGORY,
    subcategory=Subcategory.TEXT,
    tags=['huggingface', 'text', 'embedding', 'vector', 'semantic', 'rag'],
    label='Text Embedding',
    label_key='huggingface.embedding.label',
    description='Generate text embeddings for semantic search, RAG, clustering',
    description_key='huggingface.embedding.description',
    icon='Layers',
    color=ModuleColors.EMBEDDING,

    input_types=['text'],
    output_types=['vector'],
    can_connect_to=['vector.*', 'data.*'],

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
            'task': TaskType.FEATURE_EXTRACTION
        },
        'text': {
            'type': 'string',
            'label': 'Text',
            'required': True,
            'multiline': True
        },
        'normalize': {
            'type': 'boolean',
            'label': 'Normalize',
            'default': ParamDefaults.NORMALIZE
        }
    },
    output_schema={
        'embedding': {'type': 'array', 'description': 'Embedding vector(s)'},
        'dimension': {'type': 'number', 'description': 'Embedding dimension'}
    },
    author=ModuleDefaults.AUTHOR,
    license=ModuleDefaults.LICENSE
)
async def huggingface_embedding(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate text embeddings using HuggingFace models"""
    params = context['params']
    model_id = params['model_id']
    text = params['text']
    should_normalize = params.get('normalize', ParamDefaults.NORMALIZE)

    exec_result = await _executor.execute(
        model_id=model_id,
        inputs=text
    )

    embedding = extract_embedding(exec_result['raw_result'])

    if should_normalize and embedding:
        embedding = normalize_embedding(embedding)

    dimension = len(embedding)
    logger.info(f"Generated embedding of dimension {dimension}")

    return {
        'ok': True,
        'embedding': embedding,
        'dimension': dimension,
        'model_id': model_id,
        'runtime': exec_result['runtime']
    }
