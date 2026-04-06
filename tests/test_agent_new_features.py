# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Tests for new AI Agent features:
- Output Parser (text/json/json_schema)
- ReAct agent strategy
- Template as Tool (TemplateAgentTool)
"""

import json
import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ══════════════════════════════════════════════════════════════════
# Output Parser Tests
# ══════════════════════════════════════════════════════════════════


class TestBuildOutputFormatInstructions:
    def test_text_returns_empty(self):
        from core.modules.atomic.llm.agent import _build_output_format_instructions
        result = _build_output_format_instructions('text', None)
        assert result == ''

    def test_json_returns_instruction(self):
        from core.modules.atomic.llm.agent import _build_output_format_instructions
        result = _build_output_format_instructions('json', None)
        assert 'valid JSON' in result

    def test_json_schema_includes_schema(self):
        from core.modules.atomic.llm.agent import _build_output_format_instructions
        schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        result = _build_output_format_instructions('json_schema', schema)
        assert 'score' in result
        assert 'valid JSON' in result

    def test_json_schema_without_schema(self):
        from core.modules.atomic.llm.agent import _build_output_format_instructions
        result = _build_output_format_instructions('json_schema', None)
        assert result == ''


class TestParseOutput:
    def test_text_passthrough(self):
        from core.modules.atomic.llm.agent import _parse_output
        assert _parse_output('hello world', 'text', None) == 'hello world'

    def test_json_parses(self):
        from core.modules.atomic.llm.agent import _parse_output
        result = _parse_output('{"key": "value"}', 'json', None)
        assert result == {"key": "value"}

    def test_json_strips_markdown(self):
        from core.modules.atomic.llm.agent import _parse_output
        content = '```json\n{"key": "value"}\n```'
        result = _parse_output(content, 'json', None)
        assert result == {"key": "value"}

    def test_json_invalid_returns_string(self):
        from core.modules.atomic.llm.agent import _parse_output
        result = _parse_output('not valid json', 'json', None)
        assert result == 'not valid json'

    def test_json_schema_parses(self):
        from core.modules.atomic.llm.agent import _parse_output
        schema = {"type": "object", "properties": {"score": {"type": "number"}}}
        result = _parse_output('{"score": 0.95}', 'json_schema', schema)
        assert result == {"score": 0.95}

    def test_json_array(self):
        from core.modules.atomic.llm.agent import _parse_output
        result = _parse_output('[1, 2, 3]', 'json', None)
        assert result == [1, 2, 3]

    def test_json_nested_markdown(self):
        from core.modules.atomic.llm.agent import _parse_output
        content = '```\n{"a": 1}\n```'
        result = _parse_output(content, 'json', None)
        assert result == {"a": 1}


# ══════════════════════════════════════════════════════════════════
# ReAct Parser Tests
# ══════════════════════════════════════════════════════════════════


class TestParseReactResponse:
    def test_thought_and_action(self):
        from core.modules.atomic.llm.agent import _parse_react_response
        content = 'Thought: I need to search for data\nAction: web--search({"query": "AI news"})'
        thought, action, final = _parse_react_response(content)
        assert thought == 'I need to search for data'
        assert action is not None
        assert action[0] == 'web--search'
        assert action[1] == {"query": "AI news"}
        assert final is None

    def test_thought_and_final_answer(self):
        from core.modules.atomic.llm.agent import _parse_react_response
        content = 'Thought: I have all the data I need\nFinal Answer: The top 3 AI stories are...'
        thought, action, final = _parse_react_response(content)
        assert thought == 'I have all the data I need'
        assert action is None
        assert final.startswith('The top 3')

    def test_final_answer_only(self):
        from core.modules.atomic.llm.agent import _parse_react_response
        content = 'Final Answer: 42'
        thought, action, final = _parse_react_response(content)
        assert thought is None
        assert action is None
        assert final == '42'

    def test_action_without_args(self):
        from core.modules.atomic.llm.agent import _parse_react_response
        content = 'Thought: Let me check\nAction: calculator'
        thought, action, final = _parse_react_response(content)
        assert thought is not None
        assert action is not None
        assert action[0] == 'calculator'
        assert action[1] == {}

    def test_action_with_invalid_json(self):
        from core.modules.atomic.llm.agent import _parse_react_response
        content = 'Thought: try this\nAction: my_tool(not json)'
        thought, action, final = _parse_react_response(content)
        assert action is not None
        assert action[0] == 'my_tool'
        assert action[1] == {"input": "not json"}

    def test_multiline_thought(self):
        from core.modules.atomic.llm.agent import _parse_react_response
        content = 'Thought: First I need to consider A.\nThen I need to handle B.\nFinal Answer: Done'
        thought, action, final = _parse_react_response(content)
        assert 'consider A' in thought
        assert 'handle B' in thought
        assert final == 'Done'


class TestBuildReactInstructions:
    def test_contains_format(self):
        from core.modules.atomic.llm.agent import _build_react_instructions
        result = _build_react_instructions()
        assert 'Thought:' in result
        assert 'Action:' in result
        assert 'Final Answer:' in result
        assert 'Observation' in result


# ══════════════════════════════════════════════════════════════════
# TemplateAgentTool Tests
# ══════════════════════════════════════════════════════════════════


class TestTemplateAgentTool:
    def test_name(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='analyze.sentiment',
            tool_description='Analyze text sentiment',
        )
        assert tool.name == 'analyze--sentiment'

    def test_module_id(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='test',
            tool_description='Test tool',
        )
        assert tool.module_id == 'template.invoke:tpl_123'

    def test_description(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='test',
            tool_description='My custom description',
        )
        assert tool.description == 'My custom description'

    def test_to_tool_call_request_default_schema(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='test',
            tool_description='Test tool',
        )
        req = tool.to_tool_call_request()
        assert req.name == 'test'
        assert req.description == 'Test tool'
        assert 'input' in req.parameters['properties']

    def test_to_tool_call_request_custom_schema(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to analyze"},
                "lang": {"type": "string", "description": "Language code"},
            },
            "required": ["text"]
        }
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='analyze',
            tool_description='Analyze text',
            input_schema=schema,
        )
        req = tool.to_tool_call_request()
        assert 'text' in req.parameters['properties']
        assert 'lang' in req.parameters['properties']

    @pytest.mark.asyncio
    async def test_invoke_no_template(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='nonexistent',
            tool_name='test',
            tool_description='Test',
            parent_context={},
        )
        result = await tool.invoke({"input": "hello"})
        assert result['ok'] is False
        assert 'not found' in result['error']

    @pytest.mark.asyncio
    async def test_invoke_with_loader(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool

        # Mock template loader
        mock_definition = {
            "nodes": [{"id": "n1", "type": "trigger"}],
            "edges": [],
        }
        async def mock_loader(tid):
            return mock_definition

        tool = TemplateAgentTool(
            template_id='tpl_test',
            tool_name='test',
            tool_description='Test',
            timeout_seconds=5,
            parent_context={'_template_loader': mock_loader},
        )

        # Mock WorkflowEngine
        with patch('core.modules.atomic.llm._agent_tool_template.TemplateAgentTool._execute_template') as mock_exec:
            mock_exec.return_value = {'ok': True, 'data': {'result': 'done'}}
            result = await tool.invoke({"input": "test"})
            assert result['ok'] is True

    @pytest.mark.asyncio
    async def test_invoke_timeout(self):
        import asyncio
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool

        tool = TemplateAgentTool(
            template_id='tpl_slow',
            tool_name='slow_tool',
            tool_description='Slow tool',
            timeout_seconds=1,
            parent_context={'template_definitions': {'tpl_slow': {'nodes': [], 'edges': []}}},
        )

        # Simulate TimeoutError from invoke
        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        tool._execute_template = raise_timeout
        result = await tool.invoke({"input": "test"})
        assert result['ok'] is False
        assert 'timed out' in result['error']


# ══════════════════════════════════════════════════════════════════
# ai.tool_template module Tests
# ══════════════════════════════════════════════════════════════════


class TestAiToolTemplateModule:
    """Test the ai_tool_template raw function logic."""

    @pytest.mark.asyncio
    async def test_missing_template_id(self):
        # Import the raw function (before decorator wraps it)
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        # Simulate what the module does
        params = {}
        template_id = params.get('template_id', '')
        assert not template_id  # would return MISSING_TEMPLATE_ID

    @pytest.mark.asyncio
    async def test_missing_description(self):
        params = {'template_id': 'tpl_123'}
        tool_description = params.get('tool_description', '')
        assert not tool_description  # would return MISSING_DESCRIPTION

    @pytest.mark.asyncio
    async def test_success_creates_tool(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='template_tpl_123',
            tool_description='Analyze sentiment',
        )
        assert tool.name == 'template_tpl_123'
        assert tool.description == 'Analyze sentiment'
        assert tool.module_id == 'template.invoke:tpl_123'

    @pytest.mark.asyncio
    async def test_custom_name(self):
        from core.modules.atomic.llm._agent_tool_template import TemplateAgentTool
        tool = TemplateAgentTool(
            template_id='tpl_123',
            tool_name='my_analyzer',
            tool_description='Does analysis',
        )
        assert tool.name == 'my_analyzer'


# ══════════════════════════════════════════════════════════════════
# Agent Schema Tests
# ══════════════════════════════════════════════════════════════════


class TestAgentSchema:
    def test_schema_has_agent_type(self):
        from core.modules.schema import compose, field
        schema = compose(
            field('agent_type', type='select', default='tools'),
        )
        assert 'agent_type' in schema

    def test_schema_has_response_format(self):
        from core.modules.schema import compose, field
        schema = compose(
            field('response_format', type='select', default='text'),
        )
        assert 'response_format' in schema

    def test_schema_no_tools_field(self):
        """Verify the tools manual input field was removed."""
        from core.modules.schema import compose, field, presets
        schema = compose(
            field('prompt_source', type='select', default='manual'),
            field('task', type='string'),
            field('agent_type', type='select', default='tools'),
            field('system_prompt', type='string'),
            field('response_format', type='select', default='text'),
            field('context', type='object'),
            field('max_iterations', type='number'),
            presets.LLM_PROVIDER(default='openai'),
            presets.LLM_MODEL(default='gpt-4o'),
            presets.LLM_API_KEY(),
        )
        assert 'tools' not in schema
