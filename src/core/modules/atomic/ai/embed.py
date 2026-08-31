# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Embed Module
Generate embeddings from text using OpenAI or local models.

HOW FAR THIS MODULE FOLLOWS REALITY

ACCEPTED, and no higher. Vectors coming back are the provider reporting on its
own work: it ran a model we paid for and told us the numbers. Nothing here
measures a consequence in the world, so there is nothing to observe. A 200 with
a body is "the other side acknowledged taking it", which is what ACCEPTED means.

Two predicates the CALLER asked for are evaluated on every response, and either
one failing is FAILED rather than a lower rung -- `outcome.py` reserves FAILED
for exactly this, an expectation somebody else stated that was adjudicated and
did not hold:

  * one vector per input. The caller handed `texts`; a response with a different
    number of vectors silently misaligns every downstream index.
  * `dimensions`, when the caller supplied it. `text-embedding-3-*` accepts the
    parameter, and a vector of another width breaks whatever index it is written
    into.

Neither predicate can raise the rung when it holds. Both are facts about the
shape of the peer's own answer, not about the world, and VERIFIED means a
DECLARED postcondition held -- this module declares none, so `ceiling_for(None)`
caps it at OBSERVED, and it has nothing to observe either.

`token_count` is the provider's own billing figure, carried as an effect labelled
as such. No line here checks it against anything.

The error paths raise (`ValidationError`, `ModuleError`) rather than returning,
so they carry no envelope: there is no result dict for one to live in.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...errors import ModuleError, ValidationError
from ...registry import register_module
from ...schema import compose, field

logger = logging.getLogger(__name__)


def _embedding_outcome(
    *,
    model: str,
    texts_requested: int,
    embeddings: List[Any],
    dimensions_requested: Optional[int],
    dimensions_returned: int,
    token_count: Any,
) -> Dict[str, Any]:
    """The rung these vectors earned, and the caller contracts they were held to."""
    returned_effect = {
        'kind': 'embeddings_returned',
        'model': model,
        'count': len(embeddings),
        'dimensions': dimensions_returned,
        'tokens_billed_by_provider': token_count,
        'measured_by': "len() over the vectors in the provider's response body",
        'detail': (
            'The provider ran an embedding model and returned the vectors. Counting '
            'them measures the answer, not the world: it says the peer replied, not '
            'that anything was embedded correctly or stored anywhere.'
        ),
    }

    broken = []
    if len(embeddings) != texts_requested:
        broken.append({
            'kind': 'embedding_count_unmet',
            'predicate': 'len(embeddings) == len(texts)',
            'expected': texts_requested,
            'actual': len(embeddings),
            'measured_by': "len() over the vectors in the provider's response body",
            'detail': (
                'The caller handed a set of texts and got a different number of '
                'vectors back. Every position downstream is now attached to the '
                'wrong text.'
            ),
        })
    if dimensions_requested is not None and dimensions_returned != dimensions_requested:
        broken.append({
            'kind': 'embedding_dimensions_unmet',
            'predicate': 'len(embeddings[0]) == dimensions',
            'expected': dimensions_requested,
            'actual': dimensions_returned,
            'measured_by': 'len() over the first vector returned',
            'detail': (
                'The caller asked for a specific width and the vectors came back '
                'at another. Anything indexed on the requested width will reject '
                'or corrupt these.'
            ),
        })

    if broken:
        return envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.CALLER,
            postcondition='; '.join(effect['predicate'] for effect in broken),
            effects=[returned_effect] + broken,
        )

    return envelope(Outcome.ACCEPTED, effects=[returned_effect])


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
            type='string',
            format='multiline',
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
            type='string',
            format='password',
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
        'outcome': {
            'type': 'object',
            'description': (
                'How far this call was followed into reality: accepted when '
                'vectors came back, failed when the count or the width the '
                'caller asked for did not hold. Never higher than accepted -- '
                'the vectors are the provider describing its own work'
            ),
            'description_key': 'modules.ai.embed.output.outcome.description',
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
    author='Flyto2 Team',
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
        raise ModuleError(f"API request failed: {e}") from e


async def _call_openai_embed(
    api_key: str,
    model: str,
    texts: List[str],
    dimensions: Optional[int],
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

    async with aiohttp.ClientSession() as session, session.post(
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
                # Inside `data`: to_legacy_dict keeps `ok` and `data` and
                # discards every sibling, so an envelope written next to them
                # would never leave the step.
                'outcome': _embedding_outcome(
                    model=data.get('model', model),
                    texts_requested=len(texts),
                    embeddings=embeddings,
                    dimensions_requested=dimensions,
                    dimensions_returned=actual_dimensions,
                    token_count=token_count,
                ),
            },
        }
