"""
LLM Client Mixin

Shared LLM calling logic for agent modules.
"""

import logging
import os
from typing import Dict, List

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

    Requires the following attributes to be set:
    - llm_provider: 'openai' or 'ollama'
    - model: Model name
    - ollama_url: Ollama server URL
    - temperature: Creativity level
    - api_key: API key (for OpenAI)
    """

    llm_provider: str
    model: str
    ollama_url: str
    temperature: float
    api_key: str

    def validate_llm_params(self, params: dict) -> None:
        """
        Validate and set LLM parameters.

        Args:
            params: Parameters dictionary
        """
        self.llm_provider = params.get('llm_provider', 'openai')
        self.model = params.get('model', APIEndpoints.DEFAULT_OPENAI_MODEL)
        self.ollama_url = params.get('ollama_url', OLLAMA_DEFAULT_URL)
        self.temperature = params.get('temperature', 0.7)

        # Validate provider-specific requirements
        if self.llm_provider == 'openai':
            self.api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
            if not self.api_key:
                raise ValueError(
                    f"{EnvVars.OPENAI_API_KEY} environment variable is required for OpenAI provider"
                )
        elif self.llm_provider == 'ollama':
            # No API key needed for local Ollama
            self.api_key = None
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call LLM based on configured provider."""
        if self.llm_provider == 'openai':
            return await self._call_openai(messages)
        elif self.llm_provider == 'ollama':
            return await self._call_ollama(messages)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. "
                "Install with: pip install openai"
            )

        openai.api_key = self.api_key
        response = await openai.ChatCompletion.acreate(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=DEFAULT_LLM_MAX_TOKENS
        )
        return response.choices[0].message.content

    async def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        """Call local Ollama API."""
        import aiohttp

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": DEFAULT_LLM_MAX_TOKENS
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Ollama API error (status {response.status}): {error_text}"
                    )
                result = await response.json()

        message = result.get('message', {})
        return message.get('content', '')
