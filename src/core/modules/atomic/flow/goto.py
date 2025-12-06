"""
Goto Module - Unconditional jump to another step

Used for loops (jump back) and skip logic (jump forward).
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module


@register_module(
    module_id='flow.goto',
    version='1.0.0',
    category='flow',
    tags=['flow', 'goto', 'jump', 'loop', 'control'],
    label='Goto',
    label_key='modules.flow.goto.label',
    description='Unconditional jump to another step',
    description_key='modules.flow.goto.description',
    icon='CornerUpLeft',
    color='#FF5722',

    input_types=['any'],
    output_types=['jump_result'],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=['flow.control'],

    params_schema={
        'target': {
            'type': 'string',
            'label': 'Target Step',
            'label_key': 'modules.flow.goto.params.target.label',
            'description': 'Step ID to jump to',
            'description_key': 'modules.flow.goto.params.target.description',
            'required': True
        },
        'max_iterations': {
            'type': 'number',
            'label': 'Max Iterations',
            'label_key': 'modules.flow.goto.params.max_iterations.label',
            'description': 'Maximum number of times this goto can execute (prevents infinite loops)',
            'description_key': 'modules.flow.goto.params.max_iterations.description',
            'default': 100,
            'required': False
        }
    },
    output_schema={
        'next_step': {'type': 'string', 'description': 'ID of the next step to execute'},
        'iteration': {'type': 'number', 'description': 'Current iteration count for this goto'}
    },
    examples=[
        {
            'name': 'Loop back to start',
            'params': {
                'target': 'fetch_next_page',
                'max_iterations': 10
            }
        },
        {
            'name': 'Skip to end',
            'params': {
                'target': 'cleanup_step'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GotoModule(BaseModule):
    """
    Unconditional jump module

    Jumps to a specified step. Used for implementing loops and skip logic.
    Includes iteration tracking to prevent infinite loops.
    """

    module_name = "Goto"
    module_description = "Unconditional jump to another step"
    required_permission = "flow.control"

    ITERATION_PREFIX = '__goto_iteration_'

    def validate_params(self):
        if 'target' not in self.params:
            raise ValueError("Missing required parameter: target")

        self.target = self.params['target']
        self.max_iterations = self.params.get('max_iterations', 100)

        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("Parameter 'target' must be a non-empty string")

        if not isinstance(self.max_iterations, (int, float)):
            raise ValueError("Parameter 'max_iterations' must be a number")

        self.max_iterations = int(self.max_iterations)
        if self.max_iterations < 1:
            raise ValueError("Parameter 'max_iterations' must be at least 1")

    async def execute(self) -> Dict[str, Any]:
        """
        Return jump instruction for workflow engine
        """
        iteration_key = f"{self.ITERATION_PREFIX}{id(self)}"
        current_iteration = self.context.get(iteration_key, 0) + 1

        if current_iteration > self.max_iterations:
            raise RuntimeError(
                f"Goto to '{self.target}' exceeded max iterations ({self.max_iterations})"
            )

        return {
            'next_step': self.target,
            'iteration': current_iteration,
            '__set_context': {
                iteration_key: current_iteration
            }
        }
