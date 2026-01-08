"""
AI Model Sub-Node
LLM model configuration for AI Agent (n8n-style)

This is a "sub-node" that connects to AI Agent via RESOURCE edge.
It provides the LLM configuration without affecting control flow.
"""

from typing import Any, Dict
from ...registry import register_module
from ...schema import compose, field, presets
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.model',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='sub_node',
    tags=['ai', 'llm', 'model', 'openai', 'anthropic', 'sub-node', 'ssrf_protected'],
    label='AI Model',
    label_key='modules.ai.model.label',
    description='LLM model configuration for AI Agent',
    description_key='modules.ai.model.description',
    icon='Cpu',
    color='#10B981',

    # This is a sub-node type
    node_type=NodeType.AI_SUB_NODE,

    # No control flow input - this is a resource provider
    input_types=[],
    output_types=['ai_model'],

    # Can only connect to AI Agent's model port
    can_receive_from=[],
    can_connect_to=['llm.agent'],

    # No input ports (standalone configuration node)
    input_ports=[],

    # Single output port for model configuration
    output_ports=[
        {
            'id': 'model',
            'label': 'Model',
            'label_key': 'modules.ai.model.ports.model',
            'data_type': DataType.AI_MODEL.value,
            'edge_type': EdgeType.RESOURCE.value,
            'color': '#10B981'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['filesystem.read'],

    params_schema=compose(
        presets.LLM_PROVIDER(default='openai'),
        presets.LLM_MODEL(default='gpt-4o'),
        presets.TEMPERATURE(default=0.7),
        presets.LLM_API_KEY(),
        presets.LLM_BASE_URL(),
        field(
            'max_tokens',
            type='number',
            label='Max Tokens',
            label_key='modules.ai.model.params.max_tokens',
            description='Maximum tokens in response',
            description_key='modules.ai.model.params.max_tokens.description',
            required=False,
            default=4096,
            min=1,
            max=128000
        ),
    ),

    output_schema={
        'provider': {'type': 'string', 'description': 'LLM provider name',
                'description_key': 'modules.ai.model.output.provider.description'},
        'model': {'type': 'string', 'description': 'Model identifier',
                'description_key': 'modules.ai.model.output.model.description'},
        'config': {'type': 'object', 'description': 'Full model configuration',
                'description_key': 'modules.ai.model.output.config.description'}
    },

    examples=[
        {
            'title': 'OpenAI GPT-4',
            'title_key': 'modules.ai.model.examples.gpt4.title',
            'params': {
                'provider': 'openai',
                'model': 'gpt-4o',
                'temperature': 0.7
            }
        },
        {
            'title': 'Anthropic Claude',
            'title_key': 'modules.ai.model.examples.claude.title',
            'params': {
                'provider': 'anthropic',
                'model': 'claude-3-5-sonnet-20241022',
                'temperature': 0.5
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
)
async def ai_model(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Provide LLM model configuration.

    This module doesn't execute LLM calls directly - it provides
    configuration to connected AI Agent nodes via RESOURCE edge.
    """
    import os

    params = context['params']
    provider = params.get('provider', 'openai')
    model = params.get('model', 'gpt-4o')
    temperature = params.get('temperature', 0.7)
    api_key = params.get('api_key')
    base_url = params.get('base_url')
    max_tokens = params.get('max_tokens', 4096)

    # Get API key from environment if not provided
    if not api_key:
        env_vars = {
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'google': 'GOOGLE_API_KEY',
            'azure': 'AZURE_OPENAI_API_KEY'
        }
        env_var = env_vars.get(provider)
        if env_var:
            api_key = os.getenv(env_var)

    if not api_key:
        return {
            'ok': False,
            'error': f'API key not provided for {provider}',
            'error_code': 'MISSING_API_KEY'
        }

    # Build model configuration object
    config = {
        'provider': provider,
        'model': model,
        'temperature': temperature,
        'api_key': api_key,
        'max_tokens': max_tokens
    }

    if base_url:
        config['base_url'] = base_url

    return {
        'ok': True,
        '__data_type__': 'ai_model',
        'provider': provider,
        'model': model,
        'config': config
    }
