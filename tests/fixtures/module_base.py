"""
Module Test Base Class

Provides a base class for testing atomic modules with common test patterns.
"""

import pytest
from typing import Any, Dict, List, Optional, Type, Callable


class ModuleTestBase:
    """
    Base class for module tests.

    Subclasses should define:
        MODULE_ID: str - The module ID (e.g., 'string.uppercase')
        VALID_PARAMS: Dict - Valid parameters for basic execution
        EXPECTED_OUTPUT_KEYS: List[str] - Keys expected in output
    """

    MODULE_ID: str = ""
    VALID_PARAMS: Dict[str, Any] = {}
    EXPECTED_OUTPUT_KEYS: List[str] = []

    @pytest.fixture
    def module_func(self):
        """Get the module function from registry."""
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic  # Ensure modules are registered

        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.fixture
    def context(self):
        """Create execution context with valid params."""
        return {"params": self.VALID_PARAMS.copy(), "vars": {}}

    @pytest.mark.asyncio
    async def test_module_registered(self):
        """Test that module is registered in registry."""
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic

        assert ModuleRegistry.has(self.MODULE_ID), f"Module {self.MODULE_ID} not registered"

    @pytest.mark.asyncio
    async def test_module_has_metadata(self):
        """Test that module has valid metadata."""
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic

        metadata = ModuleRegistry.get_metadata(self.MODULE_ID)
        assert metadata is not None, f"Module {self.MODULE_ID} has no metadata"
        assert "version" in metadata
        assert "category" in metadata

    @pytest.mark.asyncio
    async def test_module_has_output_schema(self):
        """Test that module has output_schema defined."""
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic

        metadata = ModuleRegistry.get_metadata(self.MODULE_ID)
        assert metadata is not None
        assert "output_schema" in metadata, f"Module {self.MODULE_ID} missing output_schema"
        assert len(metadata["output_schema"]) > 0, f"Module {self.MODULE_ID} has empty output_schema"


async def run_module(module_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper function to run a module with given params.

    Args:
        module_id: The module ID
        params: Parameters to pass to the module

    Returns:
        Module execution result
    """
    from core.modules.registry import ModuleRegistry
    from core.modules import atomic

    module = ModuleRegistry.get(module_id)
    context = {"params": params, "vars": {}}

    # Check if it's a function or class
    if callable(module) and not isinstance(module, type):
        # Function-based module
        return await module(context)
    else:
        # Class-based module
        instance = module(params, context)
        return await instance.execute()
