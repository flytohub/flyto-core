"""
AI Embed Module
Generate embeddings from text using OpenAI or local models.
"""

import logging
import os
from typing import Any, Dict, List, Union

import aiohttp

from ...registry import register_module
from ...schema import compose, field
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='ai.embed',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='embedding',
    tags=['ai', 'embed', 'embedding', 'vector', 'semantic'],
    label='AI Embed',
    label_key='modules.ai.embed.label',
    description='Generate embeddings from text',
    description_key='modules.ai.embed.description',
    icon='GitBranch',
    color='#6366F1',

    input_types=['string', 'array'],
    output_types=['array', 'object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=60000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['ai.api'],

    params_schema=compose(
        field(
            'text',
            type='text',
            label='Text',
            label_key='modules.ai.embed.params.text',
            description='Single text or JSON array of texts to embed',
            description_key='modules.ai.embed.params.text.description',
            required=True,
            placeholder='Enter text to generate embeddings for...',
        ),
        field(
            'provider',
            type='select',
            label='Provider',
            label_key='modules.ai.embed.params.provider',
            description='Embedding provider',
            description_key='modules.ai.embed.params.provider.description',
            required=False,
            default='openai',
            options=[
                {'value': 'openai', 'label': 'OpenAI'},
                {'value': 'local', 'label': 'Local'},
            ],
        ),
        field(
            'model',
            type='string',
            label='Model',
            label_key='modules.ai.embed.params.model',
            description='Embedding model to use',
            description_key='modules.ai.embed.params.model.description',
            required=False,
            default='text-embedding-3-small',
            placeholder='text-embedding-3-small',
        ),
        field(
            'api_key',
            type='password',
            label='API Key',
            label_key='modules.ai.embed.params.api_key',
            description='API key (falls back to environment variable)',
            description_key='modules.ai.embed.params.api_key.description',
            required=False,
        ),
        field(
            'dimensions',
            type='number',
            label='Dimensions',
            label_key='modules.ai.embed.params.dimensions',
            description='Output embedding dimensions (for supported models like text-embedding-3-*)',
            description_key='modules.ai.embed.params.dimensions.description',
            required=False,
            min=1,
            max=3072,
        ),
    ),

    output_schema={
        'embeddings': {
            'type': 'array',
            'description': 'List of embedding vectors',
            'description_key': 'modules.ai.embed.output.embeddings.description',
        },
        'model': {
            'type': 'string',
            'description': 'Model used for embedding',
            'description_key': 'modules.ai.embed.output.model.description',
        },
        'dimensions': {
            'type': 'number',
            'description': 'Dimensions of each embedding vector',
            'description_key': 'modules.ai.embed.output.dimensions.description',
        },
        'token_count': {
            'type': 'number',
            'description': 'Total tokens consumed',
            'description_key': 'modules.ai.embed.output.token_count.description',
        },
    },

    examples=[
        {
            'title': 'Single Text Embedding',
            'title_key': 'modules.ai.embed.examples.single.title',
            'params': {
                'text': 'The quick brown fox jumps over the lazy dog',
                'provider': 'openai',
                'model': 'text-embedding-3-small',
            },
        },
        {
            'title': 'Reduced Dimensions',
            'title_key': 'modules.ai.embed.examples.dimensions.title',
            'params': {
                'text': 'Semantic search query',
                'provider': 'openai',
                'model': 'text-embedding-3-small',
                'dimensions': 256,
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def ai_embed(context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate embeddings from text."""
    params = context['params']
    text_input = params['text']
    provider = params.get('provider', 'openai')
    model = params.get('model', 'text-embedding-3-small')
    api_key = params.get('api_key')
    dimensions = params.get('dimensions')

    if not text_input:
        raise ValidationError("Text input is required", field="text")

    # Normalize input: accept single string or list of strings
    if isinstance(text_input, str):
        texts = [text_input]
    elif isinstance(text_input, list):
        texts = [str(t) for t in text_input]
    else:
        texts = [str(text_input)]

    # Resolve API key from environment if not provided
    if not api_key and provider == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')

    if provider == 'openai' and not api_key:
        raise ValidationError(
            "API key not provided for OpenAI",
            field="api_key",
            hint="Set OPENAI_API_KEY environment variable or provide api_key parameter",
        )

    try:
        if provider == 'openai':
            return await _call_openai_embed(
                api_key, model, texts, dimensions,
            )
        elif provider == 'local':
            raise ModuleError(
                "Local embedding provider is not yet implemented. "
                "Use 'openai' provider instead.",
            )
        else:
            raise ValidationError(
                f"Unsupported provider: {provider}",
                field="provider",
            )
    except aiohttp.ClientError as e:
        raise ModuleError(f"API request failed: {e}")


async def _call_openai_embed(
    api_key: str,
    model: str,
    texts: List[str],
    dimensions: int | None,
) -> Dict[str, Any]:
    """Call OpenAI Embeddings API."""
    payload: Dict[str, Any] = {
        "model": model,
        "input": texts,
    }

    if dimensions is not None:
        payload["dimensions"] = dimensions

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.openai.com/v1/embeddings",
            json=payload,
            headers=headers,
        ) as resp:
            data = await resp.json()

            if resp.status != 200:
                error_msg = data.get('error', {}).get('message', str(data))
                raise ModuleError(f"OpenAI API error: {error_msg}")

            # Extract embeddings, sorted by index
            embedding_data = sorted(data.get('data', []), key=lambda x: x['index'])
            embeddings = [item['embedding'] for item in embedding_data]

            # Determine actual dimensions
            actual_dimensions = len(embeddings[0]) if embeddings else 0

            # Get token usage
            usage = data.get('usage', {})
            token_count = usage.get('total_tokens', 0)

            return {
                'ok': True,
                'data': {
                    'embeddings': embeddings,
                    'model': data.get('model', model),
                    'dimensions': actual_dimensions,
                    'token_count': token_count,
                },
            }
