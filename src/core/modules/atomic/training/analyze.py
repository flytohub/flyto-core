"""
Training Practice Analyze Module
Analyze website structure for practice
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.training.daily_practice import DailyPracticeEngine


@register_module(
    module_id='training.practice.analyze',
    stability="beta",
    version='1.0.0',
    category='training',
    tags=['training', 'practice', 'analyze'],
    label='Practice Analyze',
    label_key='modules.training.practice.analyze.label',
    description='Analyze website structure for practice',
    description_key='modules.training.practice.analyze.description',
    icon='Search',
    color='#10B981',

    # Connection types
    input_types=['string'],
    output_types=['object'],


    can_receive_from=['data.*', 'file.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'file.*', 'notification.*', 'flow.*'],    params_schema=compose(
        presets.PRACTICE_URL(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.training.practice.analyze.output.status.description'},
        'structure': {'type': 'object', 'description': 'The structure',
                'description_key': 'modules.training.practice.analyze.output.structure.description'},
    },
    timeout_ms=30000,
)
class TrainingPracticeAnalyze(BaseModule):
    """Analyze website structure for practice"""

    module_name = "Practice Analyze"
    module_description = "Analyze website structure"

    def validate_params(self) -> None:
        if "url" not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params["url"]

    async def execute(self) -> Any:
        engine = DailyPracticeEngine()
        result = await engine.analyze_website(self.url)
        return result
