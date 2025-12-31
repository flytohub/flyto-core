"""
Schema Module - Composable schema construction for Flyto modules

This module provides tools to build params_schema in a DRY, composable way.
Instead of repeating field definitions across 100+ modules, use presets.

Quick Start:
    from core.modules.schema import compose, presets

    @register_module(
        module_id="browser.goto",
        params_schema=compose(
            presets.URL(required=True),
            presets.WAIT_CONDITION(default="domcontentloaded"),
            presets.TIMEOUT_MS(default=30000),
        ),
    )
    class BrowserGotoModule(BaseModule):
        ...

Components:
    - compose: Merge multiple schema fragments
    - field: Build a single field definition
    - patch: Override properties of existing fields
    - presets: Pre-built common field definitions
    - validators: Validation rules and patterns

Benefits:
    - DRY: Define field patterns once, reuse everywhere
    - i18n: Centralized label_key management
    - Consistency: Same UI behavior for same field types
    - Maintainability: Change preset = update all modules
"""

from .builders import (
    compose,
    field,
    patch,
    extend,
    deep_merge,
    SchemaComposeError,
)
from . import presets
from . import validators

__all__ = [
    # Core builders
    "compose",
    "field",
    "patch",
    "extend",
    "deep_merge",
    "SchemaComposeError",
    # Modules
    "presets",
    "validators",
]
