#!/usr/bin/env python3
"""
Flyto Core - Simple Workflow Runner

Usage:
    python run.py workflow.yaml
    python run.py workflow.yaml --params '{"key": "value"}'
    python run.py  # Interactive mode
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
