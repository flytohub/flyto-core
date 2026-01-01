"""
Training Practice Stats Module
Get practice statistics
"""
from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from core.training.daily_practice import DailyPracticeEngine


@register_module(
    module_id='training.practice.stats',
    version='1.0.0',
    category='training',
    tags=['training', 'practice', 'stats'],
    label='Practice Stats',
    label_key='modules.training.practice.stats.label',
    description='Get practice statistics',
    description_key='modules.training.practice.stats.description',
    icon='BarChart',
    color='#10B981',

    # Connection types
    input_types=[],
    output_types=['object'],


    can_receive_from=['data.*', 'file.*', 'flow.*', 'start'],
    can_connect_to=['data.*', 'file.*', 'notification.*', 'flow.*'],    # No params needed for stats
    params_schema={},
    output_schema={
        'total_sessions': {'type': 'number'},
        'successful_sessions': {'type': 'number'},
        'success_rate': {'type': 'number'},
        'history': {'type': 'array'},
    },
)
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
