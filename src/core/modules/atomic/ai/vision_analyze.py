# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Vision Analyze Module
Analyze images using LLM vision capabilities (OpenAI GPT-4V or Anthropic Claude).
"""

import base64
import logging
import mimetypes
import os
from typing import Any, Dict

import aiohttp

from ...registry import register_module
from ...schema import compose, field
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='ai.vision.analyze',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='vision',
    tags=['ai', 'vision', 'image', 'analysis', 'llm'],
    label='Vision Analyze',
    label_key='modules.ai.vision.analyze.label',
    description='Analyze images using LLM vision capabilities',
    description_key='modules.ai.vision.analyze.description',
    icon='Eye',
    color='#8B5CF6',

    input_types=['string', 'object'],
    output_types=['string', 'object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read', 'ai.api'],

    params_schema=compose(
        field(
            'image_path',
            type='string',
            format='path',
            label='Image Path',
            label_key='modules.ai.vision.analyze.params.image_path',
            description='Path to the image file on disk',
            description_key='modules.ai.vision.analyze.params.image_path.description',
            required=False,
            placeholder='/path/to/image.png',
        ),
        field(
            'image_url',
            type='string',
            format='url',
            label='Image URL',
            label_key='modules.ai.vision.analyze.params.image_url',
            description='URL of the image (alternative to image_path)',
            description_key='modules.ai.vision.analyze.params.image_url.description',
            required=False,
            placeholder='https://example.com/image.png',
        ),
        field(
            'prompt',
            type='string',
            format='multiline',
            label='Prompt',
            label_key='modules.ai.vision.analyze.params.prompt',
            description='What to analyze in the image',
            description_key='modules.ai.vision.analyze.params.prompt.description',
            required=False,
            default='Describe this image in detail',
            placeholder='Describe this image in detail',
        ),
        field(
            'provider',
            type='select',
            label='Provider',
            label_key='modules.ai.vision.analyze.params.provider',
            description='LLM provider for vision analysis',
            description_key='modules.ai.vision.analyze.params.provider.description',
            required=False,
            default='openai',
            options=[
                {'value': 'openai', 'label': 'OpenAI'},
                {'value': 'anthropic', 'label': 'Anthropic'},
            ],
        ),
        field(
            'model',
            type='string',
            label='Model',
            label_key='modules.ai.vision.analyze.params.model',
            description='Model to use for vision analysis',
            description_key='modules.ai.vision.analyze.params.model.description',
            required=False,
            default='gpt-4o',
            placeholder='gpt-4o',
        ),
        field(
            'api_key',
            type='string',
            format='password',
            label='API Key',
            label_key='modules.ai.vision.analyze.params.api_key',
            description='API key (falls back to environment variable)',
            description_key='modules.ai.vision.analyze.params.api_key.description',
            required=False,
        ),
        field(
            'max_tokens',
            type='number',
            label='Max Tokens',
            label_key='modules.ai.vision.analyze.params.max_tokens',
            description='Maximum tokens in response',
            description_key='modules.ai.vision.analyze.params.max_tokens.description',
            required=False,
            default=1000,
            min=1,
            max=4096,
        ),
        field(
            'detail',
            type='select',
            label='Detail Level',
            label_key='modules.ai.vision.analyze.params.detail',
            description='Image detail level for analysis',
            description_key='modules.ai.vision.analyze.params.detail.description',
            required=False,
            default='auto',
            options=[
                {'value': 'low', 'label': 'Low'},
                {'value': 'high', 'label': 'High'},
                {'value': 'auto', 'label': 'Auto'},
            ],
        ),
    ),

    output_schema={
        'analysis': {
            'type': 'string',
            'description': 'The vision analysis result',
            'description_key': 'modules.ai.vision.analyze.output.analysis.description',
        },
        'model': {
            'type': 'string',
            'description': 'Model used for analysis',
            'description_key': 'modules.ai.vision.analyze.output.model.description',
        },
        'provider': {
            'type': 'string',
            'description': 'Provider used',
            'description_key': 'modules.ai.vision.analyze.output.provider.description',
        },
        'tokens_used': {
            'type': 'number',
            'description': 'Total tokens consumed',
            'description_key': 'modules.ai.vision.analyze.output.tokens_used.description',
        },
    },

    examples=[
        {
            'title': 'Analyze Screenshot',
            'title_key': 'modules.ai.vision.analyze.examples.screenshot.title',
            'params': {
                'image_path': '/tmp/screenshot.png',
                'prompt': 'Describe what you see in this UI screenshot',
                'provider': 'openai',
                'model': 'gpt-4o',
            },
        },
        {
            'title': 'Analyze from URL',
            'title_key': 'modules.ai.vision.analyze.examples.url.title',
            'params': {
                'image_url': 'https://example.com/photo.jpg',
                'prompt': 'What objects are in this image?',
                'provider': 'anthropic',
                'model': 'claude-sonnet-4-20250514',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def ai_vision_analyze(context: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze images using LLM vision capabilities."""
    params = context['params']
    image_path = params.get('image_path', '')
    image_url = params.get('image_url', '')
    prompt = params.get('prompt', 'Describe this image in detail')
    provider = params.get('provider', 'openai')
    model = params.get('model', 'gpt-4o')
    api_key = params.get('api_key')
    max_tokens = params.get('max_tokens', 1000)
    detail = params.get('detail', 'auto')

    if not image_path and not image_url:
        raise ValidationError(
            "Either image_path or image_url must be provided",
            field="image_path",
        )

    # Resolve API key from environment if not provided
    if not api_key:
        env_vars = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
        }
        api_key = os.getenv(env_vars.get(provider, ''))

    if not api_key:
        raise ValidationError(
            f"API key not provided for {provider}",
            field="api_key",
            hint=f"Set {provider.upper()}_API_KEY environment variable or provide api_key parameter",
        )

    # Read image as base64 if path is provided
    image_b64 = None
    media_type = 'image/png'

    if image_path:
        if not os.path.exists(image_path):
            raise ValidationError(
                f"Image file not found: {image_path}",
                field="image_path",
            )
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type:
            media_type = mime_type

        with open(image_path, 'rb') as f:
            image_b64 = base64.b64encode(f.read()).decode('utf-8')

    try:
        async with aiohttp.ClientSession() as session:
            if provider == 'openai':
                return await _call_openai_vision(
                    session, api_key, model, prompt, max_tokens, detail,
                    image_b64, image_url, media_type,
                )
            elif provider == 'anthropic':
                return await _call_anthropic_vision(
                    session, api_key, model, prompt, max_tokens,
                    image_b64, image_url, media_type,
                )
            else:
                raise ValidationError(
                    f"Unsupported provider: {provider}",
                    field="provider",
                )
    except aiohttp.ClientError as e:
        raise ModuleError(f"API request failed: {e}")


async def _call_openai_vision(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    detail: str,
    image_b64: str | None,
    image_url: str,
    media_type: str,
) -> Dict[str, Any]:
    """Call OpenAI Vision API."""
    # Build image content
    if image_b64:
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{image_b64}",
                "detail": detail,
            },
        }
    else:
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": image_url,
                "detail": detail,
            },
        }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_content,
                ],
            }
        ],
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with session.post(
        "https://api.openai.com/v1/chat/completions",
        json=payload,
        headers=headers,
    ) as resp:
        data = await resp.json()

        if resp.status != 200:
            error_msg = data.get('error', {}).get('message', str(data))
            raise ModuleError(f"OpenAI API error: {error_msg}")

        choice = data['choices'][0]
        usage = data.get('usage', {})

        return {
            'ok': True,
            'data': {
                'analysis': choice['message']['content'],
                'model': data.get('model', model),
                'provider': 'openai',
                'tokens_used': usage.get('total_tokens', 0),
            },
        }


async def _call_anthropic_vision(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int,
    image_b64: str | None,
    image_url: str,
    media_type: str,
) -> Dict[str, Any]:
    """Call Anthropic Vision API."""
    # Build image source
    if image_b64:
        image_source = {
            "type": "base64",
            "media_type": media_type,
            "data": image_b64,
        }
    else:
        # For URL, we need to download and encode
        async with session.get(image_url) as img_resp:
            if img_resp.status != 200:
                raise ModuleError(f"Failed to download image from URL: {image_url}")
            img_data = await img_resp.read()
            content_type = img_resp.headers.get('Content-Type', media_type)
            image_source = {
                "type": "base64",
                "media_type": content_type.split(';')[0],
                "data": base64.b64encode(img_data).decode('utf-8'),
            }

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": image_source,
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with session.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers=headers,
    ) as resp:
        data = await resp.json()

        if resp.status != 200:
            error_msg = data.get('error', {}).get('message', str(data))
            raise ModuleError(f"Anthropic API error: {error_msg}")

        content_blocks = data.get('content', [])
        analysis = ''
        for block in content_blocks:
            if block.get('type') == 'text':
                analysis += block.get('text', '')

        usage = data.get('usage', {})
        tokens_used = usage.get('input_tokens', 0) + usage.get('output_tokens', 0)

        return {
            'ok': True,
            'data': {
                'analysis': analysis,
                'model': data.get('model', model),
                'provider': 'anthropic',
                'tokens_used': tokens_used,
            },
        }
