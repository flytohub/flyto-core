"""
AI Agent Modules

Provides autonomous AI agents with memory and reasoning capabilities.
"""
import logging
import os
from typing import Any, Dict, List

from ...base import BaseModule
from ...registry import register_module
from ....constants import (
    OLLAMA_DEFAULT_URL,
    DEFAULT_LLM_MAX_TOKENS,
    EnvVars,
    APIEndpoints,
)


logger = logging.getLogger(__name__)


@register_module(
    module_id='agent.autonomous',
    version='1.0.0',
    category='ai',
    subcategory='agent',
    tags=['ai', 'agent', 'autonomous', 'memory', 'llm'],
    label='Autonomous Agent',
    label_key='modules.agent.autonomous.label',
    description='Self-directed AI agent with memory and goal-oriented behavior',
    description_key='modules.agent.autonomous.description',
    icon='Bot',
    color='#7C3AED',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],

    # Phase 2: Execution settings
    timeout=180,  # 3 minutes for agent reasoning
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'ai.api'],

    params_schema={
        'goal': {
            'type': 'string',
            'label': 'Goal',
            'label_key': 'modules.agent.autonomous.params.goal.label',
            'description': 'The goal for the agent to achieve',
            'description_key': 'modules.agent.autonomous.params.goal.description',
            'required': True,
            'multiline': True
        },
        'context': {
            'type': 'string',
            'label': 'Context',
            'label_key': 'modules.agent.autonomous.params.context.label',
            'description': 'Additional context or constraints',
            'description_key': 'modules.agent.autonomous.params.context.description',
            'required': False,
            'multiline': True
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
        },
        'ollama_url': {
            'type': 'string',
            'label': 'Ollama URL',
            'label_key': 'modules.agent.autonomous.params.ollama_url.label',
            'description': 'Ollama server URL (only for ollama provider)',
            'description_key': 'modules.agent.autonomous.params.ollama_url.description',
            'default': OLLAMA_DEFAULT_URL,
            'required': False
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
        'result': {'type': 'string'},
        'thoughts': {'type': 'array', 'items': {'type': 'string'}},
        'iterations': {'type': 'number'},
        'goal_achieved': {'type': 'boolean'}
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
    author='Flyto2 Team',
    license='MIT'
)
class AutonomousAgentModule(BaseModule):
    """Autonomous AI Agent Module with memory and goal-oriented behavior"""

    def validate_params(self):
        self.goal = self.params.get('goal')
        self.context = self.params.get('context', '')
        self.max_iterations = self.params.get('max_iterations', 5)
        self.llm_provider = self.params.get('llm_provider', 'openai')
        self.model = self.params.get('model', APIEndpoints.DEFAULT_OPENAI_MODEL)
        self.ollama_url = self.params.get('ollama_url', OLLAMA_DEFAULT_URL)
        self.temperature = self.params.get('temperature', 0.7)

        if not self.goal:
            raise ValueError("goal is required")

        # Validate provider-specific requirements
        if self.llm_provider == 'openai':
            self.api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
            if not self.api_key:
                raise ValueError(f"{EnvVars.OPENAI_API_KEY} environment variable is required for OpenAI provider")
        elif self.llm_provider == 'ollama':
            # No API key needed for local Ollama
            self.api_key = None
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call LLM based on configured provider"""
        if self.llm_provider == 'openai':
            return await self._call_openai(messages)
        elif self.llm_provider == 'ollama':
            return await self._call_ollama(messages)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """Call OpenAI API"""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. "
                "Install with: pip install openai"
            )

        openai.api_key = self.api_key
        response = await openai.ChatCompletion.acreate(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=DEFAULT_LLM_MAX_TOKENS
        )
        return response.choices[0].message.content

    async def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        """Call local Ollama API"""
        import aiohttp

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": DEFAULT_LLM_MAX_TOKENS
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Ollama API error (status {response.status}): {error_text}"
                    )
                result = await response.json()

        message = result.get('message', {})
        return message.get('content', '')

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


@register_module(
    module_id='agent.chain',
    version='1.0.0',
    category='ai',
    subcategory='agent',
    tags=['ai', 'agent', 'chain', 'langchain', 'workflow'],
    label='Chain Agent',
    label_key='modules.agent.chain.label',
    description='Sequential AI processing chain with multiple steps',
    description_key='modules.agent.chain.description',
    icon='Link',
    color='#7C3AED',

    # Connection types
    input_types=['text', 'json'],
    output_types=['text', 'json'],

    # Phase 2: Execution settings
    timeout=120,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'ai.api'],

    params_schema={
        'input': {
            'type': 'string',
            'label': 'Input',
            'label_key': 'modules.agent.chain.params.input.label',
            'description': 'Initial input for the chain',
            'description_key': 'modules.agent.chain.params.input.description',
            'required': True,
            'multiline': True
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
        },
        'ollama_url': {
            'type': 'string',
            'label': 'Ollama URL',
            'label_key': 'modules.agent.chain.params.ollama_url.label',
            'description': 'Ollama server URL (only for ollama provider)',
            'description_key': 'modules.agent.chain.params.ollama_url.description',
            'default': OLLAMA_DEFAULT_URL,
            'required': False
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
        'result': {'type': 'string'},
        'intermediate_results': {'type': 'array', 'items': {'type': 'string'}},
        'steps_completed': {'type': 'number'}
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
    author='Flyto2 Team',
    license='MIT'
)
class ChainAgentModule(BaseModule):
    """Chain Agent Module - Sequential AI processing"""

    def validate_params(self):
        self.input = self.params.get('input')
        self.chain_steps = self.params.get('chain_steps', [])
        self.llm_provider = self.params.get('llm_provider', 'openai')
        self.model = self.params.get('model', APIEndpoints.DEFAULT_OPENAI_MODEL)
        self.ollama_url = self.params.get('ollama_url', OLLAMA_DEFAULT_URL)
        self.temperature = self.params.get('temperature', 0.7)

        if not self.input:
            raise ValueError("input is required")

        if not self.chain_steps or len(self.chain_steps) == 0:
            raise ValueError("chain_steps must contain at least one step")

        # Validate provider-specific requirements
        if self.llm_provider == 'openai':
            self.api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
            if not self.api_key:
                raise ValueError(f"{EnvVars.OPENAI_API_KEY} environment variable is required for OpenAI provider")
        elif self.llm_provider == 'ollama':
            # No API key needed for local Ollama
            self.api_key = None
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call LLM based on configured provider"""
        if self.llm_provider == 'openai':
            return await self._call_openai(messages)
        elif self.llm_provider == 'ollama':
            return await self._call_ollama(messages)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    async def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """Call OpenAI API"""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI library not installed. "
                "Install with: pip install openai"
            )

        openai.api_key = self.api_key
        response = await openai.ChatCompletion.acreate(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=DEFAULT_LLM_MAX_TOKENS
        )
        return response.choices[0].message.content

    async def _call_ollama(self, messages: List[Dict[str, str]]) -> str:
        """Call local Ollama API"""
        import aiohttp

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": DEFAULT_LLM_MAX_TOKENS
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.ollama_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Ollama API error (status {response.status}): {error_text}"
                    )
                result = await response.json()

        message = result.get('message', {})
        return message.get('content', '')

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
