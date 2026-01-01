"""
Training Practice Infer Schema Module
Infer data schema from website
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.training.daily_practice import DailyPracticeEngine


@register_module(
    module_id='training.practice.infer_schema',
    version='1.0.0',
    category='training',
    tags=['training', 'practice', 'schema'],
    label='Practice Infer Schema',
    label_key='modules.training.practice.infer_schema.label',
    description='Infer data schema from website',
    description_key='modules.training.practice.infer_schema.description',
    icon='FileJson',
    color='#10B981',

    # Connection types
    input_types=['string'],
    output_types=['object'],


    can_receive_from=['data.*', 'file.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'file.*', 'notification.*', 'flow.*'],    params_schema=compose(
        presets.PRACTICE_URL(),
        presets.PRACTICE_SAMPLE_SIZE(),
    ),
    output_schema={
        'status': {'type': 'string'},
        'schema': {'type': 'object'},
    },
)
class TrainingPracticeInferSchema(BaseModule):
    """Infer data schema from website"""

    module_name = "Practice Infer Schema"
    module_description = "Infer data schema"

    def validate_params(self):
        if "url" not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params["url"]
        self.sample_size = self.params.get("sample_size", 5)

    async def execute(self) -> Any:
        engine = DailyPracticeEngine()
        result = await engine.infer_schema(self.url, self.sample_size)
        return result
