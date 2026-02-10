"""
LLM provider API call implementations for Agent module.

Supports:
- OpenAI (with httpx or aiohttp fallback)
- Anthropic (with httpx or aiohttp fallback)
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def call_openai_with_tools(
    messages: List[Dict],
    tools: List[Dict],
    model: str,
    temperature: float,
    api_key: str,
    base_url: Optional[str]
) -> Dict[str, Any]:
    """Call OpenAI API with tool support."""
    try:
        import httpx
    except ImportError:
        return await _call_openai_aiohttp(messages, tools, model, temperature, api_key, base_url)

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
        "max_tokens": 4096
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, headers=headers, json=payload)
        result = response.json()

    return _parse_openai_response(result)


async def _call_openai_aiohttp(
    messages: List[Dict],
    tools: List[Dict],
    model: str,
    temperature: float,
    api_key: str,
    base_url: Optional[str]
) -> Dict[str, Any]:
    """Call OpenAI API using aiohttp fallback."""
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
        "max_tokens": 4096
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as response:
            result = await response.json()

    return _parse_openai_response(result)


def _parse_openai_response(result: Dict) -> Dict[str, Any]:
    """Parse OpenAI API response into standardized format."""
    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

    choice = result['choices'][0]
    message = choice['message']

    if message.get('tool_calls'):
        tool_calls = []
        for tc in message['tool_calls']:
            tool_calls.append({
                'id': tc['id'],
                'name': tc['function']['name'],
                'arguments': json.loads(tc['function']['arguments'])
            })
        return {
            'ok': True,
            'tool_calls': tool_calls,
            'tokens_used': result.get('usage', {}).get('total_tokens', 0)
        }

    return {
        'ok': True,
        'response': message.get('content', ''),
        'tokens_used': result.get('usage', {}).get('total_tokens', 0),
        'finish_reason': choice.get('finish_reason', 'stop')
    }


async def call_anthropic_with_tools(
    messages: List[Dict],
    tools: List[Dict],
    model: str,
    temperature: float,
    api_key: str
) -> Dict[str, Any]:
    """Call Anthropic API with tool support."""
    try:
        import httpx
        use_httpx = True
    except ImportError:
        import aiohttp
        use_httpx = False

    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }

    # Convert messages for Anthropic format
    system = None
    anthropic_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            system = msg['content']
        elif msg['role'] == 'tool':
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get('tool_call_id', 'unknown'),
                    "content": msg['content']
                }]
            })
        elif msg.get('tool_calls'):
            content = []
            for tc in msg['tool_calls']:
                content.append({
                    "type": "tool_use",
                    "id": tc.get('id', tc['name']),
                    "name": tc['name'],
                    "input": tc['arguments']
                })
            anthropic_messages.append({"role": "assistant", "content": content})
        else:
            anthropic_messages.append(msg)

    # Convert tools to Anthropic format
    anthropic_tools = []
    for tool in tools:
        func = tool['function']
        anthropic_tools.append({
            "name": func['name'],
            "description": func['description'],
            "input_schema": func['parameters']
        })

    payload = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": 4096,
        "temperature": temperature
    }

    if system:
        payload["system"] = system
    if anthropic_tools:
        payload["tools"] = anthropic_tools

    if use_httpx:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
            result = response.json()
    else:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                result = await response.json()

    if 'error' in result:
        return {'ok': False, 'error': result['error'].get('message', 'Unknown error')}

    tool_calls = []
    text_content = ""

    for block in result.get('content', []):
        if block['type'] == 'tool_use':
            tool_calls.append({
                'id': block['id'],
                'name': block['name'],
                'arguments': block['input']
            })
        elif block['type'] == 'text':
            text_content += block['text']

    tokens_used = result.get('usage', {}).get('input_tokens', 0) + result.get('usage', {}).get('output_tokens', 0)

    if tool_calls:
        return {
            'ok': True,
            'tool_calls': tool_calls,
            'tokens_used': tokens_used
        }

    return {
        'ok': True,
        'response': text_content,
        'tokens_used': tokens_used,
        'finish_reason': result.get('stop_reason', 'end_turn')
    }
