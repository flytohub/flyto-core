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
