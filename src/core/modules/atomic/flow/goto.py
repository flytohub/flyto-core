"""
Goto Module - Unconditional jump to another step

Used for loops (jump back) and skip logic (jump forward).
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...types import DataType, EdgeType


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

    # Control flow - no data input/output
    input_types=[],
    output_types=[],


    can_receive_from=['data.*', 'api.*', 'http.*', 'string.*', 'array.*', 'object.*', 'math.*', 'file.*', 'database.*', 'ai.*', 'flow.*', 'element.*'],
    can_connect_to=['*'],

    # Port definitions (required for flow modules)
    input_ports=[
        {
            'id': 'input',
            'label': 'Input',
            'label_key': 'modules.flow.goto.ports.input',
            'data_type': DataType.ANY.value,
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1,
            'required': True
        }
    ],
    output_ports=[
        {
            'id': 'goto',
            'label': 'Goto',
            'label_key': 'modules.flow.goto.ports.goto',
            'event': 'goto',
            'color': '#FF5722',
            'edge_type': EdgeType.CONTROL.value,
            'max_connections': 1
        }
    ],    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.TARGET_STEP(required=True),
        presets.MAX_ITERATIONS(default=100),
    ),
    output_schema={
        '__event__': {'type': 'string', 'description': 'Event for routing (goto)',
                'description_key': 'modules.flow.goto.output.__event__.description'},
        'target': {'type': 'string', 'description': 'ID of the target step',
                'description_key': 'modules.flow.goto.output.target.description'},
        'iteration': {'type': 'number', 'description': 'Current iteration count for this goto',
                'description_key': 'modules.flow.goto.output.iteration.description'}
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
    license='MIT',
    timeout_ms=5000,
)
class GotoModule(BaseModule):
    """
    Unconditional jump module

    Jumps to a specified step. Used for implementing loops and skip logic.
    Includes iteration tracking to prevent infinite loops.
    """

    module_name = "Goto"
    module_description = "Unconditional jump to another step"
    required_permission = ITERATION_PREFIX = '__goto_iteration_'

    def validate_params(self) -> None:
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
            '__event__': 'goto',
            'target': self.target,
            'iteration': current_iteration,
            '__set_context': {
                iteration_key: current_iteration
            }
        }
