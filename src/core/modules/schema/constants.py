# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Schema field visibility and grouping constants.

These constants provide a standardized way to control how fields
are displayed and organized in the UI.
"""
from __future__ import annotations


class Visibility:
    """
    Field visibility levels.

    Controls whether and when a field is shown in the UI.
    """
    DEFAULT = "default"   # Always visible
    EXPERT = "expert"     # Advanced option, collapsed by default
    HIDDEN = "hidden"     # Never shown in UI (internal use only)


class FieldGroup:
    """
    Standard field group names.

    Groups organize related fields together in the UI.
    The UI renders groups in this order: basic -> connection -> options -> advanced
    """
    BASIC = "basic"           # Essential fields (required + important)
    CONNECTION = "connection" # Connection/authentication settings
    OPTIONS = "options"       # Optional configuration
    ADVANCED = "advanced"     # Advanced settings (timeout, retry, etc.)


# Group display order for UI rendering
GROUP_ORDER = [
    FieldGroup.BASIC,
    FieldGroup.CONNECTION,
    FieldGroup.OPTIONS,
    FieldGroup.ADVANCED,
]
