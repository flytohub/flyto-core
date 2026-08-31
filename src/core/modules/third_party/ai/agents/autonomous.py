# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Autonomous Agent Module

Self-directed AI agent with memory and goal-oriented behavior.

HOW FAR THIS MODULE FOLLOWS REALITY

One return path, one rung: ACCEPTED. The agent runs no tools -- every iteration
is an LLM call and the only thing that leaves this process is a request to a
provider. Reaching the return means N completions came back, which is the peer
acknowledging its own work and is the whole of what is claimed.

THE FIELD THIS MODULE MUST NOT REST A RUNG ON is `goal_achieved`. It is
produced here:

    if any(keyword in thought.lower()
           for keyword in ['completed', 'achieved', 'finished', 'done', 'final answer']):

A substring scan of prose the model wrote about itself. It is not a check that
the goal was reached; it is not even a reliable check that the model *said* the
goal was reached. Measured against its own keyword list:

  * "I have not finished this yet"     contains "finished"  -> True
  * "I abandoned that approach"        contains "done"      -> True
  * "this cannot be completed"         contains "completed" -> True

so the field reads True for an agent explicitly reporting failure. That is left
as it is rather than swapped for a different heuristic -- word boundaries would
fix "abandoned" and still not fix "not finished", and quietly replacing one
guess with a slightly better guess is how a guess keeps its air of measurement.
What changes is that the envelope now says exactly what the boolean is measured
by, so nothing downstream can read it as a verified outcome. It is reported as
`goal_achieved_is_a_substring_match`, and no rung anywhere in this file moves
because of it.

WHY MAX-ITERATIONS IS NOT INDETERMINATE HERE, though `llm.agent` makes it so.
There, exhausting the loop leaves tools half-run and the world in a state nobody
can describe. Here the loop only produces text: whether it ended on the keyword
scan or on the iteration ceiling, the same fact holds either way -- N
completions came back and nothing else happened. The uncertainty is about the
GOAL, and the goal was never declared as a postcondition, so it is not a
question this axis answers.

The failure path raises, and no envelope can ride on a raise in this engine.
"""

import logging
from typing import Any, Dict, List

from .....engine.outcome import ClaimBy, Outcome, envelope
from ....base import BaseModule
from ....registry import register_module
from .....constants import OLLAMA_DEFAULT_URL, APIEndpoints
from .llm_client import LLMClientMixin

logger = logging.getLogger(__name__)


#: The one sentence this module owes anybody reading `goal_achieved`.
_GOAL_FLAG_IS_A_GUESS = {
    'kind': 'goal_achieved_is_a_substring_match',
    'measured_by': (
        "`any(keyword in thought.lower())` over "
        "['completed', 'achieved', 'finished', 'done', 'final answer'] "
        "against text the model wrote about itself"
    ),
    'detail': (
        'Not a check that the goal was reached, and not a reliable check that '
        'the model claimed it was. "I have not finished" contains "finished"; '
        '"I abandoned that" contains "done". The flag reads True for an agent '
        'reporting failure, so no rung rests on it and nothing downstream '
        'should render it as a completed task.'
    ),
}


def _loop_never_ran(max_iterations: Any) -> Dict[str, Any]:
    """FAILED: zero iterations, so nobody was asked anything.

    `max_iterations` is read straight off the params with no bounds check --
    `validate_params` does `self.params.get('max_iterations', 5)` and the
    schema's `min: 1` is never enforced, because this class does not opt into
    `auto_validate_schema`. So `range(0)` is reachable, and it returns the
    ordinary success shape: `result` is "", `thoughts` is [], `ok` is implicit.
    ACCEPTED on that path would say a provider acknowledged something when no
    request was ever built.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[{
            'kind': 'agent_loop_never_ran',
            'max_iterations': max_iterations,
            'measured_by': 'len(thoughts) == 0 after the reasoning loop',
            'detail': (
                'The iteration ceiling admitted no passes, so no completion was '
                'requested and nothing was billed. The empty result this returns '
                'is not an answer.'
            ),
        }],
    )


def _agent_answered(
    *,
    provider: str,
    model: str,
    iterations: int,
    max_iterations: int,
    goal_achieved: bool,
) -> Dict[str, Any]:
    """ACCEPTED: N completions came back. Nothing about the goal was evaluated."""
    return envelope(
        Outcome.ACCEPTED,
        claim_by=ClaimBy.NONE,
        effects=[
            {
                'kind': 'reasoning_completions_returned',
                'provider': provider,
                'model': model,
                'iterations': iterations,
                'max_iterations': max_iterations,
                'stopped_on': 'keyword_scan' if goal_achieved else 'iteration_ceiling',
                'measured_by': 'len() of the thoughts collected, one per _call_llm return',
                'detail': (
                    'Each iteration is the provider reporting on its own work. '
                    'This agent invokes no tools, so nothing outside this process '
                    'changed except the provider\'s billing.'
                ),
            },
            _GOAL_FLAG_IS_A_GUESS,
        ],
    )


@register_module(
    module_id='agent.autonomous',
    can_connect_to=['*'],
    can_receive_from=['*'],
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
    input_types=['any'],
    output_types=['text', 'json'],
    timeout_ms=180000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_AI_API_KEY'],
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
                {'label': 'Anthropic (Cloud)', 'value': 'anthropic'},
                {'label': 'Google Gemini (Cloud)', 'value': 'gemini'},
                {'label': 'Ollama (Local)', 'value': 'ollama'},
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
        'goal_achieved': {'type': 'boolean',
                'description': (
                    'True when the last thought contained any of the words '
                    'completed/achieved/finished/done/"final answer". A substring '
                    "match on the model's own prose, not a check that the goal "
                    'was reached -- "I have not finished" sets it True'
                ),
                'description_key': 'modules.agent.autonomous.output.goal_achieved.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far this run was followed into reality: always '
                    '"accepted" on the return path -- N completions came back and '
                    'this agent runs no tools, so nothing else happened. Never '
                    'derived from goal_achieved, which is a substring match'
                ),
                'description_key': 'modules.agent.autonomous.output.outcome.description'}
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
                "goal_achieved": goal_achieved,
                "outcome": (
                    _agent_answered(
                        provider=self.llm_provider,
                        model=self.model,
                        iterations=len(thoughts),
                        max_iterations=self.max_iterations,
                        goal_achieved=goal_achieved,
                    )
                    if thoughts
                    else _loop_never_ran(self.max_iterations)
                ),
            }

        except Exception as e:
            raise RuntimeError(f"Autonomous agent error: {str(e)}")
