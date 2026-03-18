# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
LLM Client Mixin

Shared LLM calling logic for agent modules.
Supports: OpenAI, Anthropic, Google Gemini, Ollama (local).
"""

import logging
import os
from typing import Dict, List

import aiohttp

from .....constants import (
    OLLAMA_DEFAULT_URL,
    DEFAULT_LLM_MAX_TOKENS,
    EnvVars,
    APIEndpoints,
)

logger = logging.getLogger(__name__)


class LLMClientMixin:
    """
    Mixin providing LLM calling capabilities.

    Supported providers: openai, anthropic, gemini, ollama
    """

    llm_provider: str
    model: str
    ollama_url: str
    temperature: float
    api_key: str

    PROVIDER_CHOICES = [
        {'label': 'OpenAI (Cloud)', 'value': 'openai'},
        {'label': 'Anthropic (Cloud)', 'value': 'anthropic'},
        {'label': 'Google Gemini (Cloud)', 'value': 'gemini'},
        {'label': 'Ollama (Local)', 'value': 'ollama'},
    ]

    def validate_llm_params(self, params: dict) -> None:
        """Validate and set LLM parameters."""
        self.llm_provider = params.get('llm_provider', 'openai')
        self.model = params.get('model', APIEndpoints.DEFAULT_OPENAI_MODEL)
        self.ollama_url = params.get('ollama_url', OLLAMA_DEFAULT_URL)
        self.temperature = params.get('temperature', 0.7)

        if self.llm_provider == 'openai':
            self.api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
            if not self.api_key:
                raise ValueError(
                    f"{EnvVars.OPENAI_API_KEY} environment variable is required for OpenAI provider"
                )
        elif self.llm_provider == 'anthropic':
            self.api_key = os.environ.get(EnvVars.ANTHROPIC_API_KEY)
            if not self.api_key:
                raise ValueError(
                    f"{EnvVars.ANTHROPIC_API_KEY} environment variable is required for Anthropic provider"
                )
            if self.model == APIEndpoints.DEFAULT_OPENAI_MODEL:
                self.model = APIEndpoints.DEFAULT_ANTHROPIC_MODEL
        elif self.llm_provider == 'gemini':
            self.api_key = os.environ.get('GOOGLE_AI_API_KEY')
            if not self.api_key:
                raise ValueError(
                    "GOOGLE_AI_API_KEY environment variable is required for Gemini provider"
                )
            if self.model == APIEndpoints.DEFAULT_OPENAI_MODEL:
                self.model = APIEndpoints.DEFAULT_GEMINI_MODEL
        elif self.llm_provider == 'ollama':
            self.api_key = None
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call LLM based on configured provider."""
        if self.llm_provider == 'openai':
            return await self._call_openai(messages)
        elif self.llm_provider == 'anthropic':
            return await self._call_anthropic(messages)
        elif self.llm_provider == 'gemini':
            return await self._call_gemini(messages)
        elif self.llm_provider == 'ollama':
            return await self._call_ollama(messages)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise ImportError("OpenAI library not installed. Install with: pip install openai")

        client = openai.AsyncOpenAI(api_key=self.api_key, timeout=120.0)
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=DEFAULT_LLM_MAX_TOKENS,
        )
        return response.choices[0].message.content

    async def _call_anthropic(self, messages: List[Dict[str, str]]) -> str:
        """Call Anthropic Claude API via HTTP."""
        # Separate system message from conversation messages
        system_text = None
        api_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_text = msg['content']
            else:
                api_messages.append({'role': msg['role'], 'content': msg['content']})

        headers = {
            'x-api-key': self.api_key,
            'anthropic-version': APIEndpoints.ANTHROPIC_API_VERSION,
            'content-type': 'application/json',
        }

        payload = {
            'model': self.model,
            'messages': api_messages,
            'max_tokens': DEFAULT_LLM_MAX_TOKENS,
            'temperature': self.temperature,
        }
        if system_text:
            payload['system'] = system_text

        async with aiohttp.ClientSession() as session:
            async with session.post(
                APIEndpoints.ANTHROPIC_MESSAGES_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Anthropic API error ({response.status}): {error_text}")
                data = await response.json()

        content_blocks = data.get('content', [])
        text_parts = [b['text'] for b in content_blocks if b.get('type') == 'text']
        return ''.join(text_parts)

    async def _call_gemini(self, messages: List[Dict[str, str]]) -> str:
        """Call Google Gemini API via HTTP."""
        # Convert messages to Gemini format
        contents = []
        system_instruction = None
        for msg in messages:
            if msg['role'] == 'system':
                system_instruction = msg['content']
            else:
                role = 'user' if msg['role'] == 'user' else 'model'
                contents.append({
                    'role': role,
                    'parts': [{'text': msg['content']}],
                })

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

        payload = {
            'contents': contents,
            'generationConfig': {
                'temperature': self.temperature,
                'maxOutputTokens': DEFAULT_LLM_MAX_TOKENS,
            },
        }
        if system_instruction:
            payload['systemInstruction'] = {
                'parts': [{'text': system_instruction}],
            }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Gemini API error ({response.status}): {error_text}")
                data = await response.json()

        candidates = data.get('candidates', [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get('content', {}).get('parts', [])
        return ''.join(p.get('text', '') for p in parts)

    async def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        """Call local Ollama API."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": DEFAULT_LLM_MAX_TOKENS,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error (status {response.status}): {error_text}")
                result = await response.json()

        return result.get('message', {}).get('content', '')
