"""
LINT FIXTURE: Missing Required Fields (should FAIL with S001)

This module is missing required fields: module_id, version, label, description.
Expected: S001 errors for missing required fields.
"""
from typing import Any, Dict

from core.modules.base import BaseModule
from core.modules.registry import register_module


@register_module(
    # Missing: module_id, version
    category='test',
    # Missing: label, description
    icon='Warning',
    color='#EF4444',
)
class MissingFieldsModule(BaseModule):
    """Module with missing required fields."""

    module_name = "Missing Fields"
    module_description = "Test missing fields validation"

    def validate_params(self):
        pass

    async def execute(self) -> Dict[str, Any]:
        return {'result': 'test'}
