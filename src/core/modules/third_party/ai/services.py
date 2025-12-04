"""
AI Integration Modules
Provides integrations with AI services like Anthropic Claude and Google Gemini
"""
import logging
import os

import aiohttp

from ...registry import register_module
from ....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='api.anthropic.chat',
    version='1.0.0',
    category='ai',
    tags=['ai', 'anthropic', 'claude', 'llm', 'chat', 'api'],
    label='Claude Chat',
    label_key='modules.api.anthropic.chat.label',
    description='Send a chat message to Anthropic Claude AI and get a response',
    description_key='modules.api.anthropic.chat.description',
    icon='Brain',
    color='#D97757',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_receive_from=['data.*', 'file.*', 'browser.*'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Phase 2: Execution settings
    timeout=60,  # AI responses can take up to 60s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple AI calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs ANTHROPIC_API_KEY
    handles_sensitive_data=True,  # User messages may contain sensitive info
    required_permissions=['network.access', 'ai.api'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.api.anthropic.chat.params.api_key.label',
            'description': 'Anthropic API key (defaults to env.ANTHROPIC_API_KEY)',
            'description_key': 'modules.api.anthropic.chat.params.api_key.description',
            'placeholder': '${env.ANTHROPIC_API_KEY}',
            'required': False,
            'secret': True
        },
        'model': {
            'type': 'string',
            'label': 'Model',
            'label_key': 'modules.api.anthropic.chat.params.model.label',
            'description': 'Claude model to use',
            'description_key': 'modules.api.anthropic.chat.params.model.description',
            'default': APIEndpoints.DEFAULT_ANTHROPIC_MODEL,
            'required': False,
            'options': [
                {'value': 'claude-3-5-sonnet-20241022', 'label': 'Claude 3.5 Sonnet'},
                {'value': 'claude-3-opus-20240229', 'label': 'Claude 3 Opus'},
                {'value': 'claude-3-haiku-20240307', 'label': 'Claude 3 Haiku'}
            ]
        },
        'messages': {
            'type': 'array',
            'label': 'Messages',
            'label_key': 'modules.api.anthropic.chat.params.messages.label',
            'description': 'Array of message objects with role and content',
            'description_key': 'modules.api.anthropic.chat.params.messages.description',
            'required': True,
            'items': {
                'type': 'object',
                'properties': {
                    'role': {'type': 'string', 'enum': ['user', 'assistant']},
                    'content': {'type': 'string'}
                }
            }
        },
        'max_tokens': {
            'type': 'number',
            'label': 'Max Tokens',
            'label_key': 'modules.api.anthropic.chat.params.max_tokens.label',
            'description': 'Maximum tokens in response',
            'description_key': 'modules.api.anthropic.chat.params.max_tokens.description',
            'default': 1024,
            'required': False,
            'min': 1,
            'max': 4096
        },
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'label_key': 'modules.api.anthropic.chat.params.temperature.label',
            'description': 'Sampling temperature (0-1). Higher values make output more random',
            'description_key': 'modules.api.anthropic.chat.params.temperature.description',
            'default': 1.0,
            'required': False,
            'min': 0,
            'max': 1
        },
        'system': {
            'type': 'string',
            'label': 'System Prompt',
            'label_key': 'modules.api.anthropic.chat.params.system.label',
            'description': 'System prompt to guide Claude behavior',
            'description_key': 'modules.api.anthropic.chat.params.system.description',
            'required': False,
            'multiline': True
        }
    },
    output_schema={
        'content': {
            'type': 'string',
            'description': 'Claude response text'
        },
        'model': {
            'type': 'string',
            'description': 'Model used for response'
        },
        'stop_reason': {
            'type': 'string',
            'description': 'Why the model stopped generating (end_turn, max_tokens, etc)'
        },
        'usage': {
            'type': 'object',
            'description': 'Token usage statistics',
            'properties': {
                'input_tokens': {'type': 'number'},
                'output_tokens': {'type': 'number'}
            }
        }
    },
    examples=[
        {
            'title': 'Simple question',
            'title_key': 'modules.api.anthropic.chat.examples.simple.title',
            'params': {
                'messages': [
                    {'role': 'user', 'content': 'What is the capital of France?'}
                ],
                'max_tokens': 100
            }
        },
        {
            'title': 'Text summarization',
            'title_key': 'modules.api.anthropic.chat.examples.summarize.title',
            'params': {
                'system': 'You are a helpful assistant that summarizes text concisely.',
                'messages': [
                    {'role': 'user', 'content': 'Summarize this article: ${article_text}'}
                ],
                'max_tokens': 500
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://docs.anthropic.com/claude/reference/messages_post'
)
async def anthropic_chat(context):
    """Send chat message to Anthropic Claude API"""
    params = context['params']

    # Get API key from params or environment
    api_key = params.get('api_key') or os.getenv(EnvVars.ANTHROPIC_API_KEY)
    if not api_key:
        raise ValueError(f"API key required: provide 'api_key' param or set {EnvVars.ANTHROPIC_API_KEY} env variable")

    # Prepare request
    url = APIEndpoints.ANTHROPIC_MESSAGES_URL
    headers = {
        'x-api-key': api_key,
        'anthropic-version': APIEndpoints.ANTHROPIC_API_VERSION,
        'content-type': 'application/json'
    }

    payload = {
        'model': params.get('model', APIEndpoints.DEFAULT_ANTHROPIC_MODEL),
        'messages': params['messages'],
        'max_tokens': params.get('max_tokens', 1024)
    }

    # Optional parameters
    if params.get('temperature') is not None:
        payload['temperature'] = params['temperature']
    if params.get('system'):
        payload['system'] = params['system']

    # Make API request
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Anthropic API error ({response.status}): {error_text}")

            result = await response.json()

    # Extract response
    return {
        'content': result['content'][0]['text'],
        'model': result['model'],
        'stop_reason': result['stop_reason'],
        'usage': {
            'input_tokens': result['usage']['input_tokens'],
            'output_tokens': result['usage']['output_tokens']
        }
    }


@register_module(
    module_id='api.google_gemini.chat',
    version='1.0.0',
    category='ai',
    tags=['ai', 'google', 'gemini', 'llm', 'chat', 'api'],
    label='Google Gemini Chat',
    label_key='modules.api.google_gemini.chat.label',
    description='Send a chat message to Google Gemini AI and get a response',
    description_key='modules.api.google_gemini.chat.description',
    icon='Sparkles',
    color='#4285F4',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_receive_from=['data.*', 'file.*', 'browser.*'],
    can_connect_to=['data.*', 'notification.*', 'file.*'],

    # Phase 2: Execution settings
    timeout=60,  # AI responses can take up to 60s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple AI calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs GOOGLE_AI_API_KEY
    handles_sensitive_data=True,  # User prompts may contain sensitive info
    required_permissions=['network.access', 'ai.api'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.api.google_gemini.chat.params.api_key.label',
            'description': 'Google AI API key (defaults to env.GOOGLE_AI_API_KEY)',
            'description_key': 'modules.api.google_gemini.chat.params.api_key.description',
            'placeholder': '${env.GOOGLE_AI_API_KEY}',
            'required': False,
            'secret': True
        },
        'model': {
            'type': 'string',
            'label': 'Model',
            'label_key': 'modules.api.google_gemini.chat.params.model.label',
            'description': 'Gemini model to use',
            'description_key': 'modules.api.google_gemini.chat.params.model.description',
            'default': APIEndpoints.DEFAULT_GEMINI_MODEL,
            'required': False,
            'options': [
                {'value': 'gemini-1.5-pro', 'label': 'Gemini 1.5 Pro'},
                {'value': 'gemini-1.5-flash', 'label': 'Gemini 1.5 Flash'},
                {'value': 'gemini-pro', 'label': 'Gemini Pro'}
            ]
        },
        'prompt': {
            'type': 'string',
            'label': 'Prompt',
            'label_key': 'modules.api.google_gemini.chat.params.prompt.label',
            'description': 'The text prompt to send to Gemini',
            'description_key': 'modules.api.google_gemini.chat.params.prompt.description',
            'required': True,
            'multiline': True,
            'placeholder': 'What is the meaning of life?'
        },
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'label_key': 'modules.api.google_gemini.chat.params.temperature.label',
            'description': 'Controls randomness (0-2). Higher values make output more random',
            'description_key': 'modules.api.google_gemini.chat.params.temperature.description',
            'default': 1.0,
            'required': False,
            'min': 0,
            'max': 2
        },
        'max_output_tokens': {
            'type': 'number',
            'label': 'Max Output Tokens',
            'label_key': 'modules.api.google_gemini.chat.params.max_output_tokens.label',
            'description': 'Maximum number of tokens in response',
            'description_key': 'modules.api.google_gemini.chat.params.max_output_tokens.description',
            'default': 2048,
            'required': False,
            'min': 1,
            'max': 8192
        }
    },
    output_schema={
        'text': {
            'type': 'string',
            'description': 'Generated text response from Gemini'
        },
        'model': {
            'type': 'string',
            'description': 'Model used for generation'
        },
        'candidates': {
            'type': 'array',
            'description': 'All candidate responses'
        }
    },
    examples=[
        {
            'title': 'Simple question',
            'title_key': 'modules.api.google_gemini.chat.examples.simple.title',
            'params': {
                'prompt': 'Explain quantum computing in simple terms'
            }
        },
        {
            'title': 'Content generation',
            'title_key': 'modules.api.google_gemini.chat.examples.generate.title',
            'params': {
                'prompt': 'Write a professional email about ${topic}',
                'temperature': 0.7,
                'max_output_tokens': 500
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    docs_url='https://ai.google.dev/api/rest/v1/models/generateContent'
)
async def google_gemini_chat(context):
    """Send chat message to Google Gemini API"""
    params = context['params']

    # Get API key from params or environment
    api_key = params.get('api_key') or os.getenv(EnvVars.GOOGLE_AI_API_KEY)
    if not api_key:
        raise ValueError(f"API key required: provide 'api_key' param or set {EnvVars.GOOGLE_AI_API_KEY} env variable")

    model = params.get('model', APIEndpoints.DEFAULT_GEMINI_MODEL)

    # Prepare request
    url = APIEndpoints.google_gemini_generate(model, api_key)

    payload = {
        'contents': [
            {
                'parts': [
                    {'text': params['prompt']}
                ]
            }
        ]
    }

    # Generation config
    generation_config = {}
    if params.get('temperature') is not None:
        generation_config['temperature'] = params['temperature']
    if params.get('max_output_tokens'):
        generation_config['maxOutputTokens'] = params['max_output_tokens']

    if generation_config:
        payload['generationConfig'] = generation_config

    # Make API request
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Google Gemini API error ({response.status}): {error_text}")

            result = await response.json()

    # Extract response
    candidates = result.get('candidates', [])
    if not candidates:
        raise Exception("No response generated by Gemini")

    text = candidates[0]['content']['parts'][0]['text']

    return {
        'text': text,
        'model': model,
        'candidates': candidates
    }
