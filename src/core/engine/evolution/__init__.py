# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Evolution Engine — Self-healing, self-learning, self-growing workflows.

Three layers:
1. Self-Heal: When a step fails, AI analyzes the error and generates a patch
2. Self-Learn: Patches are stored and auto-applied on future runs
3. Self-Grow: AI explores unknown websites, compiles to deterministic YAML
"""

from .healer import StepHealer
from .memory import EvolutionMemory
from .compiler import WorkflowCompiler

__all__ = ['StepHealer', 'EvolutionMemory', 'WorkflowCompiler']
