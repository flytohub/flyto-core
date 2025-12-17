"""
Training Practice Execute Module
Execute practice session
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.training.daily_practice import DailyPracticeEngine


@register_module('training.practice.execute')
class TrainingPracticeExecute(BaseModule):
    """Execute practice session"""

    module_name = "Practice Execute"
    module_description = "Execute practice session"

    def validate_params(self):
        if "url" not in self.params:
            raise ValueError("Missing required parameter: url")
        self.url = self.params["url"]
        self.max_items = self.params.get("max_items", 10)

    async def execute(self) -> Any:
        engine = DailyPracticeEngine()
        result = await engine.execute_practice(self.url, self.max_items)
        return result
