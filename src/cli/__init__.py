"""
Workflow Engine CLI Package

Provides command-line interface for workflow automation.
"""
from core import __version__

from .main import main

__all__ = ["__version__", "main"]
