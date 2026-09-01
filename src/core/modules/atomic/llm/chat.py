# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
LLM Chat Module
Interact with LLM APIs for code generation, analysis, and decision making

SECURITY: Includes SSRF protection for custom base URLs.

HOW FAR THIS MODULE FOLLOWS REALITY

ACCEPTED is the ceiling of the happy path, and the reason is the whole point of
putting a rung on an LLM call at all. A completion coming back IS an observation
of a completion. It is not an observation of anything in the world. The provider
ran a model, charged for it, and told us what it produced -- every number in the
answer (`tokens_used`, `finish_reason`, the text itself) is the peer reporting on
its own work, which is the textbook definition of "the other side acknowledged
taking it". Nothing here measures a consequence of the text.

`tokens_used` deserves naming, because it is the `bytes_written` of this module:
it is the number the provider decided to bill, read out of the provider's own
JSON. It is not a measurement we made, and no branch here checks it against
anything. It travels as an effect labelled with what it is rather than as
evidence for a rung.

The interesting rungs are off the ladder:

  a guard refused before the request                    FAILED
      SSRF, the env-credential endpoint check, a missing key, an unknown
      provider. All four return above the first `await`, so no bytes left this
      process and no money was spent. "Definitely nothing happened" and "we
      cannot say" are different answers and only the first one is true here.

  the provider answered with an error object            FAILED
      The request arrived and the peer gave a definite negative. We are not
      guessing.

  the transport failed, or anything raised              INDETERMINATE
      A timeout, a reset connection, a body we could not parse. The request may
      have been delivered, the completion may have run, the account may have
      been billed. Nothing here can tell, and `outcome.py` names exactly this
      case: an observation channel that was severed is indeterminate, never
      failed.

  response_format='json' and nothing parsed             FAILED, claim_by=CALLER
      The one predicate in this module that somebody other than us asked for.
      `response_format` is a caller-supplied contract -- "give me JSON" -- and
      `_parse_json_response` evaluates it on every response. When it comes back
      None the caller's contract broke, which `outcome.py` splits from our own
      inferences being wrong: a caller's expectation that failed is FAILED.

      The reverse does NOT climb: a response that parses is still only ACCEPTED,
      never VERIFIED. VERIFIED means a declared postcondition was evaluated and
      held, and "the peer's own answer is syntactically JSON" is a fact about
      the peer's answer, not about the world. This module declares no
      postcondition and must not; `ceiling_for(None)` caps it at OBSERVED
      anyway, and it has nothing to observe.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ....engine.outcome import ClaimBy, Outcome, envelope
from ...registry import register_module
from ...schema import compose, presets
from ....utils import (
    guarded_client_session,
    validate_url_with_env_config,
    SSRFError,
    assert_env_credential_endpoint_allowed,
    CredentialEndpointError,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The four answers this module is entitled to give, and what earns each.
# ---------------------------------------------------------------------------


def _refused_before_dispatch(reason: str) -> Dict[str, Any]:
    """FAILED, and specifically not INDETERMINATE.

    Every caller of this sits above the first `await` on a network client, so
    nothing was sent, nothing ran and nobody was billed -- and we know that
    rather than infer it. `effects` is empty because nothing about the world
    changed; `claim_by` is NONE because no expectation was adjudicated, the
    request was refused before one could be.
    """
    return envelope(
        Outcome.FAILED,
        effects=[{
            'kind': 'request_not_sent',
            'reason': reason,
            'measured_by': 'a guard that returned before any request was built',
            'detail': (
                'The request never left this process. No completion was '
                'requested and no tokens were billed.'
            ),
        }],
    )


def _provider_refused(provider: str, message: str) -> Dict[str, Any]:
    """FAILED: the request arrived and the peer said no, in its own words."""
    return envelope(
        Outcome.FAILED,
        effects=[{
            'kind': 'provider_error',
            'provider': provider,
            'message': message,
            'measured_by': "the provider's own JSON error object",
            'detail': (
                'The provider answered and the answer was an error. There is no '
                'completion. Whether the attempt was billable is the provider\'s '
                'decision and is not reported here.'
            ),
        }],
    )


def _no_answer(provider: str, error: Any) -> Dict[str, Any]:
    """INDETERMINATE: the textbook one, and it must not be argued down.

    A timeout or a transport error severs the observation channel while the
    request may already have been delivered. FAILED would assert the completion
    did not happen; nothing evaluated that. DISPATCHED would assert we know less
    than we do -- we know an attempt was made.
    """
    return envelope(
        Outcome.INDETERMINATE,
        effects=[{
            'kind': 'no_answer_from_provider',
            'provider': provider,
            'error_type': type(error).__name__ if isinstance(error, BaseException) else None,
            'error': str(error),
            'measured_by': None,
            'detail': (
                'The request was attempted and no usable answer came back. It may '
                'never have arrived, it may have run and been billed, or the '
                'answer may have been lost on the way home. Nothing here can tell '
                'which.'
            ),
        }],
    )


def _completion_outcome(
    *,
    provider: str,
    model: str,
    response_text: str,
    tokens_used: Any,
    finish_reason: Any,
    response_format: str,
    parsed: Any,
) -> Dict[str, Any]:
    """The rung a returned completion earned, which is ACCEPTED or worse."""
    effects = [{
        'kind': 'completion_returned',
        'provider': provider,
        'model': model,
        'response_chars': len(response_text or ''),
        'tokens_billed_by_provider': tokens_used,
        'finish_reason': finish_reason,
        'measured_by': "the provider's own JSON response body",
        'detail': (
            'A completion came back and the provider reported its own token '
            'usage. Both are the peer describing its own work: this is an '
            'observation of a completion, not of anything in the world. Nothing '
            'here checks that the text is correct, that the token count is the '
            'work actually done, or that any effect followed from it.'
        ),
    }]

    # Not a rung change. `length` is the provider telling us it stopped early,
    # which leaves the text a fragment -- worth carrying beside the answer, and
    # the most common reason a `json` response fails to parse below.
    if finish_reason == 'length':
        effects.append({
            'kind': 'completion_truncated',
            'finish_reason': finish_reason,
            'measured_by': "the provider's finish_reason field",
            'detail': (
                'The provider stopped at the token limit rather than at the end '
                'of its answer. The text is a fragment.'
            ),
        })

    if response_format == 'json' and parsed is None:
        return envelope(
            Outcome.FAILED,
            claim_by=ClaimBy.CALLER,
            postcondition="response_format='json': the response parses as JSON",
            effects=effects + [{
                'kind': 'response_format_unmet',
                'requested_format': response_format,
                'measured_by': '_parse_json_response(response_text) is None',
                'detail': (
                    'The caller asked for JSON and none of the three parses '
                    '(direct, fenced block, first brace-delimited object) '
                    'succeeded. `response` still carries the raw text; `parsed` '
                    'is null.'
                ),
            }],
        )

    if response_format == 'json':
        effects.append({
            'kind': 'response_format_met',
            'requested_format': response_format,
            'measured_by': '_parse_json_response(response_text) returned a value',
            'detail': (
                'The caller\'s format contract held. This does not raise the '
                'rung: it is a fact about the shape of the peer\'s own answer, '
                'not about anything in the world.'
            ),
        })

    return envelope(Outcome.ACCEPTED, effects=effects)


@register_module(
    module_id='llm.chat',
    stability="beta",
    version='1.0.0',
    category='atomic',
    subcategory='llm',
    tags=['llm', 'ai', 'chat', 'gpt', 'claude', 'code', 'generation', 'atomic'],
    label='LLM Chat',
    label_key='modules.llm.chat.label',
    description='Interact with LLM APIs for intelligent operations',
    description_key='modules.llm.chat.description',
    icon='Bot',
    color='#10A37F',

    # Connection types
    input_types=['any'],
    output_types=['string', 'object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    # Execution settings
    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read'],

    # Schema-driven params
    params_schema=compose(
        presets.LLM_PROMPT(required=True, placeholder='Analyze this code and suggest improvements...'),
        presets.SYSTEM_PROMPT(placeholder='You are an expert code reviewer...'),
        presets.LLM_CONTEXT(),
        presets.CONVERSATION_MESSAGES(),
        presets.LLM_PROVIDER(default='openai'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.TEMPERATURE(default=0.7),
        presets.MAX_TOKENS(default=2000),
        presets.LLM_RESPONSE_FORMAT(default='text'),
        presets.LLM_API_KEY(),
        presets.LLM_BASE_URL(),
    ),
    output_schema={
        'ok': {
            'type': 'boolean',
            'description': 'Whether the request succeeded'
        ,
                'description_key': 'modules.llm.chat.output.ok.description'},
        'response': {
            'type': 'string',
            'description': 'The LLM response text'
        ,
                'description_key': 'modules.llm.chat.output.response.description'},
        'parsed': {
            'type': 'any',
            'description': 'Parsed response (if JSON format requested)'
        ,
                'description_key': 'modules.llm.chat.output.parsed.description'},
        'model': {
            'type': 'string',
            'description': 'Model used'
        ,
                'description_key': 'modules.llm.chat.output.model.description',
            'placeholder': 'gpt-4o',
},
        'tokens_used': {
            'type': 'number',
            'description': 'Total tokens consumed'
        ,
                'description_key': 'modules.llm.chat.output.tokens_used.description'},
        'finish_reason': {
            'type': 'string',
            'description': 'Why the response ended'
        ,
                'description_key': 'modules.llm.chat.output.finish_reason.description'},
        'outcome': {
            'type': 'object',
            'description': (
                'How far this call was followed into reality: accepted when a '
                'completion came back, failed when a guard refused before the '
                'request or the provider answered with an error, indeterminate '
                'when nothing came back. Never higher than accepted -- a '
                'completion is an observation of a completion, not of the world'
            ),
            'description_key': 'modules.llm.chat.output.outcome.description'}
    },
    examples=[
        {
            'title': 'Code Review',
            'title_key': 'modules.llm.chat.examples.review.title',
            'params': {
                'prompt': 'Review this code for bugs and improvements:\n\n${code}',
                'system_prompt': 'You are an expert code reviewer. Be specific and actionable.',
                'model': 'gpt-4o'
            }
        },
        {
            'title': 'Generate Fix',
            'title_key': 'modules.llm.chat.examples.fix.title',
            'params': {
                'prompt': 'The UI evaluation found these issues: ${issues}\n\nGenerate code fixes.',
                'system_prompt': 'You are a frontend developer. Return only valid code.',
                'response_format': 'code'
            }
        },
        {
            'title': 'Decision Making',
            'title_key': 'modules.llm.chat.examples.decision.title',
            'params': {
                'prompt': 'Based on these test results, should we deploy? ${test_results}',
                'system_prompt': 'You are a DevOps engineer. Return JSON: {"decision": "yes/no", "reason": "..."}',
                'response_format': 'json'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def llm_chat(context: Dict[str, Any]) -> Dict[str, Any]:
    """Interact with LLM APIs"""
    params = context['params']
    prompt = params['prompt']
    system_prompt = params.get('system_prompt', '')
    context_data = params.get('context', {})
    messages = params.get('messages', [])
    provider = params.get('provider', 'openai')
    model = params.get('model', 'gpt-4o')
    temperature = params.get('temperature', 0.7)
    max_tokens = params.get('max_tokens', 2000)
    response_format = params.get('response_format', 'text')
    api_key = params.get('api_key')
    base_url = params.get('base_url')

    # SECURITY: Validate custom base URL for SSRF
    if base_url:
        try:
            validate_url_with_env_config(base_url)
        except SSRFError as e:
            return {
                'ok': False,
                'error': str(e),
                'error_code': 'SSRF_BLOCKED',
                'outcome': _refused_before_dispatch('SSRF_BLOCKED'),
            }

    # Get API key from environment if not provided
    key_from_env = False
    if not api_key:
        env_vars = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'ollama': None  # Ollama doesn't need API key
        }
        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)
            key_from_env = bool(api_key)

    # SECURITY: never forward the operator's env-derived key to a caller-supplied
    # endpoint (GHSA-qq9q-xgm3-xv9g). The SSRF check above does not stop this —
    # it allows public attacker hosts.
    try:
        assert_env_credential_endpoint_allowed(base_url, key_from_env)
    except CredentialEndpointError as e:
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'ENV_KEY_UNTRUSTED_ENDPOINT',
            'outcome': _refused_before_dispatch('ENV_KEY_UNTRUSTED_ENDPOINT'),
        }

    if provider != 'ollama' and not api_key:
        return {
            'ok': False,
            'error': f'API key not provided for {provider}',
            'error_code': 'MISSING_API_KEY',
            'outcome': _refused_before_dispatch('MISSING_API_KEY'),
        }

    # Inject context into prompt
    if context_data:
        for key, value in context_data.items():
            placeholder = f'${{{key}}}'
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))

    # Build messages
    api_messages = []

    if system_prompt:
        # Add format instructions
        format_instructions = {
            'json': '\n\nIMPORTANT: Return valid JSON only.',
            'code': '\n\nIMPORTANT: Return only code, no explanations.',
            'markdown': '\n\nFormat your response as Markdown.'
        }
        system_prompt += format_instructions.get(response_format, '')
        api_messages.append({"role": "system", "content": system_prompt})

    # Add conversation history
    if messages:
        api_messages.extend(messages)

    # Add current prompt
    api_messages.append({"role": "user", "content": prompt})

    # Call appropriate provider
    try:
        if provider == 'openai':
            result = await _call_openai(api_messages, model, temperature, max_tokens, api_key, base_url, response_format)
        elif provider == 'anthropic':
            result = await _call_anthropic(api_messages, model, temperature, max_tokens, api_key)
        elif provider == 'ollama':
            result = await _call_ollama(api_messages, model, temperature, max_tokens, base_url)
        else:
            return {
                'ok': False,
                'error': f'Unknown provider: {provider}',
                'error_code': 'INVALID_PROVIDER',
                'outcome': _refused_before_dispatch('INVALID_PROVIDER'),
            }

        if not result.get('ok'):
            # The provider helpers build their own envelope, because only they
            # know whether the peer refused (FAILED) or never answered
            # (INDETERMINATE). Passing the result through keeps that distinction
            # instead of flattening both into one guess made out here.
            return result

        response_text = result['response']

        # Parse response if needed
        parsed = None
        if response_format == 'json':
            parsed = _parse_json_response(response_text)

        tokens_used = result.get('tokens_used', 0)
        finish_reason = result.get('finish_reason', 'stop')

        logger.info(f"LLM chat completed: {tokens_used} tokens")

        return {
            'ok': True,
            'response': response_text,
            'parsed': parsed,
            'model': model,
            'tokens_used': tokens_used,
            'finish_reason': finish_reason,
            'outcome': _completion_outcome(
                provider=provider,
                model=model,
                response_text=response_text,
                tokens_used=tokens_used,
                finish_reason=finish_reason,
                response_format=response_format,
                parsed=parsed,
            ),
        }

    except Exception as e:
        logger.error(f"LLM chat failed: {e}")
        # Everything reachable from here is downstream of a request having been
        # built and handed to a client: a transport error, a timeout, or a
        # response body whose shape we could not read. In none of those cases do
        # we know whether the completion ran.
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'API_ERROR',
            'outcome': _no_answer(provider, e),
        }


async def _call_openai(
    messages: List[Dict],
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
    base_url: Optional[str],
    response_format: str
) -> Dict[str, Any]:
    """Call OpenAI API"""
    try:
        import httpx
        from ....utils import guarded_httpx_client
    except ImportError:
        import aiohttp
        return await _call_openai_aiohttp(messages, model, temperature, max_tokens, api_key, base_url, response_format)

    url = base_url or "https://api.openai.com/v1"
    url = f"{url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    if response_format == 'json':
        payload["response_format"] = {"type": "json_object"}

    async with guarded_httpx_client(timeout=120) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

    if 'error' in result:
        message = result['error'].get('message', 'Unknown error')
        return {
            'ok': False,
            'error': message,
            'outcome': _provider_refused('openai', message),
        }

    return {
        'ok': True,
        'response': result['choices'][0]['message']['content'],
        'tokens_used': result.get('usage', {}).get('total_tokens', 0),
        'finish_reason': result['choices'][0].get('finish_reason', 'stop')
    }


async def _call_openai_aiohttp(
    messages: List[Dict],
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
    base_url: Optional[str],
    response_format: str
) -> Dict[str, Any]:
    """Call OpenAI API using aiohttp"""
    import aiohttp

    url = base_url or "https://api.openai.com/v1"
    url = f"{url.rstrip('/')}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    if response_format == 'json':
        payload["response_format"] = {"type": "json_object"}

    # SECURITY: Set timeout to prevent hanging API calls
    timeout = aiohttp.ClientTimeout(total=120, connect=30)
    async with guarded_client_session(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.json()

    if 'error' in result:
        message = result['error'].get('message', 'Unknown error')
        return {
            'ok': False,
            'error': message,
            'outcome': _provider_refused('openai', message),
        }

    return {
        'ok': True,
        'response': result['choices'][0]['message']['content'],
        'tokens_used': result.get('usage', {}).get('total_tokens', 0),
        'finish_reason': result['choices'][0].get('finish_reason', 'stop')
    }


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


async def _call_anthropic(
    messages: List[Dict],
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: str,
    base_url: str = None
) -> Dict[str, Any]:
    """Call Anthropic Claude API"""
    try:
        import httpx
        from ....utils import guarded_httpx_client
        use_httpx = True
    except ImportError:
        import aiohttp
        use_httpx = False

    url = base_url or ANTHROPIC_API_URL

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    # Convert messages format for Anthropic
    system = None
    anthropic_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            system = msg['content']
        else:
            anthropic_messages.append(msg)

    payload = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    if system:
        payload["system"] = system

    if use_httpx:
        async with guarded_httpx_client(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            result = response.json()
    else:
        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=120, connect=30)
        async with guarded_client_session(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                result = await response.json()

    if 'error' in result:
        message = result['error'].get('message', 'Unknown error')
        return {
            'ok': False,
            'error': message,
            'outcome': _provider_refused('anthropic', message),
        }

    return {
        'ok': True,
        'response': result['content'][0]['text'],
        'tokens_used': result.get('usage', {}).get('input_tokens', 0) + result.get('usage', {}).get('output_tokens', 0),
        'finish_reason': result.get('stop_reason', 'end_turn')
    }


async def _call_ollama(
    messages: List[Dict],
    model: str,
    temperature: float,
    max_tokens: int,
    base_url: Optional[str]
) -> Dict[str, Any]:
    """Call Ollama local API"""
    try:
        import httpx
        from ....utils import guarded_httpx_client
        use_httpx = True
    except ImportError:
        import aiohttp
        use_httpx = False

    url = base_url or "http://localhost:11434"
    url = f"{url.rstrip('/')}/api/chat"

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }

    try:
        if use_httpx:
            async with guarded_httpx_client(timeout=120) as client:
                response = await client.post(url, json=payload)
                result = response.json()
        else:
            # SECURITY: Set timeout to prevent hanging API calls
            timeout = aiohttp.ClientTimeout(total=120, connect=30)
            async with guarded_client_session(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    result = await response.json()

        return {
            'ok': True,
            'response': result['message']['content'],
            'tokens_used': result.get('eval_count', 0) + result.get('prompt_eval_count', 0),
            'finish_reason': 'stop'
        }

    except Exception as e:
        # Ollama is the one provider whose transport failure is swallowed into a
        # result rather than raised, so the INDETERMINATE has to be built here.
        # `llm_chat` returns this dict verbatim and would otherwise attach the
        # FAILED it uses for a peer that answered -- which would be a claim that
        # the local model definitely did not run.
        return {
            'ok': False,
            'error': f'Ollama error: {e}',
            'outcome': _no_answer('ollama', e),
        }


def _parse_json_response(text: str) -> Optional[Any]:
    """Try to parse JSON from response"""
    import json
    import re

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None
