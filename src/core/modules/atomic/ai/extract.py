# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Extract Module
Extract structured data from text using LLM.
"""

import json
import logging
import os
import re
from typing import Any, Dict

import aiohttp

from ...registry import register_module
from ...schema import compose, field
from ...errors import ValidationError, ModuleError

logger = logging.getLogger(__name__)


@register_module(
    module_id='ai.extract',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='extract',
    tags=['ai', 'extract', 'structured', 'llm', 'json'],
    label='AI Extract',
    label_key='modules.ai.extract.label',
    description='Extract structured data from text using LLM',
    description_key='modules.ai.extract.description',
    icon='Database',
    color='#10B981',

    input_types=['string', 'object'],
    output_types=['object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    timeout_ms=120000,
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
            label='Input Text',
            label_key='modules.ai.extract.params.text',
            description='The text to extract structured data from',
            description_key='modules.ai.extract.params.text.description',
            required=True,
            placeholder='Paste the text to extract data from...',
        ),
        field(
            'schema',
            type='object',
            label='Output Schema',
            label_key='modules.ai.extract.params.schema',
            description='JSON schema describing the desired output structure',
            description_key='modules.ai.extract.params.schema.description',
            required=True,
        ),
        field(
            'instructions',
            type='string',
            format='multiline',
            label='Instructions',
            label_key='modules.ai.extract.params.instructions',
            description='Additional extraction instructions for the LLM',
            description_key='modules.ai.extract.params.instructions.description',
            required=False,
            placeholder='Extract all person names and their roles...',
        ),
        field(
            'provider',
            type='select',
            label='Provider',
            label_key='modules.ai.extract.params.provider',
            description='LLM provider',
            description_key='modules.ai.extract.params.provider.description',
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
            label_key='modules.ai.extract.params.model',
            description='Model to use for extraction',
            description_key='modules.ai.extract.params.model.description',
            required=False,
            default='gpt-4o-mini',
            placeholder='gpt-4o-mini',
        ),
        field(
            'api_key',
            type='string',
            format='password',
            label='API Key',
            label_key='modules.ai.extract.params.api_key',
            description='API key (falls back to environment variable)',
            description_key='modules.ai.extract.params.api_key.description',
            required=False,
        ),
        field(
            'temperature',
            type='number',
            label='Temperature',
            label_key='modules.ai.extract.params.temperature',
            description='LLM temperature (0 = deterministic)',
            description_key='modules.ai.extract.params.temperature.description',
            required=False,
            default=0,
            min=0,
            max=1,
        ),
    ),

    output_schema={
        'extracted': {
            'type': 'object',
            'description': 'The extracted structured data',
            'description_key': 'modules.ai.extract.output.extracted.description',
        },
        'model': {
            'type': 'string',
            'description': 'Model used for extraction',
            'description_key': 'modules.ai.extract.output.model.description',
        },
        'raw_response': {
            'type': 'string',
            'description': 'Raw LLM response text',
            'description_key': 'modules.ai.extract.output.raw_response.description',
        },
    },

    examples=[
        {
            'title': 'Extract Contact Info',
            'title_key': 'modules.ai.extract.examples.contact.title',
            'params': {
                'text': 'John Smith is a senior engineer at Acme Corp. Email: john@acme.com',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string'},
                        'title': {'type': 'string'},
                        'company': {'type': 'string'},
                        'email': {'type': 'string'},
                    },
                },
                'provider': 'openai',
                'model': 'gpt-4o-mini',
            },
        },
        {
            'title': 'Extract Invoice Data',
            'title_key': 'modules.ai.extract.examples.invoice.title',
            'params': {
                'text': 'Invoice #1234 from Acme Corp. Total: $500.00. Due: 2024-03-01',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'invoice_number': {'type': 'string'},
                        'vendor': {'type': 'string'},
                        'total': {'type': 'number'},
                        'due_date': {'type': 'string'},
                    },
                },
                'instructions': 'Extract all invoice fields. Parse amounts as numbers.',
            },
        },
    ],
    author='Flyto Team',
    license='MIT',
)
async def ai_extract(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured data from text using LLM."""
    params = context['params']
    text = params['text']
    schema = params['schema']
    instructions = params.get('instructions', '')
    provider = params.get('provider', 'openai')
    model = params.get('model', 'gpt-4o-mini')
    api_key = params.get('api_key')
    temperature = params.get('temperature', 0)

    if not text:
        raise ValidationError("Input text is required", field="text")

    if not schema:
        raise ValidationError("Output schema is required", field="schema")

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

    # Build extraction prompt
    schema_str = json.dumps(schema, indent=2)
    system_prompt = (
        "You are a data extraction assistant. Extract structured data from the "
        "provided text according to the given JSON schema. Return ONLY valid JSON "
        "matching the schema. Do not include any explanations or markdown formatting."
    )
    if instructions:
        system_prompt += f"\n\nAdditional instructions: {instructions}"

    user_prompt = (
        f"Extract data from the following text according to this schema:\n\n"
        f"Schema:\n```json\n{schema_str}\n```\n\n"
        f"Text:\n{text}\n\n"
        f"Return ONLY the extracted JSON object."
    )

    try:
        async with aiohttp.ClientSession() as session:
            if provider == 'openai':
                return await _call_openai_extract(
                    session, api_key, model, system_prompt, user_prompt, temperature,
                )
            elif provider == 'anthropic':
                return await _call_anthropic_extract(
                    session, api_key, model, system_prompt, user_prompt, temperature,
                )
            else:
                raise ValidationError(
                    f"Unsupported provider: {provider}",
                    field="provider",
                )
    except aiohttp.ClientError as e:
        raise ModuleError(f"API request failed: {e}")


def _parse_json_response(raw: str) -> dict:
    """Try to parse JSON from LLM response, handling common formats."""
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } block
    brace_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find first [ ... ] block
    bracket_match = re.search(r'\[.*\]', raw, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ModuleError(
        "Failed to parse JSON from LLM response",
        details={"raw_response": raw[:500]},
    )


async def _call_openai_extract(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> Dict[str, Any]:
    """Call OpenAI API for structured extraction."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
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

        raw_response = data['choices'][0]['message']['content']
        extracted = _parse_json_response(raw_response)

        return {
            'ok': True,
            'data': {
                'extracted': extracted,
                'model': data.get('model', model),
                'raw_response': raw_response,
            },
        }


async def _call_anthropic_extract(
    session: aiohttp.ClientSession,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> Dict[str, Any]:
    """Call Anthropic API for structured extraction."""
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
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
        raw_response = ''
        for block in content_blocks:
            if block.get('type') == 'text':
                raw_response += block.get('text', '')

        extracted = _parse_json_response(raw_response)

        return {
            'ok': True,
            'data': {
                'extracted': extracted,
                'model': data.get('model', model),
                'raw_response': raw_response,
            },
        }
