"""
Training Practice Analyze Module
Analyze website structure for practice
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.training.daily_practice import DailyPracticeEngine


@register_module('training.practice.analyze')
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
