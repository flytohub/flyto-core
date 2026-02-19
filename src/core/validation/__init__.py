# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Flyto2 Core Validation API

Single Source of Truth for workflow validation.
Used by flyto-cloud and flyto-pro.

Usage:
    from core.validation import (
        validate_connection,
        validate_workflow,
        get_connectable,
        get_startable_modules,
    )
"""

from .connection import (
    validate_connection,
    validate_replacement,
    get_connectable,
    get_connectable_summary,
    get_connectable_for_replacement,
    ConnectionResult,
)
from .workflow import (
    validate_workflow,
    validate_start,
    validate_node_params,
    get_startable_modules,
    WorkflowResult,
    WorkflowError,
)
from .errors import ErrorCode, ERROR_MESSAGES, explain_error
from .index import ConnectionIndex

__all__ = [
    # Connection validation
    'validate_connection',
    'validate_replacement',
    'get_connectable',
    'get_connectable_summary',
    'get_connectable_for_replacement',
    'ConnectionResult',

    # Workflow validation
    'validate_workflow',
    'validate_start',
    'validate_node_params',
    'get_startable_modules',
    'WorkflowResult',
    'WorkflowError',

    # Error handling
    'ErrorCode',
    'ERROR_MESSAGES',
    'explain_error',

    # Index
    'ConnectionIndex',
]
