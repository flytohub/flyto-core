# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Template Modules

Provides modules for executing templates as nodes in workflows.
Allows templates from user's library to be used as reusable components.
"""

from .invoke import InvokeTemplate

__all__ = ['InvokeTemplate']
