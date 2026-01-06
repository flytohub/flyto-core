"""
LLM Chat Module
Interact with LLM APIs for code generation, analysis, and decision making

SECURITY: Includes SSRF protection for custom base URLs.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ...registry import register_module
from ...schema import compose, presets
from ....utils import validate_url_with_env_config, SSRFError


logger = logging.getLogger(__name__)


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
    input_types=['string', 'object'],
    output_types=['string', 'object'],
    can_connect_to=['*'],
    can_receive_from=['*'],

    # Execution settings
    timeout=120,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['ai.chat'],

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
        },
        'response': {
            'type': 'string',
            'description': 'The LLM response text'
        },
        'parsed': {
            'type': 'any',
            'description': 'Parsed response (if JSON format requested)'
        },
        'model': {
            'type': 'string',
            'description': 'Model used'
        },
        'tokens_used': {
            'type': 'number',
            'description': 'Total tokens consumed'
        },
        'finish_reason': {
            'type': 'string',
            'description': 'Why the response ended'
        }
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
                'error_code': 'SSRF_BLOCKED'
            }

    # Get API key from environment if not provided
    if not api_key:
        env_vars = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'ollama': None  # Ollama doesn't need API key
        }
        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)

    if provider != 'ollama' and not api_key:
        return {
            'ok': False,
            'error': f'API key not provided for {provider}',
            'error_code': 'MISSING_API_KEY'
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
                'error_code': 'INVALID_PROVIDER'
            }

        if not result.get('ok'):
            return result

        response_text = result['response']

        # Parse response if needed
        parsed = None
        if response_format == 'json':
            parsed = _parse_json_response(response_text)

        logger.info(f"LLM chat completed: {result.get('tokens_used', 0)} tokens")

        return {
            'ok': True,
            'response': response_text,
            'parsed': parsed,
            'model': model,
            'tokens_used': result.get('tokens_used', 0),
            'finish_reason': result.get('finish_reason', 'stop')
        }

    except Exception as e:
        logger.error(f"LLM chat failed: {e}")
        return {
            'ok': False,
            'error': str(e),
            'error_code': 'API_ERROR'
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

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

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
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

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
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            result = response.json()
    else:
        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=120, connect=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                result = await response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

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
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(url, json=payload)
                result = response.json()
        else:
            # SECURITY: Set timeout to prevent hanging API calls
            timeout = aiohttp.ClientTimeout(total=120, connect=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    result = await response.json()

        return {
            'ok': True,
            'response': result['message']['content'],
            'tokens_used': result.get('eval_count', 0) + result.get('prompt_eval_count', 0),
            'finish_reason': 'stop'
        }

    except Exception as e:
        return {'ok': False, 'error': f'Ollama error: {e}'}


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
