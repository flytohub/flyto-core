"""
OpenAI Integration Modules

Provides OpenAI GPT chat and DALL-E image generation.
"""
import logging
import os
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import EnvVars, APIEndpoints


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.openai.chat',
    version='1.0.0',
    category='ai',
    subcategory='ai',
    tags=['ai', 'openai', 'gpt', 'chat', 'llm'],
    label='OpenAI Chat',
    label_key='modules.api.openai.chat.label',
    description='Send a chat message to OpenAI GPT models',
    description_key='modules.api.openai.chat.description',
    icon='MessageCircle',
    color='#10A37F',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Phase 2: Execution settings
    timeout=60,  # AI responses can take time
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,  # User prompts may contain PII
    required_permissions=['network.access', 'ai.api'],

    params_schema={
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'modules.api.openai.chat.params.prompt.label',
            'description': 'The message to send to GPT',
            'description_key': 'modules.api.openai.chat.params.prompt.description',
            'required': True,
            'multiline': True
        },
        'model': {
            'type': 'select',
            'label': 'Model',
            'label_key': 'modules.api.openai.chat.params.model.label',
            'description': 'OpenAI model to use',
            'description_key': 'modules.api.openai.chat.params.model.description',
            'options': [
                {'label': 'GPT-4 Turbo', 'value': 'gpt-4-turbo-preview'},
                {'label': 'GPT-4', 'value': 'gpt-4'},
                {'label': 'GPT-3.5 Turbo', 'value': 'gpt-3.5-turbo'}
            ],
            'default': APIEndpoints.DEFAULT_OPENAI_MODEL,
            'required': False
        },
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'label_key': 'modules.api.openai.chat.params.temperature.label',
            'description': 'Sampling temperature (0-2)',
            'description_key': 'modules.api.openai.chat.params.temperature.description',
            'default': 0.7,
            'min': 0,
            'max': 2,
            'required': False
        },
        'max_tokens': {
            'type': 'number',
            'label': 'Max Tokens',
            'label_key': 'modules.api.openai.chat.params.max_tokens.label',
            'description': 'Maximum tokens in response',
            'description_key': 'modules.api.openai.chat.params.max_tokens.description',
            'default': 1000,
            'required': False
        },
        'system_message': {
            'type': 'string',
            'label': 'System Message',
            'label_key': 'modules.api.openai.chat.params.system_message.label',
            'description': 'System role message (optional)',
            'description_key': 'modules.api.openai.chat.params.system_message.description',
            'required': False,
            'multiline': True
        }
    },
    output_schema={
        'response': {'type': 'string'},
        'model': {'type': 'string'},
        'usage': {
            'type': 'object',
            'properties': {
                'prompt_tokens': {'type': 'number'},
                'completion_tokens': {'type': 'number'},
                'total_tokens': {'type': 'number'}
            }
        }
    },
    examples=[
        {
            'title': 'Simple chat',
            'params': {
                'prompt': 'Explain quantum computing in 3 sentences',
                'model': 'gpt-3.5-turbo'
            }
        },
        {
            'title': 'Code generation',
            'params': {
                'prompt': 'Write a Python function to calculate fibonacci numbers',
                'model': 'gpt-4',
                'temperature': 0.2,
                'system_message': 'You are a Python programming expert'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class OpenAIChatModule(BaseModule):
    """OpenAI Chat Module"""

    def validate_params(self):
        self.prompt = self.params.get('prompt')
        self.model = self.params.get('model', APIEndpoints.DEFAULT_OPENAI_MODEL)
        self.temperature = self.params.get('temperature', 0.7)
        self.max_tokens = self.params.get('max_tokens', 1000)
        self.system_message = self.params.get('system_message')

        if not self.prompt:
            raise ValueError("prompt is required")

        # Get API key from environment
        self.api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
        if not self.api_key:
            raise ValueError(f"{EnvVars.OPENAI_API_KEY} environment variable is required")

    async def execute(self) -> Any:
        try:
            # Import OpenAI
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "OpenAI library not installed. "
                    "Install with: pip install openai"
                )

            # Set API key
            openai.api_key = self.api_key

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

            # Make API call
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            return {
                "response": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")


@register_module(
    module_id='api.openai.image',
    version='1.0.0',
    category='ai',
    subcategory='image',
    tags=['ai', 'openai', 'dall-e', 'image', 'generation'],
    label='DALL-E Image Generation',
    label_key='modules.api.openai.image.label',
    description='Generate images using DALL-E',
    description_key='modules.api.openai.image.description',
    icon='Image',
    color='#10A37F',

    # Connection types
    input_types=['text'],
    output_types=['image', 'url'],
    can_connect_to=['file.*', 'cloud.*', 'notification.*'],

    # Phase 2: Execution settings
    timeout=120,  # Image generation takes longer
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=False,
    required_permissions=['network.access', 'ai.api'],

    params_schema={
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'modules.api.openai.image.params.prompt.label',
            'description': 'Description of the image to generate',
            'description_key': 'modules.api.openai.image.params.prompt.description',
            'required': True,
            'multiline': True
        },
        'size': {
            'type': 'select',
            'label': 'Size',
            'label_key': 'modules.api.openai.image.params.size.label',
            'description': 'Image size',
            'description_key': 'modules.api.openai.image.params.size.description',
            'options': [
                {'label': '256x256', 'value': '256x256'},
                {'label': '512x512', 'value': '512x512'},
                {'label': '1024x1024', 'value': '1024x1024'},
                {'label': '1792x1024 (DALL-E 3)', 'value': '1792x1024'},
                {'label': '1024x1792 (DALL-E 3)', 'value': '1024x1792'}
            ],
            'default': '1024x1024',
            'required': False
        },
        'model': {
            'type': 'select',
            'label': 'Model',
            'label_key': 'modules.api.openai.image.params.model.label',
            'description': 'DALL-E model version',
            'description_key': 'modules.api.openai.image.params.model.description',
            'options': [
                {'label': 'DALL-E 3', 'value': 'dall-e-3'},
                {'label': 'DALL-E 2', 'value': 'dall-e-2'}
            ],
            'default': 'dall-e-3',
            'required': False
        },
        'quality': {
            'type': 'select',
            'label': 'Quality',
            'label_key': 'modules.api.openai.image.params.quality.label',
            'description': 'Image quality (DALL-E 3 only)',
            'description_key': 'modules.api.openai.image.params.quality.description',
            'options': [
                {'label': 'Standard', 'value': 'standard'},
                {'label': 'HD', 'value': 'hd'}
            ],
            'default': 'standard',
            'required': False
        },
        'n': {
            'type': 'number',
            'label': 'Number of Images',
            'label_key': 'modules.api.openai.image.params.n.label',
            'description': 'Number of images to generate (1-10)',
            'description_key': 'modules.api.openai.image.params.n.description',
            'default': 1,
            'min': 1,
            'max': 10,
            'required': False
        }
    },
    output_schema={
        'images': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string'},
                    'revised_prompt': {'type': 'string'}
                }
            }
        },
        'model': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Generate artwork',
            'params': {
                'prompt': 'A serene mountain landscape at sunset, digital art',
                'size': '1024x1024',
                'model': 'dall-e-3',
                'quality': 'hd'
            }
        },
        {
            'title': 'Create logo',
            'params': {
                'prompt': 'Modern tech startup logo with blue and green colors',
                'size': '512x512',
                'model': 'dall-e-2',
                'n': 3
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class OpenAIImageModule(BaseModule):
    """DALL-E Image Generation Module"""

    def validate_params(self):
        self.prompt = self.params.get('prompt')
        self.size = self.params.get('size', '1024x1024')
        self.model = self.params.get('model', 'dall-e-3')
        self.quality = self.params.get('quality', 'standard')
        self.n = self.params.get('n', 1)

        if not self.prompt:
            raise ValueError("prompt is required")

        # Get API key from environment
        self.api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
        if not self.api_key:
            raise ValueError(f"{EnvVars.OPENAI_API_KEY} environment variable is required")

    async def execute(self) -> Any:
        try:
            # Import OpenAI
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "OpenAI library not installed. "
                    "Install with: pip install openai"
                )

            # Set API key
            openai.api_key = self.api_key

            # Build request parameters
            params = {
                "model": self.model,
                "prompt": self.prompt,
                "size": self.size,
                "n": self.n
            }

            # Add quality for DALL-E 3
            if self.model == 'dall-e-3':
                params["quality"] = self.quality

            # Make API call
            response = await openai.Image.acreate(**params)

            # Format output
            images = []
            for image_data in response.data:
                image_info = {"url": image_data.url}
                # DALL-E 3 provides revised_prompt
                if hasattr(image_data, 'revised_prompt'):
                    image_info["revised_prompt"] = image_data.revised_prompt
                images.append(image_info)

            return {
                "images": images,
                "model": self.model
            }
        except Exception as e:
            raise RuntimeError(f"DALL-E API error: {str(e)}")
