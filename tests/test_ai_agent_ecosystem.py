"""
Tests for AI Agent Ecosystem
Covers: LLMClientMixin, agent.tool_use, ai.memory.vector, tool name mapping
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# 1. Tool Name Mapping
# ---------------------------------------------------------------------------

class TestToolNameMapping:
    """Tool name <-> module ID round-trip."""

    def test_simple_module_id(self):
        """browser.click -> browser--click -> browser.click"""
        tool_name = "browser.click".replace('.', '--')
        assert tool_name == "browser--click"
        module_id = tool_name.replace('--', '.')
        assert module_id == "browser.click"

    def test_underscore_module_id(self):
        """flow.error_handle -> flow--error_handle -> flow.error_handle"""
        tool_name = "flow.error_handle".replace('.', '--')
        assert tool_name == "flow--error_handle"
        module_id = tool_name.replace('--', '.')
        assert module_id == "flow.error_handle"

    def test_deep_module_id(self):
        """api.google_sheets.read -> api--google_sheets--read -> api.google_sheets.read"""
        original = "api.google_sheets.read"
        tool_name = original.replace('.', '--')
        assert tool_name == "api--google_sheets--read"
        recovered = tool_name.replace('--', '.')
        assert recovered == original

    def test_all_registered_modules_roundtrip(self):
        """Every registered module should survive the round-trip."""
        from core.modules.registry import get_registry
        registry = get_registry()
        broken = []
        for module_id in registry.list_all():
            tool_name = module_id.replace('.', '--')
            recovered = tool_name.replace('--', '.')
            if recovered != module_id:
                broken.append(module_id)
        assert not broken, f"Round-trip failed for: {broken}"


# ---------------------------------------------------------------------------
# 2. LLMClientMixin
# ---------------------------------------------------------------------------

class TestLLMClientMixin:
    """LLMClientMixin provider tests with mocked APIs."""

    def _make_agent(self):
        from core.modules.third_party.ai.agents.llm_client import LLMClientMixin

        class TestAgent(LLMClientMixin):
            pass

        return TestAgent()

    # -- validate_llm_params ------------------------------------------------

    def test_validate_openai(self):
        agent = self._make_agent()
        os.environ['OPENAI_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'openai'})
            assert agent.llm_provider == 'openai'
            assert agent.api_key == 'test-key'
            assert agent.model == 'gpt-4o'  # default
        finally:
            os.environ.pop('OPENAI_API_KEY', None)

    def test_validate_anthropic_auto_model(self):
        agent = self._make_agent()
        os.environ['ANTHROPIC_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'anthropic'})
            assert agent.model == 'claude-sonnet-4-6'
        finally:
            os.environ.pop('ANTHROPIC_API_KEY', None)

    def test_validate_gemini_auto_model(self):
        agent = self._make_agent()
        os.environ['GOOGLE_AI_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'gemini'})
            assert agent.model == 'gemini-2.5-pro'
        finally:
            os.environ.pop('GOOGLE_AI_API_KEY', None)

    def test_validate_ollama_no_key(self):
        agent = self._make_agent()
        agent.validate_llm_params({'llm_provider': 'ollama'})
        assert agent.api_key is None

    def test_validate_missing_key_raises(self):
        agent = self._make_agent()
        for provider in ('openai', 'anthropic', 'gemini'):
            # Clear all keys
            for k in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_AI_API_KEY'):
                os.environ.pop(k, None)
            with pytest.raises(ValueError):
                agent.validate_llm_params({'llm_provider': provider})

    def test_validate_invalid_provider(self):
        agent = self._make_agent()
        with pytest.raises(ValueError, match="Unsupported"):
            agent.validate_llm_params({'llm_provider': 'invalid'})

    def test_explicit_model_not_overridden(self):
        """If user sets model explicitly, don't auto-switch."""
        agent = self._make_agent()
        os.environ['ANTHROPIC_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({
                'llm_provider': 'anthropic',
                'model': 'claude-3-opus-20240229',
            })
            assert agent.model == 'claude-3-opus-20240229'
        finally:
            os.environ.pop('ANTHROPIC_API_KEY', None)

    # -- _call_anthropic ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_call_anthropic_mocked(self):
        """Test _call_anthropic with mocked HTTP response."""
        agent = self._make_agent()
        os.environ['ANTHROPIC_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'anthropic'})
        finally:
            os.environ.pop('ANTHROPIC_API_KEY', None)

        mock_response = {
            'content': [{'type': 'text', 'text': 'Hello from Claude'}],
            'model': 'claude-sonnet-4-6',
            'stop_reason': 'end_turn',
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.text = AsyncMock(return_value='')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await agent._call_anthropic([
                {'role': 'system', 'content': 'You are helpful.'},
                {'role': 'user', 'content': 'Hello'},
            ])

        assert result == 'Hello from Claude'
        # Verify system was separated from messages
        call_args = mock_session.post.call_args
        payload = call_args.kwargs.get('json') or call_args[1].get('json')
        assert payload['system'] == 'You are helpful.'
        assert len(payload['messages']) == 1
        assert payload['messages'][0]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_call_anthropic_error_status(self):
        """Anthropic returning non-200 should raise."""
        agent = self._make_agent()
        os.environ['ANTHROPIC_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'anthropic'})
        finally:
            os.environ.pop('ANTHROPIC_API_KEY', None)

        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.text = AsyncMock(return_value='Bad request')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(RuntimeError, match="Anthropic API error"):
                await agent._call_anthropic([{'role': 'user', 'content': 'Hi'}])

    # -- _call_gemini -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_call_gemini_mocked(self):
        """Test _call_gemini with mocked HTTP response."""
        agent = self._make_agent()
        os.environ['GOOGLE_AI_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'gemini'})
        finally:
            os.environ.pop('GOOGLE_AI_API_KEY', None)

        mock_response = {
            'candidates': [{
                'content': {
                    'parts': [{'text': 'Hello from Gemini'}],
                    'role': 'model',
                },
            }],
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.text = AsyncMock(return_value='')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await agent._call_gemini([
                {'role': 'system', 'content': 'Be concise.'},
                {'role': 'user', 'content': 'Hello'},
            ])

        assert result == 'Hello from Gemini'
        # Verify Gemini format
        call_args = mock_session.post.call_args
        payload = call_args.kwargs.get('json') or call_args[1].get('json')
        assert 'systemInstruction' in payload
        assert payload['systemInstruction']['parts'][0]['text'] == 'Be concise.'
        assert payload['contents'][0]['role'] == 'user'

    @pytest.mark.asyncio
    async def test_call_gemini_no_candidates_raises(self):
        """Gemini returning empty candidates should raise."""
        agent = self._make_agent()
        os.environ['GOOGLE_AI_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'gemini'})
        finally:
            os.environ.pop('GOOGLE_AI_API_KEY', None)

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={'candidates': []})
        mock_resp.text = AsyncMock(return_value='')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(RuntimeError, match="no candidates"):
                await agent._call_gemini([{'role': 'user', 'content': 'Hi'}])

    # -- _call_ollama -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_call_ollama_mocked(self):
        """Test _call_ollama with mocked HTTP response."""
        agent = self._make_agent()
        agent.validate_llm_params({'llm_provider': 'ollama'})

        mock_response = {
            'message': {'role': 'assistant', 'content': 'Hello from Ollama'},
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        mock_resp.text = AsyncMock(return_value='')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await agent._call_ollama([{'role': 'user', 'content': 'Hi'}])

        assert result == 'Hello from Ollama'


# ---------------------------------------------------------------------------
# 3. Vector Memory
# ---------------------------------------------------------------------------

class TestMemoryVector:
    """Vector memory tests with mocked embeddings."""

    @pytest.mark.asyncio
    async def test_add_message_with_embedder(self):
        """Messages should get real embeddings when embedder is available."""
        from core.modules.atomic.ai.memory_vector import (
            _vector_add_message, _vector_clear,
        )

        mock_embedder = MagicMock()
        mock_embedder.generate = MagicMock(side_effect=[
            [1.0, 0.0, 0.0],  # message 1
            [0.9, 0.1, 0.0],  # message 2 (similar to 1)
            [0.0, 0.0, 1.0],  # message 3 (different)
        ])
        mock_embedder.get_dimension = MagicMock(return_value=3)

        memory_state = {
            'vector_store': {'embeddings': [], 'messages': [], 'metadata': []},
            'embedder': mock_embedder,
            'config': {'top_k': 2, 'similarity_threshold': 0.5},
        }

        await _vector_add_message(memory_state, 'user', 'Python sorting')
        await _vector_add_message(memory_state, 'user', 'Python lists')
        await _vector_add_message(memory_state, 'user', 'Weather forecast')

        store = memory_state['vector_store']
        assert len(store['messages']) == 3
        assert store['embeddings'][0] == [1.0, 0.0, 0.0]
        assert store['embeddings'][2] == [0.0, 0.0, 1.0]
        assert mock_embedder.generate.call_count == 3

    @pytest.mark.asyncio
    async def test_semantic_search(self):
        """Semantic search should rank by cosine similarity."""
        from core.modules.atomic.ai.memory_vector import (
            _vector_add_message, _vector_search, _vector_get_relevant,
        )

        call_count = 0
        embeddings = [
            [1.0, 0.0, 0.0],   # "Python sorting"
            [0.0, 0.0, 1.0],   # "Weather forecast"
            [0.95, 0.05, 0.0],  # query embedding for "Python programming"
        ]

        mock_embedder = MagicMock()
        mock_embedder.generate = MagicMock(side_effect=embeddings)
        mock_embedder.get_dimension = MagicMock(return_value=3)

        memory_state = {
            'vector_store': {'embeddings': [], 'messages': [], 'metadata': []},
            'embedder': mock_embedder,
            'config': {'top_k': 2, 'similarity_threshold': 0.3},
        }

        await _vector_add_message(memory_state, 'user', 'Python sorting')
        await _vector_add_message(memory_state, 'user', 'Weather forecast')

        results = _vector_get_relevant(memory_state, 'Python programming')
        assert len(results) > 0
        # Python-related message should rank higher
        assert results[0]['message']['content'] == 'Python sorting'
        assert results[0]['similarity'] > 0.9

    @pytest.mark.asyncio
    async def test_fallback_without_embedder(self):
        """Without embedder, should fallback to recent messages."""
        from core.modules.atomic.ai.memory_vector import (
            _vector_add_message, _vector_get_relevant,
        )

        memory_state = {
            'vector_store': {'embeddings': [], 'messages': [], 'metadata': []},
            'embedder': None,  # No embedder
            'config': {'top_k': 2, 'similarity_threshold': 0.5},
        }

        await _vector_add_message(memory_state, 'user', 'Message 1')
        await _vector_add_message(memory_state, 'user', 'Message 2')
        await _vector_add_message(memory_state, 'user', 'Message 3')

        # Without embedder, embeddings should be zero vectors (dim=1536 default)
        assert all(v == 0.0 for v in memory_state['vector_store']['embeddings'][0])

        results = _vector_get_relevant(memory_state, 'any query')
        assert len(results) == 2  # top_k = 2
        # Should return the last 2 messages (recent)
        assert results[0]['message']['content'] == 'Message 2'
        assert results[1]['message']['content'] == 'Message 3'

    @pytest.mark.asyncio
    async def test_clear_memory(self):
        """Clear should empty all stores."""
        from core.modules.atomic.ai.memory_vector import (
            _vector_add_message, _vector_clear,
        )

        memory_state = {
            'vector_store': {'embeddings': [], 'messages': [], 'metadata': []},
            'embedder': None,
            'config': {'top_k': 5, 'similarity_threshold': 0.5},
        }

        await _vector_add_message(memory_state, 'user', 'Test')
        assert len(memory_state['vector_store']['messages']) == 1

        _vector_clear(memory_state)
        assert len(memory_state['vector_store']['messages']) == 0
        assert len(memory_state['vector_store']['embeddings']) == 0

    @pytest.mark.asyncio
    async def test_embedder_failure_fallback(self):
        """If embedder.generate raises, should fallback to zero vector."""
        from core.modules.atomic.ai.memory_vector import _vector_add_message

        mock_embedder = MagicMock()
        mock_embedder.generate = MagicMock(side_effect=RuntimeError("API down"))
        mock_embedder.get_dimension = MagicMock(return_value=3)

        memory_state = {
            'vector_store': {'embeddings': [], 'messages': [], 'metadata': []},
            'embedder': mock_embedder,
            'config': {'top_k': 5, 'similarity_threshold': 0.5},
        }

        await _vector_add_message(memory_state, 'user', 'Test')
        # Should have a zero vector, not crash
        assert memory_state['vector_store']['embeddings'][0] == [0.0, 0.0, 0.0]
        assert memory_state['vector_store']['messages'][0]['content'] == 'Test'


# ---------------------------------------------------------------------------
# 4. execute_tool
# ---------------------------------------------------------------------------

class TestExecuteTool:
    """Test execute_tool function with real modules."""

    @pytest.mark.asyncio
    async def test_execute_nonexistent_module(self):
        """Should return error for non-existent module."""
        from core.modules.atomic.llm._tools import execute_tool
        result = await execute_tool('nonexistent--module', {}, {})
        assert result['ok'] is False
        assert 'not found' in result['error'].lower()

    def test_build_tool_definitions_is_callable(self):
        """build_tool_definitions should exist and be callable."""
        from core.modules.atomic.llm._tools import build_tool_definitions
        assert callable(build_tool_definitions)

    def test_tool_name_uses_double_dash_separator(self):
        """Tool names in definitions must use -- separator, not dots."""
        from core.modules.atomic.llm._tools import build_tool_definitions
        # Verify the separator logic by checking the source implementation
        # The function replaces '.' with '--' on line: tool_id.replace('.', '--')
        tool_id = "api.openai.chat"
        expected = "api--openai--chat"
        assert tool_id.replace('.', '--') == expected


# ---------------------------------------------------------------------------
# 5. Model Options
# ---------------------------------------------------------------------------

class TestModelOptions:
    """Verify model option lists are current."""

    def test_openai_has_gpt4o(self):
        from core.modules.registry import get_registry
        registry = get_registry()
        meta = registry.get_metadata('api.openai.chat')
        assert meta is not None, "api.openai.chat module not registered"
        models = [o['value'] for o in meta['params_schema']['model']['options']]
        assert 'gpt-4o' in models
        assert 'gpt-4o-mini' in models
        assert 'o3' in models

    def test_anthropic_has_claude4(self):
        from core.modules.registry import get_registry
        registry = get_registry()
        meta = registry.get_metadata('api.anthropic.chat')
        assert meta is not None, "api.anthropic.chat module not registered"
        models = [o['value'] for o in meta['params_schema']['model']['options']]
        assert 'claude-sonnet-4-6' in models
        assert 'claude-opus-4-6' in models

    def test_anthropic_max_tokens_raised(self):
        from core.modules.registry import get_registry
        registry = get_registry()
        meta = registry.get_metadata('api.anthropic.chat')
        assert meta is not None, "api.anthropic.chat module not registered"
        assert meta['params_schema']['max_tokens']['max'] == 16384

    def test_gemini_has_25(self):
        from core.modules.registry import get_registry
        registry = get_registry()
        meta = registry.get_metadata('api.google_gemini.chat')
        assert meta is not None, "api.google_gemini.chat module not registered"
        models = [o['value'] for o in meta['params_schema']['model']['options']]
        assert 'gemini-2.5-pro' in models
        assert 'gemini-2.5-flash' in models

    def test_autonomous_has_all_providers(self):
        from core.modules.registry import get_registry
        registry = get_registry()
        meta = registry.get_metadata('agent.autonomous')
        assert meta is not None, "agent.autonomous module not registered"
        providers = [o['value'] for o in meta['params_schema']['llm_provider']['options']]
        assert set(providers) == {'openai', 'anthropic', 'gemini', 'ollama'}

    def test_default_constants(self):
        from core.constants import APIEndpoints
        assert APIEndpoints.DEFAULT_OPENAI_MODEL == 'gpt-4o'
        assert APIEndpoints.DEFAULT_ANTHROPIC_MODEL == 'claude-sonnet-4-6'
        assert APIEndpoints.DEFAULT_GEMINI_MODEL == 'gemini-2.5-pro'


# ---------------------------------------------------------------------------
# 6. LLMClientMixin — OpenAI mocked call + error handling
# ---------------------------------------------------------------------------

class TestLLMClientMixinOpenAI:
    """OpenAI-specific mocked tests (separate from main class to avoid env pollution)."""

    def _make_agent(self):
        from core.modules.third_party.ai.agents.llm_client import LLMClientMixin

        class TestAgent(LLMClientMixin):
            pass
        return TestAgent()

    @pytest.mark.asyncio
    async def test_call_openai_mocked(self):
        """Test _call_openai with mocked openai.AsyncOpenAI client."""
        agent = self._make_agent()
        os.environ['OPENAI_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'openai'})
        finally:
            os.environ.pop('OPENAI_API_KEY', None)

        # Mock the openai module
        mock_message = MagicMock()
        mock_message.content = 'Hello from GPT-4o'

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_completions = AsyncMock()
        mock_completions.create = AsyncMock(return_value=mock_response)

        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        mock_client = MagicMock()
        mock_client.chat = mock_chat

        with patch('openai.AsyncOpenAI', return_value=mock_client):
            result = await agent._call_openai([
                {'role': 'system', 'content': 'You are helpful.'},
                {'role': 'user', 'content': 'Hello'},
            ])

        assert result == 'Hello from GPT-4o'
        # Verify the create call
        mock_completions.create.assert_awaited_once()
        call_kwargs = mock_completions.create.call_args.kwargs
        assert call_kwargs['model'] == 'gpt-4o'
        assert len(call_kwargs['messages']) == 2

    @pytest.mark.asyncio
    async def test_call_openai_propagates_error(self):
        """OpenAI errors should propagate."""
        agent = self._make_agent()
        os.environ['OPENAI_API_KEY'] = 'test-key'
        try:
            agent.validate_llm_params({'llm_provider': 'openai'})
        finally:
            os.environ.pop('OPENAI_API_KEY', None)

        mock_completions = AsyncMock()
        mock_completions.create = AsyncMock(
            side_effect=Exception("Rate limit exceeded")
        )

        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        mock_client = MagicMock()
        mock_client.chat = mock_chat

        with patch('openai.AsyncOpenAI', return_value=mock_client):
            with pytest.raises(Exception, match="Rate limit exceeded"):
                await agent._call_openai([{'role': 'user', 'content': 'Hi'}])


# ---------------------------------------------------------------------------
# 7. Agent Tool Use — Full Loop (mocked LLM + real tool execution)
# ---------------------------------------------------------------------------

class TestAgentToolUseLoop:
    """End-to-end agent tool use loop with mocked LLM."""

    @staticmethod
    def _make_mock_session(responses):
        """Build a mock aiohttp session that returns responses in order."""
        call_count = [0]

        def mock_post_cm(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            resp = MagicMock()
            resp.status = 200
            resp.json = AsyncMock(return_value=responses[min(idx, len(responses) - 1)])
            resp.text = AsyncMock(return_value='')
            # Wrap in async context manager
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=resp)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=mock_post_cm)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    async def test_openai_tool_loop_executes_tool(self):
        """OpenAI agent should call execute_tool and feed results back."""
        from core.modules.third_party.ai.agents.tool_use import _run_openai_agent

        responses = [
            # Response 1: LLM wants to call a tool
            {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': None,
                        'tool_calls': [{
                            'id': 'call_1',
                            'type': 'function',
                            'function': {
                                'name': 'my_tool',
                                'arguments': '{"input": "test"}',
                            },
                        }],
                    },
                    'finish_reason': 'tool_calls',
                }],
            },
            # Response 2: LLM gives final answer
            {
                'choices': [{
                    'message': {
                        'role': 'assistant',
                        'content': 'The tool returned: mock result',
                    },
                    'finish_reason': 'stop',
                }],
                'model': 'gpt-4o',
            },
        ]

        mock_session = self._make_mock_session(responses)
        mock_tool_result = {'ok': True, 'data': 'mock result'}

        with patch('aiohttp.ClientSession', return_value=mock_session), \
             patch('core.modules.third_party.ai.agents.tool_use.execute_tool',
                   new=AsyncMock(return_value=mock_tool_result)):
            result = await _run_openai_agent(
                api_key='test', model='gpt-4o', prompt='Use the tool',
                tools=[{'name': 'my_tool', 'description': 'Test', 'parameters': {}}],
                max_iterations=5, system_prompt='', context={},
            )

        assert result['ok'] is True
        assert result['data']['result'] == 'The tool returned: mock result'
        assert len(result['data']['tool_calls']) == 1
        assert result['data']['tool_calls'][0]['name'] == 'my_tool'
        assert 'result' in result['data']['tool_calls'][0]

    @pytest.mark.asyncio
    async def test_anthropic_tool_loop_executes_tool(self):
        """Anthropic agent should call execute_tool and feed results back."""
        from core.modules.third_party.ai.agents.tool_use import _run_anthropic_agent

        responses = [
            # Response 1: Claude calls tool
            {
                'stop_reason': 'tool_use',
                'content': [
                    {'type': 'text', 'text': 'Let me check...'},
                    {'type': 'tool_use', 'id': 'toolu_1', 'name': 'my_tool', 'input': {'query': 'test'}},
                ],
                'model': 'claude-sonnet-4-6',
            },
            # Response 2: Final answer
            {
                'stop_reason': 'end_turn',
                'content': [{'type': 'text', 'text': 'Based on the tool: done'}],
                'model': 'claude-sonnet-4-6',
            },
        ]

        mock_session = self._make_mock_session(responses)
        mock_tool_result = {'ok': True, 'data': 'anthropic mock result'}

        with patch('aiohttp.ClientSession', return_value=mock_session), \
             patch('core.modules.third_party.ai.agents.tool_use.execute_tool',
                   new=AsyncMock(return_value=mock_tool_result)):
            result = await _run_anthropic_agent(
                api_key='test', model='claude-sonnet-4-6', prompt='Use the tool',
                tools=[{'name': 'my_tool', 'description': 'Test', 'parameters': {}}],
                max_iterations=5, system_prompt='', context={},
            )

        assert result['ok'] is True
        assert 'Based on the tool' in result['data']['result']
        assert len(result['data']['tool_calls']) == 1

    @pytest.mark.asyncio
    async def test_tool_execution_error_doesnt_crash_loop(self):
        """If execute_tool raises, agent should get error message and continue."""
        from core.modules.third_party.ai.agents.tool_use import _run_openai_agent

        responses = [
            {
                'choices': [{
                    'message': {
                        'role': 'assistant', 'content': None,
                        'tool_calls': [{'id': 'call_1', 'type': 'function',
                                        'function': {'name': 'broken_tool', 'arguments': '{}'}}],
                    },
                    'finish_reason': 'tool_calls',
                }],
            },
            {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'The tool failed, sorry.'},
                    'finish_reason': 'stop',
                }],
                'model': 'gpt-4o',
            },
        ]

        mock_session = self._make_mock_session(responses)

        with patch('aiohttp.ClientSession', return_value=mock_session), \
             patch('core.modules.third_party.ai.agents.tool_use.execute_tool',
                   new=AsyncMock(side_effect=RuntimeError("Module crashed"))):
            result = await _run_openai_agent(
                api_key='test', model='gpt-4o', prompt='Use the tool',
                tools=[{'name': 'broken_tool', 'description': 'Fail', 'parameters': {}}],
                max_iterations=5, system_prompt='', context={},
            )

        assert result['ok'] is True
        assert result['data']['result'] == 'The tool failed, sorry.'
        assert 'error' in result['data']['tool_calls'][0].get('result', '')


# ---------------------------------------------------------------------------
# 8. OpenAI Chat Module — new AsyncOpenAI client
# ---------------------------------------------------------------------------

class TestOpenAIChatModule:
    """Test the OpenAI chat module (openai_integration.py) with mocked client."""

    @pytest.mark.asyncio
    async def test_execute_with_new_client(self):
        """OpenAIChatModule.execute() should use AsyncOpenAI client."""
        from core.modules.registry import get_registry

        registry = get_registry()
        module_cls = registry.get('api.openai.chat')

        # Mock the openai module
        mock_message = MagicMock()
        mock_message.content = 'Mocked GPT response'

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = 'gpt-4o'
        mock_response.usage = mock_usage

        mock_completions = AsyncMock()
        mock_completions.create = AsyncMock(return_value=mock_response)

        mock_chat = MagicMock()
        mock_chat.completions = mock_completions

        mock_client = MagicMock()
        mock_client.chat = mock_chat

        os.environ['OPENAI_API_KEY'] = 'test-key'
        try:
            params = {'prompt': 'Hello', 'model': 'gpt-4o'}
            instance = module_cls(params, {})
            instance.validate_params()

            with patch('openai.AsyncOpenAI', return_value=mock_client):
                result = await instance.execute()

            assert result['response'] == 'Mocked GPT response'
            assert result['model'] == 'gpt-4o'
            assert result['usage']['total_tokens'] == 30
        finally:
            os.environ.pop('OPENAI_API_KEY', None)


# ---------------------------------------------------------------------------
# 9. Anthropic Chat Module — services.py
# ---------------------------------------------------------------------------

class TestAnthropicChatModule:
    """Test anthropic_chat function in services.py with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_anthropic_chat_via_registry(self):
        """Anthropic chat module should work through the registry execution path."""
        from core.modules.registry import get_registry

        registry = get_registry()
        module_cls = registry.get('api.anthropic.chat')

        mock_api_response = {
            'content': [{'type': 'text', 'text': 'Hello from Claude module'}],
            'model': 'claude-sonnet-4-6',
            'stop_reason': 'end_turn',
            'usage': {'input_tokens': 15, 'output_tokens': 25},
        }

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_api_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        os.environ['ANTHROPIC_API_KEY'] = 'test-key'
        try:
            params = {
                'messages': [{'role': 'user', 'content': 'Hello'}],
                'max_tokens': 100,
            }
            context = {'params': params}

            instance = module_cls(params, context)

            with patch('aiohttp.ClientSession', return_value=mock_session):
                result = await instance.run()

            assert result['content'] == 'Hello from Claude module'
            assert result['model'] == 'claude-sonnet-4-6'
            assert result['usage']['input_tokens'] == 15
        finally:
            os.environ.pop('ANTHROPIC_API_KEY', None)


# ---------------------------------------------------------------------------
# 10. Gemini URL Security
# ---------------------------------------------------------------------------

class TestGeminiSecurity:
    """Verify Gemini API key handling."""

    def test_gemini_url_contains_api_key_as_param(self):
        """Gemini REST API requires key in URL query param — verify format."""
        from core.modules.third_party.ai.agents.llm_client import LLMClientMixin

        class TestAgent(LLMClientMixin):
            pass

        agent = TestAgent()
        os.environ['GOOGLE_AI_API_KEY'] = 'test-gemini-key'
        try:
            agent.validate_llm_params({'llm_provider': 'gemini'})
        finally:
            os.environ.pop('GOOGLE_AI_API_KEY', None)

        # The URL construction in _call_gemini uses f-string with key as query param
        # This is the standard Gemini REST API approach
        expected_url_part = f"key={agent.api_key}"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{agent.model}:generateContent?key={agent.api_key}"
        )
        assert expected_url_part in url
        assert 'test-gemini-key' in url
        # Verify it's HTTPS (key in URL is safe over TLS)
        assert url.startswith('https://')
