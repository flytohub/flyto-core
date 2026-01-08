"""
Training Practice Execute Module
Execute practice session
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from core.training.daily_practice import DailyPracticeEngine


@register_module(
    module_id='training.practice.execute',
    stability="beta",
    version='1.0.0',
    category='training',
    tags=['training', 'practice', 'execute'],
    label='Practice Execute',
    label_key='modules.training.practice.execute.label',
    description='Execute practice session',
    description_key='modules.training.practice.execute.description',
    icon='Play',
    color='#10B981',

    # Connection types
    input_types=['string'],
    output_types=['object'],


    can_receive_from=['data.*', 'file.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'file.*', 'notification.*', 'flow.*'],    params_schema=compose(
        presets.PRACTICE_URL(),
        presets.PRACTICE_MAX_ITEMS(),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.training.practice.execute.output.status.description'},
        'items_processed': {'type': 'number', 'description': 'The items processed',
                'description_key': 'modules.training.practice.execute.output.items_processed.description'},
    },
    timeout_ms=30000,
)
class TrainingPracticeExecute(BaseModule):
    """Execute practice session"""

    module_name = "Practice Execute"
    module_description = "Execute practice session"

    def validate_params(self) -> None:
        if "url" not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params["url"]
        self.max_items = self.params.get("max_items", 10)

    async def execute(self) -> Any:
        engine = DailyPracticeEngine()
        result = await engine.execute_practice(self.url, self.max_items)
        return result
