# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
OpenAI Integration Modules

Provides OpenAI GPT chat and DALL-E image generation.

HOW FAR AN OPENAI CALL IS FOLLOWED

ACCEPTED, on both modules' returning path, and for the same reason as every
other API module here: one request, the reply to that request, no read-back.
There is no `response.status` to point at in these two -- the SDK raises on a
non-2xx -- so what stands in for it is the parsed object itself: the client
handed back a completion, which it only does when the peer answered.

The image module is the more interesting of the two, because it is the one
where OBSERVED looks available and is not. It returns URLs. A URL is not an
image: nothing here fetches one, so no byte of any generated picture has been
seen by this process, and the effect actually claimed is "OpenAI says it made
these and put them at these addresses". Those addresses expire. Claiming
OBSERVED off a URL would be `file.write`'s `bytes_written` with a hostname on
the front.

ERROR PATHS CARRY NOTHING, and cannot: both `execute` bodies wrap everything in
`except Exception -> raise RuntimeError`, so a refusal, a rate limit and a
timeout all leave as raised exceptions and the payload is discarded. The
timeout is the loss that matters -- it is the textbook INDETERMINATE, and a
caller who retries it pays twice.
"""
import logging
import os
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import EnvVars, APIEndpoints
from ....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _sdk_answered(operation: str) -> Dict[str, Any]:
    """What replaces a status line when an SDK, not aiohttp, made the call.

    `openai.AsyncOpenAI` raises on every non-2xx, so a returned response object
    IS the 2xx: reaching this line means a server received the request and
    answered it. That is the distance between DISPATCHED and ACCEPTED, and it
    is the whole distance travelled -- an SDK that parsed a reply has not
    observed anything about the world.
    """
    return {
        'kind': 'openai_reply_parsed',
        'operation': operation,
        'measured_by': 'the SDK returned a response object instead of raising',
        'detail': (
            'The client raises on any non-2xx, so a returned object means a '
            'server answered. Nothing corroborates what it said.'
        ),
    }


@register_module(
    module_id='api.openai.chat',
    version='1.0.0',
    category='ai',
    subcategory='ai',
    tags=['ai', 'openai', 'gpt', 'chat', 'llm', 'ssrf_protected'],
    label='OpenAI Chat',
    label_key='modules.api.openai.chat.label',
    description='Send a chat message to OpenAI GPT models',
    description_key='modules.api.openai.chat.description',
    icon='MessageCircle',
    color='#10A37F',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_connect_to=['data.*', 'notify.*', 'file.*'],
    can_receive_from=['data.*', 'string.*', 'file.*', 'http.*', 'flow.*'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # AI responses can take time
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY'],
    handles_sensitive_data=True,  # User prompts may contain PII
    required_permissions=['ai.api'],

    params_schema={
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'modules.api.openai.chat.params.prompt.label',
            'description': 'The message to send to GPT',
            'description_key': 'modules.api.openai.chat.params.prompt.description',
            'required': True,
            'multiline': True
        ,
            'placeholder': 'Enter your prompt...',
},
        'model': {
            'type': 'select',
            'label': 'Model',
            'label_key': 'modules.api.openai.chat.params.model.label',
            'description': 'OpenAI model to use',
            'description_key': 'modules.api.openai.chat.params.model.description',
            'options': [
                {'label': 'GPT-4o', 'value': 'gpt-4o'},
                {'label': 'GPT-4o Mini', 'value': 'gpt-4o-mini'},
                {'label': 'GPT-4.1', 'value': 'gpt-4.1'},
                {'label': 'GPT-4.1 Mini', 'value': 'gpt-4.1-mini'},
                {'label': 'o3', 'value': 'o3'},
                {'label': 'o3 Mini', 'value': 'o3-mini'},
                {'label': 'o4 Mini', 'value': 'o4-mini'},
                {'label': 'GPT-4 Turbo', 'value': 'gpt-4-turbo-preview'},
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
        ,
            'placeholder': 'You are a helpful assistant.',
}
    },
    output_schema={
        'response': {'type': 'string', 'description': 'Response from the operation',
                'description_key': 'modules.api.openai.chat.output.response.description'},
        'model': {'type': 'string', 'description': 'Model name or identifier',
                'description_key': 'modules.api.openai.chat.output.model.description'},
        'usage': {
            'type': 'object',
            'description': 'Token usage statistics',
                'description_key': 'modules.api.openai.chat.output.usage.description',
            'properties': {
                'prompt_tokens': {'type': 'number', 'description': 'The prompt tokens',
                'description_key': 'modules.api.openai.chat.output.usage.properties.prompt_tokens.description'},
                'completion_tokens': {'type': 'number', 'description': 'The completion tokens',
                'description_key': 'modules.api.openai.chat.output.usage.properties.completion_tokens.description'},
                'total_tokens': {'type': 'number', 'description': 'The total tokens',
                'description_key': 'modules.api.openai.chat.output.usage.properties.total_tokens.description'}
            }
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed. Always "accepted" on the path '
                'that returns: OpenAI answered and reported its own usage, and '
                'nothing corroborates the answer. Error paths raise, so they '
                'carry no outcome at all'
            ),
            'description_key': 'modules.api.openai.chat.output.outcome.description'}
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

    def validate_params(self) -> None:
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
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "OpenAI library not installed. "
                    "Install with: pip install openai"
                )

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

            # Use new OpenAI client (>= 1.0)
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                timeout=120.0,
            )
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            return {
                "response": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "outcome": envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[
                        _sdk_answered('chat.completions.create'),
                        {
                            # Field names avoid the word the vendor uses on
                            # purpose: `_redact_sensitive_output` blanks any key
                            # matching `token`, so `prompt_tokens` here would
                            # reach every hook and stored trace as '[REDACTED]'.
                            # The unit rides as a value, where the pattern does
                            # not look. (The module's own `usage` output above
                            # is redacted for exactly that reason -- an existing
                            # behaviour this envelope routes around rather than
                            # changes.)
                            'kind': 'model_usage_reported',
                            'unit': 'tokens',
                            'input_count': response.usage.prompt_tokens,
                            'output_count': response.usage.completion_tokens,
                            'stop': response.choices[0].finish_reason,
                            'measured_by': 'the usage block of the completion OpenAI returned',
                            'detail': (
                                'OpenAI counting its own work, which is what it '
                                'bills from. Evidence that something ran on the '
                                'other side, and still the peer reporting on '
                                'itself. `stop` of "length" means the answer was '
                                'cut off and the text downstream is a fragment.'
                            ),
                        },
                        {
                            'kind': 'model_named_by_peer',
                            'model': response.model,
                            'measured_by': 'the model field of the completion OpenAI returned',
                            'detail': (
                                'Which model served the request, read from the '
                                'reply rather than echoed from the parameters -- '
                                'an alias resolving to a dated snapshot is the '
                                'ordinary case, and this is the field that shows '
                                'it.'
                            ),
                        },
                    ],
                ),
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
    can_connect_to=['file.*', 'cloud.*', 'notify.*'],
    can_receive_from=['data.*', 'string.*', 'file.*', 'http.*', 'flow.*'],

    # Phase 2: Execution settings
    timeout_ms=120000,  # Image generation takes longer
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY'],
    handles_sensitive_data=False,
    required_permissions=['ai.api'],

    params_schema={
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'modules.api.openai.image.params.prompt.label',
            'description': 'Description of the image to generate',
            'description_key': 'modules.api.openai.image.params.prompt.description',
            'required': True,
            'multiline': True,
            'placeholder': 'Enter your prompt...',
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
            'description': 'List of generated images',
            'items': {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string', 'description': 'URL address'},
                    'revised_prompt': {'type': 'string', 'description': 'The revised prompt'}
                }
            }
        },
        'model': {'type': 'string', 'description': 'Model name or identifier'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed. Always "accepted" on the path '
                'that returns: OpenAI answered with URLs it says host the '
                'images. Nothing fetches them, so no image is observed, and the '
                '`model` output is the one requested rather than one reported'
            )
        }
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

    def validate_params(self) -> None:
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
                "model": self.model,
                "outcome": envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[
                        _sdk_answered('images.generate'),
                        {
                            'kind': 'image_urls_reported',
                            'count': len(images),
                            'measured_by': (
                                'len() over the data array in the reply, and the url '
                                'field of each entry'
                            ),
                            'detail': (
                                'Addresses OpenAI says it put generated images at. '
                                'Nothing here fetches one, so no byte of any image '
                                'has been seen by this process: the count is of URLs '
                                'in a reply, not of pictures that exist. These '
                                'addresses also expire, so a later 404 is not '
                                'evidence that this step was wrong.'
                            ),
                        },
                        {
                            # The same trap `file.write`'s `bytes_written` was:
                            # a value computed from the caller's own input,
                            # identical whether the effect happened or not. The
                            # reply names the model; this module does not read
                            # it, so the field is labelled an echo rather than
                            # left looking like a peer statement.
                            'kind': 'model_echoed_from_request',
                            'model': self.model,
                            'measured_by': None,
                            'detail': (
                                'The model this module ASKED for, copied from the '
                                'parameters. Not read from the reply, so no rung '
                                'rests on it.'
                            ),
                        },
                    ],
                ),
            }
        except Exception as e:
            raise RuntimeError(f"DALL-E API error: {str(e)}")
