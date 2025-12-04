"""
Local Ollama Integration Module

Provides local LLM support via Ollama for completely offline AI agent execution.
"""
import logging
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import OLLAMA_DEFAULT_URL


logger = logging.getLogger(__name__)


@register_module(
    module_id='ai.local_ollama.chat',
    version='1.0.0',
    category='ai',
    subcategory='ai',
    tags=['ai', 'ollama', 'local', 'llm', 'offline', 'chat'],
    label='Local Ollama Chat',
    label_key='modules.ai.local_ollama.chat.label',
    description='Chat with local LLM via Ollama (completely offline)',
    description_key='modules.ai.local_ollama.chat.description',
    icon='Server',
    color='#000000',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Phase 2: Execution settings
    timeout=120,  # Local LLM can take time depending on hardware
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,  # No API key needed for local
    handles_sensitive_data=True,  # User prompts may contain PII
    required_permissions=['network.access'],  # For localhost connection

    params_schema={
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'modules.ai.local_ollama.chat.params.prompt.label',
            'description': 'The message to send to the local LLM',
            'description_key': 'modules.ai.local_ollama.chat.params.prompt.description',
            'required': True,
            'multiline': True
        },
        'model': {
            'type': 'select',
            'label': 'Model',
            'label_key': 'modules.ai.local_ollama.chat.params.model.label',
            'description': 'Ollama model to use',
            'description_key': 'modules.ai.local_ollama.chat.params.model.description',
            'options': [
                {'label': 'Llama 2 7B', 'value': 'llama2'},
                {'label': 'Llama 2 13B', 'value': 'llama2:13b'},
                {'label': 'Llama 2 70B', 'value': 'llama2:70b'},
                {'label': 'Mistral 7B', 'value': 'mistral'},
                {'label': 'Mixtral 8x7B', 'value': 'mixtral'},
                {'label': 'CodeLlama 7B', 'value': 'codellama'},
                {'label': 'CodeLlama 13B', 'value': 'codellama:13b'},
                {'label': 'Phi-2', 'value': 'phi'},
                {'label': 'Neural Chat 7B', 'value': 'neural-chat'},
                {'label': 'Starling 7B', 'value': 'starling-lm'}
            ],
            'default': 'llama2',
            'required': False
        },
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'label_key': 'modules.ai.local_ollama.chat.params.temperature.label',
            'description': 'Sampling temperature (0-2)',
            'description_key': 'modules.ai.local_ollama.chat.params.temperature.description',
            'default': 0.7,
            'min': 0,
            'max': 2,
            'required': False
        },
        'system_message': {
            'type': 'string',
            'label': 'System Message',
            'label_key': 'modules.ai.local_ollama.chat.params.system_message.label',
            'description': 'System role message (optional)',
            'description_key': 'modules.ai.local_ollama.chat.params.system_message.description',
            'required': False,
            'multiline': True
        },
        'ollama_url': {
            'type': 'string',
            'label': 'Ollama URL',
            'label_key': 'modules.ai.local_ollama.chat.params.ollama_url.label',
            'description': 'Ollama server URL',
            'description_key': 'modules.ai.local_ollama.chat.params.ollama_url.description',
            'default': OLLAMA_DEFAULT_URL,
            'required': False
        },
        'max_tokens': {
            'type': 'number',
            'label': 'Max Tokens',
            'label_key': 'modules.ai.local_ollama.chat.params.max_tokens.label',
            'description': 'Maximum tokens in response (optional, depends on model)',
            'description_key': 'modules.ai.local_ollama.chat.params.max_tokens.description',
            'required': False
        }
    },
    output_schema={
        'response': {'type': 'string'},
        'model': {'type': 'string'},
        'context': {'type': 'array', 'items': {'type': 'number'}},
        'total_duration': {'type': 'number'},
        'load_duration': {'type': 'number'},
        'prompt_eval_count': {'type': 'number'},
        'eval_count': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Simple local chat',
            'params': {
                'prompt': 'Explain quantum computing in 3 sentences',
                'model': 'llama2'
            }
        },
        {
            'title': 'Code generation with local model',
            'params': {
                'prompt': 'Write a Python function to calculate fibonacci numbers',
                'model': 'codellama',
                'temperature': 0.2,
                'system_message': 'You are a Python programming expert. Write clean, efficient code.'
            }
        },
        {
            'title': 'Local reasoning task',
            'params': {
                'prompt': 'What are the pros and cons of microservices architecture?',
                'model': 'mistral',
                'temperature': 0.7
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class LocalOllamaChatModule(BaseModule):
    """Local Ollama Chat Module - Completely offline LLM"""

    def validate_params(self):
        self.prompt = self.params.get('prompt')
        self.model = self.params.get('model', 'llama2')
        self.temperature = self.params.get('temperature', 0.7)
        self.system_message = self.params.get('system_message')
        self.ollama_url = self.params.get('ollama_url', OLLAMA_DEFAULT_URL)
        self.max_tokens = self.params.get('max_tokens')

        if not self.prompt:
            raise ValueError("prompt is required")

    async def execute(self) -> Any:
        try:
            import aiohttp
            import json

            # Build messages
            messages = []
            if self.system_message:
                messages.append({
                    "role": "system",
                    "content": self.system_message
                })
            messages.append({
                "role": "user",
                "content": self.prompt
            })

            # Build request payload
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature
                }
            }

            # Add max_tokens if specified
            if self.max_tokens:
                payload["options"]["num_predict"] = self.max_tokens

            # Make API call to local Ollama
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(
                            f"Ollama API error (status {response.status}): {error_text}"
                        )

                    result = await response.json()

            # Extract response
            message = result.get('message', {})
            content = message.get('content', '')

            return {
                "response": content,
                "model": result.get('model', self.model),
                "context": result.get('context', []),
                "total_duration": result.get('total_duration', 0),
                "load_duration": result.get('load_duration', 0),
                "prompt_eval_count": result.get('prompt_eval_count', 0),
                "eval_count": result.get('eval_count', 0)
            }

        except aiohttp.ClientError as e:
            raise RuntimeError(
                f"Failed to connect to Ollama at {self.ollama_url}. "
                f"Make sure Ollama is running (ollama serve). Error: {str(e)}"
            )
        except Exception as e:
            raise RuntimeError(f"Local Ollama error: {str(e)}")
