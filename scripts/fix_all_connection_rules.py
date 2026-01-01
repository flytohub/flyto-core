#!/usr/bin/env python3
"""
Fix ALL modules missing can_receive_from across all directories.
"""

import re
from pathlib import Path

# Default rules by category
CATEGORY_RULES = {
    # Core categories
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

    # Third-party categories
    'api': "['*']",
    'ai': "['data.*', 'string.*', 'file.*', 'api.*', 'flow.*', 'start']",
    'cloud': "['data.*', 'file.*', 'api.*', 'flow.*', 'start']",
    'developer': "['*']",
    'payment': "['data.*', 'api.*', 'flow.*', 'start']",
    'productivity': "['data.*', 'api.*', 'flow.*', 'start']",

    # Integration categories
    'jira': "['data.*', 'api.*', 'flow.*', 'start']",
    'salesforce': "['data.*', 'api.*', 'flow.*', 'start']",

    # Default
    'default': "['*']",
}

def get_category(content: str) -> str:
    """Extract category from module content."""
    match = re.search(r"category\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        return match.group(1)
    # Try from module_id
    match = re.search(r"module_id\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        parts = match.group(1).split('.')
        # Skip 'core' or 'api' prefix if present
        if parts[0] in ('core', 'api') and len(parts) > 1:
            return parts[1]
        return parts[0]
    return 'default'

def add_can_receive_from(content: str, category: str) -> tuple:
    """Add can_receive_from after can_connect_to."""
    rule = CATEGORY_RULES.get(category, CATEGORY_RULES['default'])

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

    if 'can_receive_from' in content:
        return False

    if 'can_connect_to' not in content:
        # Add both rules
        category = get_category(content)
        rule_receive = CATEGORY_RULES.get(category, CATEGORY_RULES['default'])

        # Find @register_module( and add rules after first few lines
        pattern = r"(@register_module\s*\(\s*\n\s*module_id\s*=\s*['\"][^'\"]+['\"],)"

        def replacer(match):
            return match.group(1) + f"\n    can_connect_to=['*'],\n    can_receive_from={rule_receive},"

        new_content, count = re.subn(pattern, replacer, content)
        if count > 0:
            filepath.write_text(new_content)
            print(f"  ADDED BOTH: {filepath.name} (category: {category})")
            return True
        else:
            print(f"  SKIP (no can_connect_to pattern): {filepath.name}")
            return False

    category = get_category(content)
    new_content, modified = add_can_receive_from(content, category)

    if modified:
        filepath.write_text(new_content)
        print(f"  FIXED: {filepath.name} (category: {category})")
        return True
    else:
        print(f"  FAILED: {filepath.name}")
        return False

def main():
    roots = [
        Path("src/core/modules/atomic"),
        Path("src/core/modules/third_party"),
        Path("src/core/modules/integrations"),
    ]

    print("Scanning for modules missing can_receive_from...")
    print()

    fixed = 0
    skipped = 0

    for root in roots:
        if not root.exists():
            continue

        print(f"Scanning {root}...")

        for py_file in sorted(root.rglob("*.py")):
            if py_file.name.startswith("__"):
                continue
            if py_file.name.startswith("_"):
                continue

            content = py_file.read_text()

            if '@register_module' not in content:
                continue

            if 'can_receive_from' in content:
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
