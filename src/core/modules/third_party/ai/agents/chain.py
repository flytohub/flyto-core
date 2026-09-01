# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Chain Agent Module

Sequential AI processing chain with multiple steps.

HOW FAR THIS MODULE FOLLOWS REALITY

One return path, one rung: ACCEPTED. Every step in the chain is one LLM call
and every LLM call is the provider describing its own work, so the highest
honest claim is that the provider answered -- N times, once per step.

  the whole chain ran                            ACCEPTED
      Reaching the return means `_call_llm` came back without raising for each
      of the N steps. That is real evidence the calls happened, and it is
      evidence of nothing else. No step's output is validated, parsed or
      checked against its prompt; a chain step that asked for JSON and got an
      apology is indistinguishable here from one that worked.

`steps_completed` is deliberately NOT the thing the rung rests on, even though
it is a count of real completions. On this return path it is always
`len(chain_steps)`, because a partial chain raises instead of returning -- so it
is the caller's own input read back, and the test this contract is built on
("would this value be the same if the effect had not happened?") says it is not
evidence. The count of completions that came back non-empty is a different
number and is carried separately for exactly that reason.

THE FAILURE PATH CARRIES NOTHING, and that is a gap worth naming rather than
papering over. `except Exception -> raise RuntimeError` means a chain that died
on step 5 of 7 has already paid for four completions, and the exception that
reaches the executor says so nowhere. An envelope cannot ride on a raise in this
engine; making that path reportable would mean changing what this module returns
on failure, which is a bigger change than an outcome contract should smuggle in.
"""

import logging
from typing import Any, Dict, List

from .....engine.outcome import ClaimBy, Outcome, envelope
from ....base import BaseModule
from ....registry import register_module
from .....constants import OLLAMA_DEFAULT_URL, APIEndpoints
from .llm_client import LLMClientMixin

logger = logging.getLogger(__name__)


def _chain_completed(
    *,
    provider: str,
    model: str,
    steps_requested: int,
    completions: List[Any],
) -> Dict[str, Any]:
    """ACCEPTED: the provider answered once per step, and that is the whole claim."""
    non_empty = sum(1 for output in completions if isinstance(output, str) and output.strip())
    effects = [{
        'kind': 'chain_completions_returned',
        'provider': provider,
        'model': model,
        'steps_requested': steps_requested,
        'completions_returned': len(completions),
        'completions_with_text': non_empty,
        'measured_by': (
            'one _call_llm return per step, counted in the loop; '
            'completions_with_text is len() over the ones that were non-blank strings'
        ),
        'detail': (
            'Each step is the provider reporting on its own work. Nothing here '
            'evaluates whether any step did what its prompt asked -- a step that '
            'was told to return JSON and returned an apology looks the same.'
        ),
    }]
    if non_empty < len(completions):
        effects.append({
            'kind': 'chain_step_returned_no_text',
            'blank_completions': len(completions) - non_empty,
            'measured_by': 'the same loop count, inverted',
            'detail': (
                'At least one step came back empty or non-textual. The provider '
                'still answered, which is why this stays accepted, but the '
                'result flowing downstream from a blank step is a blank, and a '
                'blank substituted into the next step\'s {previous} placeholder '
                'is what the chain was built on.'
            ),
        })
    return envelope(Outcome.ACCEPTED, claim_by=ClaimBy.NONE, effects=effects)


@register_module(
    module_id='agent.chain',
    can_connect_to=['*'],
    can_receive_from=['*'],
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
    input_types=['any'],
    output_types=['text', 'json'],
    timeout_ms=120000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,
    requires_credentials=True,
    credential_keys=['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_AI_API_KEY'],
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
                {'label': 'Anthropic (Cloud)', 'value': 'anthropic'},
                {'label': 'Google Gemini (Cloud)', 'value': 'gemini'},
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
                'description_key': 'modules.agent.chain.output.steps_completed.description'},
        'outcome': {'type': 'object',
                'description': (
                    'How far this chain was followed into reality: always '
                    '"accepted" on the return path -- the provider answered once '
                    'per step and nothing here evaluates any answer. The failure '
                    'path raises and carries no envelope at all'
                ),
                'description_key': 'modules.agent.chain.output.outcome.description'}
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
                "steps_completed": len(intermediate_results),
                "outcome": _chain_completed(
                    provider=self.llm_provider,
                    model=self.model,
                    steps_requested=len(self.chain_steps),
                    completions=intermediate_results,
                ),
            }

        except Exception as e:
            raise RuntimeError(f"Chain agent error: {str(e)}")
