# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
AI Tool Sub-Node
Wraps a flyto-core module as an AI Agent tool (n8n-style)

This is a "sub-node" that connects to AI Agent via RESOURCE edge.
It tells the agent which module to use as a tool.
"""

from typing import Any, Dict
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.tool',
    stability="stable",
    version='1.0.0',
    category='ai',
    subcategory='sub_node',
    tags=['ai', 'tool', 'agent', 'sub-node'],
    label='AI Tool',
    label_key='modules.ai.tool.label',
    description='Expose a module as a tool for AI Agent',
    description_key='modules.ai.tool.description',
    icon='Wrench',
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
            'label_key': 'modules.ai.tool.ports.tool',
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
            'module_id',
            type='string',
            label='Module',
            label_key='modules.ai.tool.params.module_id',
            description='Module ID to expose as tool (e.g. http.request, data.json_parse)',
            description_key='modules.ai.tool.params.module_id.description',
            required=True,
            placeholder='http.request',
            ui={'component': 'module_selector'},
        ),
        field(
            'tool_description',
            type='string',
            label='Description',
            label_key='modules.ai.tool.params.tool_description',
            description='Custom description for the agent (overrides module default)',
            description_key='modules.ai.tool.params.tool_description.description',
            required=False,
            format='multiline',
            placeholder='Leave empty to use module default description',
        ),
    ),

    output_schema={
        'module_id': {
            'type': 'string',
            'description': 'Module ID exposed as tool',
            'description_key': 'modules.ai.tool.output.module_id.description',
        },
    },

    examples=[
        {
            'title': 'HTTP Request Tool',
            'title_key': 'modules.ai.tool.examples.http.title',
            'params': {
                'module_id': 'http.request',
            }
        },
        {
            'title': 'JSON Parse Tool',
            'title_key': 'modules.ai.tool.examples.json.title',
            'params': {
                'module_id': 'data.json_parse',
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
async def ai_tool(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide tool configuration for AI Agent.

    This module doesn't execute anything directly - it tells the
    connected AI Agent which module to use as a tool via RESOURCE edge.
    """
    params = context['params']
    module_id = params.get('module_id', '')
    tool_description = params.get('tool_description', '')

    if not module_id:
        return {
            'ok': False,
            'error': 'module_id is required',
            'error_code': 'MISSING_MODULE_ID'
        }

    # Verify module exists
    from ...registry import get_registry
    registry = get_registry()
    if not registry.has(module_id):
        return {
            'ok': False,
            'error': f'Module not found: {module_id}',
            'error_code': 'MODULE_NOT_FOUND'
        }

    result = {
        'ok': True,
        '__data_type__': 'ai_tool',
        'module_id': module_id,
    }

    if tool_description:
        result['description'] = tool_description

    return result
