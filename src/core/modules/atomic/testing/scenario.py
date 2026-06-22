# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Scenario Test Runner Module

Execute scenario-based tests.
"""

import logging
from typing import Any, Dict

from ...registry import register_module
from .runner import execute_test_steps

logger = logging.getLogger(__name__)


@register_module(
    module_id='testing.scenario.run',
    version='1.0.0',
    category='atomic',
    subcategory='testing',
    tags=['testing', 'scenario', 'bdd', 'atomic'],
    label='Run Scenario',
    label_key='modules.testing.scenario.run.label',
    description='Execute scenario-based test (BDD style)',
    description_key='modules.testing.scenario.run.description',
    icon='ListTree',
    color='#EC4899',

    input_types=['object'],
    output_types=['object'],
    can_receive_from=['start', 'flow.*', 'data.*'],
    can_connect_to=['testing.*', 'notify.*', 'data.*', 'flow.*'],

    timeout_ms=180000,
    retryable=False,

    params_schema={
        'scenario': {
            'type': 'object',
            'label': 'Scenario',
            'required': True,
            'description': 'Scenario definition with given/when/then',
            'description_key': 'modules.testing.scenario.run.params.scenario.description',
        },
        'context': {
            'type': 'object',
            'label': 'Context',
            'default': {},
            'description': 'Additional context data',
        },
    },
    output_schema={
        'ok': {'type': 'boolean', 'description': 'Whether the operation succeeded',
                'description_key': 'modules.testing.scenario.run.output.ok.description'},
        'passed': {'type': 'boolean', 'description': 'Number of tests passed',
                'description_key': 'modules.testing.scenario.run.output.passed.description'},
        'steps': {'type': 'array', 'description': 'The steps',
                'description_key': 'modules.testing.scenario.run.output.steps.description'}
    }
)
async def testing_scenario_run(context: Dict[str, Any]) -> Dict[str, Any]:
    """Run scenario test"""
    params = context['params']
    scenario = params.get('scenario', {})

    steps = []
    for phase in ['given', 'when', 'then']:
        step_def = scenario.get(phase, [])
        for s in (step_def if isinstance(step_def, list) else [step_def]):
            if isinstance(s, dict) and s.get('module'):
                executable = dict(s)
                executable.setdefault('id', f"{phase}_{len(steps) + 1}")
                executable.setdefault('name', executable.get('description', executable['id']))
                executable['phase'] = phase
                steps.append(executable)
            else:
                steps.append({
                    'id': f"{phase}_{len(steps) + 1}",
                    'phase': phase,
                    'description': s if isinstance(s, str) else s.get('description', ''),
                    'status': 'passed',
                    'note_only': True,
                })

    executable_steps = [step for step in steps if not step.get('note_only')]
    if executable_steps:
        runner_context = {key: value for key, value in context.items() if key != 'params'}
        result = await execute_test_steps(
            executable_steps,
            context=runner_context,
            stop_on_failure=params.get('stop_on_failure', True),
            timeout_per_step=params.get('timeout_per_step', 30000),
        )
        note_steps = [step for step in steps if step.get('note_only')]
        return {
            'ok': result['ok'],
            'passed': result['ok'],
            'scenario': scenario.get('name', 'Unnamed'),
            'steps': note_steps + result['results'],
            'summary': {
                'passed': result['passed'],
                'failed': result['failed'],
                'total': result['total'] + len(note_steps),
            },
        }
    return {
        'ok': True,
        'passed': True,
        'scenario': scenario.get('name', 'Unnamed'),
        'steps': steps
    }
