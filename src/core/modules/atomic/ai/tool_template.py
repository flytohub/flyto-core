# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Tool Template Sub-Node
Wraps a flyto template (workflow) as an AI Agent tool.

The agent can invoke any user template during execution,
similar to n8n's "Workflow Tool" but using flyto's template system.
"""

from typing import Any, Dict
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.tool_template',
    stability="stable",
    version='1.0.0',
    category='ai',
    subcategory='sub_node',
    tags=['ai', 'tool', 'agent', 'sub-node', 'template', 'workflow'],
    label='Template Tool',
    label_key='modules.ai.tool_template.label',
    description='Use a template (workflow) as an AI Agent tool',
    description_key='modules.ai.tool_template.description',
    icon='Package',
    color='#F59E0B',

    node_type=NodeType.AI_SUB_NODE,

    input_types=[],
    output_types=['ai_tool'],

    can_receive_from=[],
    can_connect_to=['llm.agent'],

    input_ports=[],

    output_ports=[
        {
            'id': 'tool',
            'label': 'Tool',
            'label_key': 'modules.ai.tool_template.ports.tool',
            'data_type': DataType.AI_TOOL.value,
            'edge_type': EdgeType.RESOURCE.value,
            'color': '#F59E0B'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema=compose(
        field(
            'template_id',
            type='string',
            label='Template',
            label_key='modules.ai.tool_template.params.template_id',
            description='Template to expose as an agent tool',
            description_key='modules.ai.tool_template.params.template_id.description',
            required=True,
            placeholder='Select a template...',
            ui={'component': 'template_selector'},
        ),
        field(
            'tool_name',
            type='string',
            label='Tool Name',
            label_key='modules.ai.tool_template.params.tool_name',
            description='Name the agent sees (defaults to template name)',
            description_key='modules.ai.tool_template.params.tool_name.description',
            required=False,
            placeholder='e.g. analyze_sentiment',
        ),
        field(
            'tool_description',
            type='string',
            label='Description',
            label_key='modules.ai.tool_template.params.tool_description',
            description='What this tool does (helps the agent decide when to use it)',
            description_key='modules.ai.tool_template.params.tool_description.description',
            required=True,
            format='multiline',
            placeholder='Analyzes text sentiment and returns positive/negative/neutral score',
        ),
        field(
            'input_schema',
            type='object',
            label='Input Schema',
            label_key='modules.ai.tool_template.params.input_schema',
            description='JSON Schema for tool input (what the agent passes in)',
            description_key='modules.ai.tool_template.params.input_schema.description',
            required=False,
            default={},
            ui={'component': 'json_editor'},
        ),
        field(
            'timeout_seconds',
            type='number',
            label='Timeout (seconds)',
            label_key='modules.ai.tool_template.params.timeout_seconds',
            description='Maximum execution time',
            description_key='modules.ai.tool_template.params.timeout_seconds.description',
            required=False,
            default=120,
            min=5,
            max=600,
        ),
    ),

    output_schema={
        'template_id': {
            'type': 'string',
            'description': 'Template ID exposed as tool',
        },
    },

    examples=[
        {
            'title': 'Sentiment Analysis Workflow',
            'params': {
                'template_id': 'tpl_sentiment_123',
                'tool_name': 'analyze_sentiment',
                'tool_description': 'Analyzes text sentiment, returns {score, label}',
            }
        },
        {
            'title': 'Data Enrichment Workflow',
            'params': {
                'template_id': 'tpl_enrich_456',
                'tool_name': 'enrich_company',
                'tool_description': 'Takes a company name and returns enriched data (industry, size, revenue)',
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
async def ai_tool_template(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide a template as a tool for AI Agent.

    This module creates a TemplateAgentTool that the agent can invoke.
    When called, it executes the template with the agent's arguments as input.
    """
    params = context['params']
    template_id = params.get('template_id', '')
    tool_name = params.get('tool_name', '')
    tool_description = params.get('tool_description', '')
    input_schema = params.get('input_schema', {})
    timeout_seconds = params.get('timeout_seconds', 120)

    if not template_id:
        return {
            'ok': False,
            'error': 'template_id is required',
            'error_code': 'MISSING_TEMPLATE_ID'
        }

    if not tool_description:
        return {
            'ok': False,
            'error': 'tool_description is required (helps the agent know when to use this tool)',
            'error_code': 'MISSING_DESCRIPTION'
        }

    from ..llm._agent_tool_template import TemplateAgentTool
    tool_obj = TemplateAgentTool(
        template_id=template_id,
        tool_name=tool_name or f'template_{template_id[:8]}',
        tool_description=tool_description,
        input_schema=input_schema,
        timeout_seconds=timeout_seconds,
        parent_context=context,
    )

    return {
        'ok': True,
        '__data_type__': 'ai_tool',
        'module_id': f'template.invoke:{template_id}',
        'tool': tool_obj,
        'description': tool_description,
    }
