"""
Chain Agent Module

Sequential AI processing chain with multiple steps.
"""

import logging
from typing import Any, Dict, List

from ....base import BaseModule
from ....registry import register_module
from .....constants import OLLAMA_DEFAULT_URL, APIEndpoints
from .llm_client import LLMClientMixin

logger = logging.getLogger(__name__)


@register_module(
    module_id='agent.chain',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'string.*', 'file.*', 'api.*', 'flow.*', 'start'],
    version='1.0.0',
    category='ai',
    subcategory='agent',
    tags=['ssrf_protected', 'ai', 'agent', 'chain', 'langchain', 'workflow'],
    label='Chain Agent',
    label_key='modules.agent.chain.label',
    description='Sequential AI processing chain with multiple steps',
    description_key='modules.agent.chain.description',
    icon='Link',
    color='#7C3AED',
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY', 'ANTHROPIC_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['ai.api'],
    params_schema={
        'input': {
            'type': 'string',
            'label': 'Input',
            'label_key': 'modules.agent.chain.params.input.label',
            'description': 'Initial input for the chain',
            'description_key': 'modules.agent.chain.params.input.description',
            'required': True,
            'multiline': True
        ,
            'placeholder': 'Input data...',
},
        'chain_steps': {
            'type': 'array',
            'label': 'Chain Steps',
            'label_key': 'modules.agent.chain.params.chain_steps.label',
            'description': 'Array of processing steps (each is a prompt template)',
            'description_key': 'modules.agent.chain.params.chain_steps.description',
            'required': True
        },
        'llm_provider': {
            'type': 'select',
            'label': 'LLM Provider',
            'label_key': 'modules.agent.chain.params.llm_provider.label',
            'description': 'Choose LLM provider (cloud or local)',
            'description_key': 'modules.agent.chain.params.llm_provider.description',
            'options': [
                {'label': 'OpenAI (Cloud)', 'value': 'openai'},
                {'label': 'Ollama (Local)', 'value': 'ollama'}
            ],
            'default': 'openai',
            'required': False
        },
        'model': {
            'type': 'string',
            'label': 'Model',
            'label_key': 'modules.agent.chain.params.model.label',
            'description': 'Model name (e.g., gpt-4, llama2, mistral)',
            'description_key': 'modules.agent.chain.params.model.description',
            'default': APIEndpoints.DEFAULT_OPENAI_MODEL,
            'required': False
        ,
            'placeholder': 'gpt-4o',
},
        'ollama_url': {
            'type': 'string',
            'label': 'Ollama URL',
            'label_key': 'modules.agent.chain.params.ollama_url.label',
            'description': 'Ollama server URL (only for ollama provider)',
            'description_key': 'modules.agent.chain.params.ollama_url.description',
            'default': OLLAMA_DEFAULT_URL,
            'required': False
        ,
            'placeholder': 'http://localhost:11434',
},
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'label_key': 'modules.agent.chain.params.temperature.label',
            'description': 'Creativity level (0-2)',
            'description_key': 'modules.agent.chain.params.temperature.description',
            'default': 0.7,
            'min': 0,
            'max': 2,
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'string', 'description': 'The operation result',
                'description_key': 'modules.agent.chain.output.result.description'},
        'intermediate_results': {'type': 'array', 'description': 'Results from each step in the chain',
                'description_key': 'modules.agent.chain.output.intermediate_results.description', 'items': {'type': 'string'}},
        'steps_completed': {'type': 'number', 'description': 'The steps completed',
                'description_key': 'modules.agent.chain.output.steps_completed.description'}
    },
    examples=[
        {
            'title': 'Content pipeline',
            'params': {
                'input': 'AI and machine learning trends',
                'chain_steps': [
                    'Generate 5 blog post ideas about: {input}',
                    'Take the first idea and write a detailed outline: {previous}',
                    'Write an introduction paragraph based on: {previous}'
                ],
                'model': 'gpt-4'
            }
        },
        {
            'title': 'Data analysis chain',
            'params': {
                'input': 'User behavior data shows 60% bounce rate',
                'chain_steps': [
                    'Analyze what might cause this issue: {input}',
                    'Suggest 3 solutions based on: {previous}',
                    'Create an action plan from: {previous}'
                ]
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class ChainAgentModule(LLMClientMixin, BaseModule):
    """Chain Agent Module - Sequential AI processing"""

    def validate_params(self) -> None:
        self.input = self.params.get('input')
        self.chain_steps = self.params.get('chain_steps', [])

        if not self.input:
            raise ValueError("input is required")

        if not self.chain_steps or len(self.chain_steps) == 0:
            raise ValueError("chain_steps must contain at least one step")

        # Validate LLM parameters
        self.validate_llm_params(self.params)

    async def execute(self) -> Any:
        try:
            # Track results
            intermediate_results: List[str] = []
            current_input = self.input
            previous_output = ""

            # Process each step in the chain
            for i, step_template in enumerate(self.chain_steps):
                # Replace placeholders
                prompt = step_template.replace('{input}', current_input)
                prompt = prompt.replace('{previous}', previous_output)

                # Make API call to configured LLM provider
                output = await self._call_llm([
                    {"role": "user", "content": prompt}
                ])

                intermediate_results.append(output)
                previous_output = output

            # Final result is the last output
            result = intermediate_results[-1] if intermediate_results else ""

            return {
                "result": result,
                "intermediate_results": intermediate_results,
                "steps_completed": len(intermediate_results)
            }

        except Exception as e:
            raise RuntimeError(f"Chain agent error: {str(e)}")
