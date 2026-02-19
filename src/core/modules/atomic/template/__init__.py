# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Template Modules

Provides modules for executing templates as nodes in workflows.
Allows templates from user's library to be used as reusable components.
"""

from .invoke import InvokeTemplate

__all__ = ['InvokeTemplate']
