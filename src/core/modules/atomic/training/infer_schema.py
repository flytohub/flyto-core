"""
Training Practice Infer Schema Module
Infer data schema from website
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.training.daily_practice import DailyPracticeEngine


@register_module('training.practice.infer_schema')
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
