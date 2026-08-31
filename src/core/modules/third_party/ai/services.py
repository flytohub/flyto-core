# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Integration Modules
Provides integrations with AI services like Anthropic Claude and Google Gemini

HOW FAR AN LLM CALL IS FOLLOWED

ACCEPTED, on the one path that returns. Both modules post once, read the reply
to that post, and stop; there is no second request and nothing to read back --
a completion is not a resource with an address. The strongest true statement is
the one `http.request` makes about any 2xx: a server received this, chose a
reply, and sent it. Reading a peer's report of its own work is taking its word
for it, and a `usage` block is exactly that -- the vendor's count of what it did
and what it will bill for.

The effect that outlives the step is money spent and, for a caller who chains
on it, text that will be treated as an answer. Neither is observable from here.

WHAT THE ERROR PATHS CANNOT SAY, and why they are silent rather than lying.
Both modules `raise` on a non-200 and on a malformed body, so the payload never
survives: a raised module becomes an ERROR result and `to_legacy_dict` discards
everything but the message. An envelope written on those paths could not be
read by anything, which is the same wall `http.request` documents on its
non-2xx branch. So a timeout against a model that had already begun generating
-- the textbook INDETERMINATE, and the case where a retry pays twice -- is
currently reported as a plain step failure. Changing that means changing what a
failed AI step returns, which is a decision about step semantics rather than
about reporting, so it is written down here instead of smuggled in.
"""
import logging
import os
from typing import Any, Dict

import aiohttp

from ...registry import register_module
from ....constants import APIEndpoints, EnvVars
from ....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _reply_read(status: int, vendor: str) -> Dict[str, Any]:
    """The measurement both modules share: a status line came back from the vendor.

    This is the whole distance between DISPATCHED and ACCEPTED, and the whole
    distance these modules travel. Nothing below claims the answer is correct,
    complete, or untruncated -- only that a peer replied.
    """
    return {
        'kind': 'llm_reply_read',
        'vendor': vendor,
        'status': status,
        'measured_by': 'response.status on the reply to this request',
        'detail': (
            'A server received this request and chose a reply. Nothing here '
            'corroborates what the reply says; there is no second request.'
        ),
    }


def _usage_reported(
    *, unit: str, input_count: Any, output_count: Any, stop: Any
) -> Dict[str, Any]:
    """The vendor's account of the work it did, kept labelled as an account.

    Deliberately NOT named with the vendor's own word for the unit.
    `_redact_sensitive_output` blanks any key matching `token`, so a field
    called `input_tokens` would reach every hook and every stored trace as
    '[REDACTED]'. The unit rides as a value instead, where that pattern does
    not look.

    `stop` is carried because it is the one field saying the answer may be
    incomplete: 'max_tokens' / 'MAX_TOKENS' means the model was cut off
    mid-sentence and the text downstream is a fragment. That is not a rung --
    a truncated completion is a completion, and the peer did the work it billed
    for -- but a consumer deciding whether to trust the text needs it.
    """
    return {
        'kind': 'model_usage_reported',
        'unit': unit,
        'input_count': input_count,
        'output_count': output_count,
        'stop': stop,
        'measured_by': 'the usage block of the body the vendor returned',
        'detail': (
            'The vendor counting its own work, which is what it bills from. It '
            'is evidence that something ran on the other side -- these numbers '
            'vary with the request and cannot be produced here -- and it is '
            'still the peer reporting on itself, which is why the rung stops at '
            'accepted.'
        ),
    }


@register_module(
    module_id='api.anthropic.chat',
    version='1.0.0',
    category='ai',
    tags=['ai', 'anthropic', 'claude', 'llm', 'chat', 'api', 'ssrf_protected'],
    label='Claude Chat',
    label_key='modules.api.anthropic.chat.label',
    description='Send a chat message to Anthropic Claude AI and get a response',
    description_key='modules.api.anthropic.chat.description',
    icon='Brain',
    color='#D97757',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    can_receive_from=['data.*', 'string.*', 'file.*', 'http.*', 'flow.*'],
    can_connect_to=['data.*', 'notify.*', 'file.*'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # AI responses can take up to 60s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple AI calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['ANTHROPIC_API_KEY'],
    handles_sensitive_data=True,  # User messages may contain sensitive info
    required_permissions=['ai.api'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.api.anthropic.chat.params.api_key.label',
            'description': 'Anthropic API key (defaults to env.ANTHROPIC_API_KEY)',
            'description_key': 'modules.api.anthropic.chat.params.api_key.description',
            'placeholder': '${env.ANTHROPIC_API_KEY}',
            'required': False,
            'sensitive': True
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
                {'value': 'claude-sonnet-4-6', 'label': 'Claude Sonnet 4.6'},
                {'value': 'claude-opus-4-6', 'label': 'Claude Opus 4.6'},
                {'value': 'claude-haiku-4-5-20251001', 'label': 'Claude Haiku 4.5'},
                {'value': 'claude-3-5-sonnet-20241022', 'label': 'Claude 3.5 Sonnet'},
                {'value': 'claude-3-opus-20240229', 'label': 'Claude 3 Opus'},
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
                    'content': {'type': 'string', 'description': 'Content returned by the operation',
                'description_key': 'modules.api.anthropic.chat.params.messages.properties.content.description'}
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
            'max': 16384
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
        ,
            'placeholder': 'Enter system...',
}
    },
    output_schema={
        'content': {
            'type': 'string',
            'description': 'Claude response text'
        ,
                'description_key': 'modules.api.anthropic.chat.output.content.description'},
        'model': {
            'type': 'string',
            'description': 'Model used for response'
        ,
                'description_key': 'modules.api.anthropic.chat.output.model.description'},
        'stop_reason': {
            'type': 'string',
            'description': 'Why the model stopped generating (end_turn, max_tokens, etc)'
        ,
                'description_key': 'modules.api.anthropic.chat.output.stop_reason.description'},
        'usage': {
            'type': 'object',
            'description': 'Token usage statistics',
                'description_key': 'modules.api.anthropic.chat.output.usage.description',
            'properties': {
                'input_tokens': {'type': 'number', 'description': 'The input tokens',
                'description_key': 'modules.api.anthropic.chat.output.usage.properties.input_tokens.description'},
                'output_tokens': {'type': 'number', 'description': 'The output tokens',
                'description_key': 'modules.api.anthropic.chat.output.usage.properties.output_tokens.description'}
            }
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed. Always "accepted" on the path '
                'that returns: Anthropic answered and reported its own usage, '
                'and nothing here corroborates the answer. Error paths raise, so '
                'they carry no outcome at all'
            ),
            'description_key': 'modules.api.anthropic.chat.output.outcome.description'}
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

    # Make API request with timeout
    # SECURITY: Set timeout to prevent hanging API calls
    timeout = aiohttp.ClientTimeout(total=120, connect=30)  # 2 min total for AI
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Anthropic API error ({response.status}): {error_text}")

            status = response.status
            result = await response.json()

    # Extract response
    return {
        'content': result['content'][0]['text'],
        'model': result['model'],
        'stop_reason': result['stop_reason'],
        'usage': {
            'input_tokens': result['usage']['input_tokens'],
            'output_tokens': result['usage']['output_tokens']
        },
        'outcome': envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                _reply_read(status, 'anthropic'),
                _usage_reported(
                    unit='tokens',
                    input_count=result['usage']['input_tokens'],
                    output_count=result['usage']['output_tokens'],
                    stop=result['stop_reason'],
                ),
                {
                    'kind': 'model_named_by_peer',
                    'model': result['model'],
                    'measured_by': 'the model field of the body Anthropic returned',
                    'detail': (
                        'Which model the vendor says served this request. It is '
                        'read from the reply, not echoed from the request, so it '
                        'can differ from the model asked for -- an alias resolving '
                        'to a dated snapshot is the ordinary case.'
                    ),
                },
            ],
        ),
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
    can_receive_from=['data.*', 'string.*', 'file.*', 'http.*', 'flow.*'],
    can_connect_to=['data.*', 'notify.*', 'file.*'],

    # Phase 2: Execution settings
    timeout_ms=60000,  # AI responses can take up to 60s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple AI calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GOOGLE_API_KEY'],
    handles_sensitive_data=True,  # User prompts may contain sensitive info
    required_permissions=['ai.api'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.api.google_gemini.chat.params.api_key.label',
            'description': 'Google AI API key (defaults to env.GOOGLE_AI_API_KEY)',
            'description_key': 'modules.api.google_gemini.chat.params.api_key.description',
            'placeholder': '${env.GOOGLE_AI_API_KEY}',
            'required': False,
            'sensitive': True
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
                {'value': 'gemini-2.5-pro', 'label': 'Gemini 2.5 Pro'},
                {'value': 'gemini-2.5-flash', 'label': 'Gemini 2.5 Flash'},
                {'value': 'gemini-2.0-flash', 'label': 'Gemini 2.0 Flash'},
                {'value': 'gemini-1.5-pro', 'label': 'Gemini 1.5 Pro'},
                {'value': 'gemini-1.5-flash', 'label': 'Gemini 1.5 Flash'},
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
        },
        'outcome': {
            'type': 'object',
            'description': (
                'How far the effect was followed. Always "accepted" on the path '
                'that returns: Gemini answered and reported its own usage. Note '
                'that the `model` output above is the model REQUESTED, echoed '
                'from the parameters, and the outcome effects say so'
            )
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
    # SECURITY: API key passed via header, not URL query parameter
    url = APIEndpoints.google_gemini_generate(model)
    headers = {
        'x-goog-api-key': api_key,
        'Content-Type': 'application/json'
    }

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

    # Make API request with timeout
    # SECURITY: Set timeout to prevent hanging API calls
    timeout = aiohttp.ClientTimeout(total=120, connect=30)  # 2 min total for AI
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Google Gemini API error ({response.status}): {error_text}")

            status = response.status
            result = await response.json()

    # Extract response
    candidates = result.get('candidates', [])
    if not candidates:
        raise Exception("No response generated by Gemini")

    text = candidates[0]['content']['parts'][0]['text']

    # `usageMetadata` is absent on some Gemini responses; None is the honest
    # value for a count that was not reported, and 0 would be a number written
    # here rather than one that crossed the wire.
    usage = result.get('usageMetadata') or {}

    return {
        'text': text,
        'model': model,
        'candidates': candidates,
        'outcome': envelope(
            Outcome.ACCEPTED,
            claim_by=ClaimBy.NONE,
            effects=[
                _reply_read(status, 'google_gemini'),
                _usage_reported(
                    unit='tokens',
                    input_count=usage.get('promptTokenCount'),
                    output_count=usage.get('candidatesTokenCount'),
                    stop=candidates[0].get('finishReason'),
                ),
                {
                    'kind': 'candidates_returned',
                    'count': len(candidates),
                    'measured_by': 'len() over the candidates array Gemini returned',
                    'detail': (
                        'How many candidate completions came back. Only the first '
                        'is read into `text`.'
                    ),
                },
                {
                    # Named so that nobody mistakes it for evidence. This is the
                    # `file.write` mistake in miniature: the module's `model`
                    # output is `params['model']`, the caller's own string,
                    # identical whether Gemini answered or not. Gemini's reply
                    # carries `modelVersion`; this module does not read it, so
                    # the honest thing is to say the field is an echo rather
                    # than to quietly let it look like a peer statement.
                    'kind': 'model_echoed_from_request',
                    'model': model,
                    'measured_by': None,
                    'detail': (
                        "The model this module ASKED for, copied from the "
                        'request. Unlike the Anthropic module beside it, nothing '
                        'here reads which model actually served the call, so '
                        'this field is not evidence of anything and no rung '
                        'rests on it.'
                    ),
                },
            ],
        ),
    }
