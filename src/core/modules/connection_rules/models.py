# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Connection Rules Models

Data classes and enums for connection rules.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class ConnectionCategory(str, Enum):
    """Categories for connection rule grouping"""
    BROWSER = "browser"
    FLOW = "flow"
    DATA = "data"
    FILE = "file"
    DATABASE = "database"
    API = "api"
    AI = "ai"
    DOCUMENT = "document"
    NOTIFICATION = "notification"
    ANALYSIS = "analysis"
    UTILITY = "utility"
    ANY = "*"


@dataclass
class ConnectionRule:
    """
    Connection rule for a category of modules.

    Attributes:
        category: Module category (e.g., "browser")
        can_connect_to: List of patterns for allowed targets
        can_receive_from: List of patterns for allowed sources
        description: Human-readable rule description
    """
    category: str
    can_connect_to: List[str]
    can_receive_from: List[str]
    description: str = ""
