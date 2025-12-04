"""
Meta Module Generator - Wrapper for ModuleGenerator

Allows workflows to generate new modules
"""

from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module
from src.core.meta.module_generator import ModuleGenerator
from typing import Any, Dict


@register_module('meta.modules.test_generator')
class TestGeneratorModule(BaseModule):
    """
    Test the module generator (for testing only)

    Parameters:
        module_spec (dict): Module specification

    Returns:
        Generation result
    """

    module_name = "TestGenerator"
    module_description = "Test module generation capability"

    def validate_params(self):
        """Validate and extract parameters"""
        if "module_spec" not in self.params:
            raise ValueError("Missing required parameter: module_spec")
        self.module_spec = self.params["module_spec"]

    async def execute(self) -> Any:
        """
        Test module generation

        Returns:
            Generation result
        """
        try:
            generator = ModuleGenerator()
            result = generator.generate_module(self.module_spec)

            return result

        except Exception as e:
            raise RuntimeError(f"Module generation test failed: {str(e)}")


@register_module('meta.modules.generate')
class GenerateModuleModule(BaseModule):
    """
    Generate a new module from specification

    Parameters:
        module_id (str): Module ID (e.g., "string.reverse")
        description (str): Module description
        category (str): Module category
        params (dict): Parameter specifications
        returns (str): Return type description
        examples (list): Example usages (optional)

    Returns:
        Generation result with paths and code
    """

    module_name = "GenerateModule"
    module_description = "Generate new module from specification"

    def validate_params(self):
        """Validate and extract parameters"""
        required = ["module_id", "description", "category", "params", "returns"]
        for param in required:
            if param not in self.params:
                raise ValueError(f"Missing required parameter: {param}")

        self.module_id = self.params["module_id"]
        self.description = self.params["description"]
        self.category = self.params["category"]
        self.param_specs = self.params["params"]
        self.returns = self.params["returns"]
        self.examples = self.params.get("examples", [])

    async def execute(self) -> Any:
        """
        Generate module

        Returns:
            Generation result
        """
        try:
            spec = {
                "module_id": self.module_id,
                "description": self.description,
                "category": self.category,
                "params": self.param_specs,
                "returns": self.returns,
                "examples": self.examples
            }

            generator = ModuleGenerator()
            result = generator.generate_module(spec)

            return result

        except Exception as e:
            raise RuntimeError(f"Module generation failed: {str(e)}")
