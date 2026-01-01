#!/usr/bin/env python3
"""
Fix modules missing can_receive_from.
Based on REGISTER_MODULE_GUIDE.md category rules.
"""

import re
from pathlib import Path

# Category-based can_receive_from rules
CATEGORY_RULES = {
    'data': "['*']",
    'database': "['data.*', 'api.*', 'http.*', 'flow.*', 'start']",
    'communication': "['*']",
    'email': "['*']",
    'slack': "['*']",
    'webhook': "['*']",
    'document': "['file.*', 'data.*', 'api.*', 'flow.*', 'start']",
    'excel': "['file.*', 'data.*', 'api.*', 'flow.*', 'start']",
    'pdf': "['file.*', 'data.*', 'api.*', 'flow.*', 'start']",
    'word': "['file.*', 'data.*', 'api.*', 'flow.*', 'start']",
    'http': "['*']",
    'image': "['file.*', 'browser.*', 'screenshot.*', 'api.*', 'flow.*', 'start']",
    'llm': "['data.*', 'string.*', 'file.*', 'api.*', 'flow.*', 'start']",
    'huggingface': "['data.*', 'string.*', 'file.*', 'image.*', 'api.*', 'flow.*', 'start']",
    'process': "['flow.*', 'start']",
    'port': "['process.*', 'flow.*', 'start']",
    'shell': "['data.*', 'string.*', 'file.*', 'flow.*', 'start']",
    'ui': "['browser.*', 'element.*', 'flow.*']",
    'vision': "['image.*', 'file.*', 'screenshot.*', 'api.*', 'flow.*', 'start']",
}

def get_category(content: str) -> str:
    """Extract category from module content."""
    match = re.search(r"category\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        return match.group(1)
    # Try from module_id
    match = re.search(r"module_id\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        return match.group(1).split('.')[0]
    return None

def has_can_receive_from(content: str) -> bool:
    """Check if module already has can_receive_from."""
    return 'can_receive_from' in content

def add_can_receive_from(content: str, category: str) -> str:
    """Add can_receive_from after can_connect_to."""
    rule = CATEGORY_RULES.get(category, "['*']")

    # Find can_connect_to line and add can_receive_from after it
    pattern = r"(can_connect_to\s*=\s*\[[^\]]*\],?)"

    def replacer(match):
        line = match.group(1)
        # Ensure it ends with comma
        if not line.rstrip().endswith(','):
            line = line.rstrip() + ','
        return f"{line}\n    can_receive_from={rule},"

    new_content, count = re.subn(pattern, replacer, content)
    return new_content, count > 0

def process_file(filepath: Path) -> bool:
    """Process a single file."""
    content = filepath.read_text()

    if '@register_module' not in content:
        return False

    if has_can_receive_from(content):
        return False

    if 'can_connect_to' not in content:
        print(f"  SKIP (no can_connect_to): {filepath.name}")
        return False

    category = get_category(content)
    if not category:
        print(f"  SKIP (no category): {filepath.name}")
        return False

    new_content, modified = add_can_receive_from(content, category)

    if modified:
        filepath.write_text(new_content)
        print(f"  FIXED: {filepath.name} (category: {category})")
        return True
    else:
        print(f"  FAILED: {filepath.name}")
        return False

def main():
    root = Path(__file__).parent.parent / "src" / "core" / "modules" / "atomic"

    print("Scanning for modules missing can_receive_from...")
    print()

    fixed = 0
    skipped = 0

    for py_file in sorted(root.rglob("*.py")):
        if py_file.name.startswith("__"):
            continue
        if py_file.name.startswith("_"):
            continue

        content = py_file.read_text()

        if '@register_module' not in content:
            continue

        if has_can_receive_from(content):
            continue

        if 'can_connect_to' not in content:
            skipped += 1
            continue

        if process_file(py_file):
            fixed += 1
        else:
            skipped += 1

    print()
    print(f"Fixed: {fixed} modules")
    print(f"Skipped: {skipped} modules")

if __name__ == "__main__":
    main()
