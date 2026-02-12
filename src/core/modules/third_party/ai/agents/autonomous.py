"""
Autonomous Agent Module

Self-directed AI agent with memory and goal-oriented behavior.
"""

import logging
from typing import Any, Dict, List

from ....base import BaseModule
from ....registry import register_module
from .....constants import OLLAMA_DEFAULT_URL, APIEndpoints
from .llm_client import LLMClientMixin

logger = logging.getLogger(__name__)


@register_module(
    module_id='agent.autonomous',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'string.*', 'file.*', 'api.*', 'flow.*', 'start'],
    version='1.0.0',
    category='ai',
    subcategory='agent',
    tags=['ssrf_protected', 'ai', 'agent', 'autonomous', 'memory', 'llm'],
    label='Autonomous Agent',
    label_key='modules.agent.autonomous.label',
    description='Self-directed AI agent with memory and goal-oriented behavior',
    description_key='modules.agent.autonomous.description',
    icon='Bot',
    color='#7C3AED',
    input_types=['text', 'json'],
    output_types=['text', 'json'],
    timeout_ms=180000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY', 'ANTHROPIC_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['ai.api'],
    params_schema={
        'goal': {
            'type': 'string',
            'label': 'Goal',
            'label_key': 'modules.agent.autonomous.params.goal.label',
            'description': 'The goal for the agent to achieve',
            'description_key': 'modules.agent.autonomous.params.goal.description',
            'required': True,
            'multiline': True
        ,
            'placeholder': 'Describe the goal...',
},
        'context': {
            'type': 'string',
            'label': 'Context',
            'label_key': 'modules.agent.autonomous.params.context.label',
            'description': 'Additional context or constraints',
            'description_key': 'modules.agent.autonomous.params.context.description',
            'required': False,
            'multiline': True
        ,
            'placeholder': 'Additional context...',
},
        'max_iterations': {
            'type': 'number',
            'label': 'Max Iterations',
            'label_key': 'modules.agent.autonomous.params.max_iterations.label',
            'description': 'Maximum reasoning steps',
            'description_key': 'modules.agent.autonomous.params.max_iterations.description',
            'default': 5,
            'min': 1,
            'max': 20,
            'required': False
        },
        'llm_provider': {
            'type': 'select',
            'label': 'LLM Provider',
            'label_key': 'modules.agent.autonomous.params.llm_provider.label',
            'description': 'Choose LLM provider (cloud or local)',
            'description_key': 'modules.agent.autonomous.params.llm_provider.description',
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
            'label_key': 'modules.agent.autonomous.params.model.label',
            'description': 'Model name (e.g., gpt-4, llama2, mistral)',
            'description_key': 'modules.agent.autonomous.params.model.description',
            'default': APIEndpoints.DEFAULT_OPENAI_MODEL,
            'required': False
        ,
            'placeholder': 'gpt-4o',
},
        'ollama_url': {
            'type': 'string',
            'label': 'Ollama URL',
            'label_key': 'modules.agent.autonomous.params.ollama_url.label',
            'description': 'Ollama server URL (only for ollama provider)',
            'description_key': 'modules.agent.autonomous.params.ollama_url.description',
            'default': OLLAMA_DEFAULT_URL,
            'required': False
        ,
            'placeholder': 'http://localhost:11434',
},
        'temperature': {
            'type': 'number',
            'label': 'Temperature',
            'label_key': 'modules.agent.autonomous.params.temperature.label',
            'description': 'Creativity level (0-2)',
            'description_key': 'modules.agent.autonomous.params.temperature.description',
            'default': 0.7,
            'min': 0,
            'max': 2,
            'required': False
        }
    },
    output_schema={
        'result': {'type': 'string', 'description': 'The operation result',
                'description_key': 'modules.agent.autonomous.output.result.description'},
        'thoughts': {'type': 'array', 'description': 'Agent reasoning steps',
                'description_key': 'modules.agent.autonomous.output.thoughts.description', 'items': {'type': 'string'}},
        'iterations': {'type': 'number', 'description': 'The iterations',
                'description_key': 'modules.agent.autonomous.output.iterations.description'},
        'goal_achieved': {'type': 'boolean', 'description': 'The goal achieved',
                'description_key': 'modules.agent.autonomous.output.goal_achieved.description'}
    },
    examples=[
        {
            'title': 'Research task',
            'params': {
                'goal': 'Research the latest trends in AI and summarize the top 3',
                'max_iterations': 5,
                'model': 'gpt-4'
            }
        },
        {
            'title': 'Problem solving',
            'params': {
                'goal': 'Find the best approach to optimize database queries',
                'context': 'PostgreSQL database with 10M records',
                'max_iterations': 10
            }
        }
    ],
    author='Flyto Team',
    license='MIT'
)
class AutonomousAgentModule(LLMClientMixin, BaseModule):
    """Autonomous AI Agent Module with memory and goal-oriented behavior"""

    def validate_params(self) -> None:
        self.goal = self.params.get('goal')
        self.context = self.params.get('context', '')
        self.max_iterations = self.params.get('max_iterations', 5)

        if not self.goal:
            raise ValueError("goal is required")

        # Validate LLM parameters
        self.validate_llm_params(self.params)

    async def execute(self) -> Any:
        try:
            # Agent memory (thoughts and actions)
            thoughts: List[str] = []
            memory: List[Dict[str, str]] = []

            # System prompt for autonomous agent
            system_prompt = """You are an autonomous AI agent with the ability to think step-by-step and achieve goals.

Your process:
1. Analyze the goal
2. Break it down into steps
3. Think through each step
4. Provide a final answer

Be concise but thorough. Focus on achieving the goal efficiently."""

            # Add context if provided
            if self.context:
                system_prompt += f"\n\nAdditional context: {self.context}"

            # Initial message
            memory.append({
                "role": "system",
                "content": system_prompt
            })
            memory.append({
                "role": "user",
                "content": f"Goal: {self.goal}\n\nPlease work towards achieving this goal."
            })

            result = ""
            goal_achieved = False

            # Iterative reasoning loop
            for iteration in range(self.max_iterations):
                # Make API call to configured LLM provider
                thought = await self._call_llm(memory)
                thoughts.append(thought)

                # Add to memory
                memory.append({
                    "role": "assistant",
                    "content": thought
                })

                # Check if goal is achieved
                if any(keyword in thought.lower() for keyword in ['completed', 'achieved', 'finished', 'done', 'final answer']):
                    result = thought
                    goal_achieved = True
                    break

                # Ask agent to continue if not done
                if iteration < self.max_iterations - 1:
                    memory.append({
                        "role": "user",
                        "content": "Continue working towards the goal. What's your next step?"
                    })
                else:
                    result = thought

            return {
                "result": result,
                "thoughts": thoughts,
                "iterations": len(thoughts),
                "goal_achieved": goal_achieved
            }

        except Exception as e:
            raise RuntimeError(f"Autonomous agent error: {str(e)}")
