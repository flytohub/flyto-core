#!/usr/bin/env python3
"""
Hello World - Python Example

Shows how to use Flyto Core modules directly in Python code.

Run:
    python examples/hello_world/run_python.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.modules.registry import ModuleRegistry


async def main():
    print("=== Flyto Core: Hello World ===\n")

    # Example 1: Simple string reverse
    print("1. Reverse a string:")
    result = await ModuleRegistry.execute(
        "string.reverse",
        params={"text": "Hello Flyto"},
        context={}
    )
    print(f"   Input:  'Hello Flyto'")
    print(f"   Output: '{result['result']}'\n")

    # Example 2: Chain operations
    print("2. Chain operations (reverse + uppercase):")
    reversed_text = await ModuleRegistry.execute(
        "string.reverse",
        params={"text": "Hello Flyto"},
        context={}
    )

    uppercased = await ModuleRegistry.execute(
        "string.uppercase",
        params={"text": reversed_text['result']},
        context={}
    )
    print(f"   Input:  'Hello Flyto'")
    print(f"   Step 1: '{reversed_text['result']}' (reversed)")
    print(f"   Step 2: '{uppercased['result']}' (uppercased)\n")

    # Example 3: List available modules
    print("3. Available string modules:")
    all_modules = ModuleRegistry.list_all()
    string_modules = [m for m in all_modules.keys() if m.startswith('string.') or m.startswith('text.')]
    for module_id in sorted(string_modules)[:5]:
        print(f"   - {module_id}")
    print(f"   ... and {len(string_modules) - 5} more\n")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
