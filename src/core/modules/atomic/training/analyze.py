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

    params_schema=compose(
        presets.PRACTICE_URL(),
    ),
    output_schema={
        'status': {'type': 'string'},
        'structure': {'type': 'object'},
    },
)
class TrainingPracticeAnalyze(BaseModule):
    """Analyze website structure for practice"""

    module_name = "Practice Analyze"
    module_description = "Analyze website structure"

    def validate_params(self):
        if "url" not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params["url"]

    async def execute(self) -> Any:
        engine = DailyPracticeEngine()
        result = await engine.analyze_website(self.url)
        return result
