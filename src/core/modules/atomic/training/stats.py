"""
Training Practice Stats Module
Get practice statistics
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.training.daily_practice import DailyPracticeEngine


@register_module('training.practice.stats')
class TrainingPracticeStats(BaseModule):
    """Get practice statistics"""

    module_name = "Practice Stats"
    module_description = "Get practice statistics"

    def validate_params(self):
        pass

    async def execute(self) -> Any:
        engine = DailyPracticeEngine()
        history = engine.get_practice_history()

        total_sessions = len(history)
        successful_sessions = sum(1 for s in history if s.get("success_rate", 0) > 0.5)

        return {
            "total_sessions": total_sessions,
            "successful_sessions": successful_sessions,
            "success_rate": successful_sessions / total_sessions if total_sessions > 0 else 0,
            "history": history
        }
