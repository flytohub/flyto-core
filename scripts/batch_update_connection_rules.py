#!/usr/bin/env python3
"""
Batch Update Connection Rules for flyto-core modules

This script adds can_receive_from and can_connect_to to modules
that don't have them defined.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Base directory
BASE_DIR = Path(__file__).parent.parent / "src" / "core" / "modules" / "atomic"

# =============================================================================
# CATEGORY-BASED DEFAULT RULES
# =============================================================================

CATEGORY_RULES: Dict[str, Dict[str, List[str]]] = {
    # Browser - STRICT: Must stay in browser context
    'browser': {
        'can_receive_from': ['browser.*', 'flow.*'],
        'can_connect_to': ['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
    },

    # Element - Requires browser context
    'element': {
        'can_receive_from': ['browser.*', 'element.*', 'flow.*'],
        'can_connect_to': ['element.*', 'browser.*', 'data.*', 'string.*', 'flow.*', 'file.*'],
    },

    # Page - Requires browser context
    'page': {
        'can_receive_from': ['browser.*', 'page.*', 'element.*', 'flow.*'],
        'can_connect_to': ['page.*', 'browser.*', 'element.*', 'data.*', 'flow.*'],
    },

    # Screenshot - From browser, outputs image
    'screenshot': {
        'can_receive_from': ['browser.*', 'page.*', 'element.*', 'flow.*'],
        'can_connect_to': ['file.*', 'image.*', 'ai.*', 'data.*', 'flow.*', 'notification.*'],
    },

    # Flow control - Can output anywhere, input from data producers
    'flow': {
        'can_receive_from': ['data.*', 'api.*', 'http.*', 'string.*', 'array.*', 'object.*', 'math.*', 'file.*', 'database.*', 'ai.*', 'flow.*', 'element.*', 'start'],
        'can_connect_to': ['*'],
    },

    # Data - Universal input, no browser output
    'data': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # Array - Same as data
    'array': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # Object - Same as data
    'object': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # String - Same as data
    'string': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # Math - Same as data
    'math': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'math.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],
    },

    # DateTime - Same as data
    'datetime': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'string.*', 'file.*', 'database.*', 'api.*', 'notification.*', 'flow.*'],
    },

    # File - Wide input, structured output
    'file': {
        'can_receive_from': ['*'],
        'can_connect_to': ['file.*', 'data.*', 'document.*', 'image.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # Image - From specific sources
    'image': {
        'can_receive_from': ['screenshot.*', 'file.*', 'image.*', 'browser.*', 'api.*', 'flow.*', 'start'],
        'can_connect_to': ['image.*', 'file.*', 'ai.*', 'data.*', 'notification.*', 'flow.*'],
    },

    # Database - Structured data
    'database': {
        'can_receive_from': ['data.*', 'array.*', 'object.*', 'file.*', 'api.*', 'http.*', 'flow.*', 'start'],
        'can_connect_to': ['database.*', 'data.*', 'array.*', 'object.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],
    },

    # API/HTTP - No browser output
    'api': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'http.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    'http': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'api.*', 'http.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # AI - No browser output
    'ai': {
        'can_receive_from': ['data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'image.*', 'screenshot.*', 'api.*', 'http.*', 'database.*', 'ai.*', 'flow.*', 'start'],
        'can_connect_to': ['data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'database.*', 'api.*', 'notification.*', 'flow.*', 'ai.*'],
    },

    'llm': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*'],
    },

    # Analysis - Can receive from browser, no browser output
    'analysis': {
        'can_receive_from': ['browser.*', 'element.*', 'page.*', 'file.*', 'data.*', 'api.*', 'flow.*', 'start'],
        'can_connect_to': ['data.*', 'array.*', 'object.*', 'string.*', 'file.*', 'database.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # Document - File-based
    'document': {
        'can_receive_from': ['file.*', 'browser.*', 'api.*', 'document.*', 'flow.*', 'start'],
        'can_connect_to': ['document.*', 'data.*', 'string.*', 'file.*', 'ai.*', 'notification.*', 'flow.*'],
    },

    # Notification - End point
    'notification': {
        'can_receive_from': ['*'],
        'can_connect_to': ['notification.*', 'data.*', 'flow.*', 'end'],
    },

    'communication': {
        'can_receive_from': ['*'],
        'can_connect_to': ['notification.*', 'communication.*', 'data.*', 'flow.*', 'end'],
    },

    # Testing
    'test': {
        'can_receive_from': ['*'],
        'can_connect_to': ['test.*', 'flow.*', 'notification.*', 'data.*'],
    },

    'testing': {
        'can_receive_from': ['*'],
        'can_connect_to': ['testing.*', 'test.*', 'flow.*', 'notification.*', 'data.*'],
    },

    # Utility
    'utility': {
        'can_receive_from': ['*'],
        'can_connect_to': ['data.*', 'string.*', 'file.*', 'api.*', 'notification.*', 'flow.*', 'utility.*'],
    },

    # Meta - Universal (logging, debug)
    'meta': {
        'can_receive_from': ['*'],
        'can_connect_to': ['*'],
    },

    # HuggingFace - AI models
    'huggingface': {
        'can_receive_from': ['data.*', 'string.*', 'file.*', 'image.*', 'api.*', 'huggingface.*', 'flow.*', 'start'],
        'can_connect_to': ['data.*', 'string.*', 'array.*', 'object.*', 'file.*', 'ai.*', 'huggingface.*', 'notification.*', 'flow.*'],
    },

    # Vector/Embedding
    'vector': {
        'can_receive_from': ['data.*', 'string.*', 'file.*', 'ai.*', 'huggingface.*', 'flow.*'],
        'can_connect_to': ['data.*', 'array.*', 'ai.*', 'database.*', 'file.*', 'flow.*'],
    },

    # Training
    'training': {
        'can_receive_from': ['data.*', 'file.*', 'flow.*', 'start'],
        'can_connect_to': ['data.*', 'file.*', 'notification.*', 'flow.*'],
    },

    # Shell/Process
    'shell': {
        'can_receive_from': ['data.*', 'string.*', 'file.*', 'flow.*', 'start'],
        'can_connect_to': ['data.*', 'string.*', 'file.*', 'flow.*', 'test.*'],
    },

    'process': {
        'can_receive_from': ['process.*', 'flow.*', 'start'],
        'can_connect_to': ['process.*', 'port.*', 'data.*', 'flow.*', 'test.*'],
    },

    'port': {
        'can_receive_from': ['process.*', 'flow.*', 'start'],
        'can_connect_to': ['browser.*', 'http.*', 'api.*', 'flow.*', 'test.*'],
    },

    # UI
    'ui': {
        'can_receive_from': ['browser.*', 'element.*', 'flow.*'],
        'can_connect_to': ['data.*', 'test.*', 'file.*', 'flow.*'],
    },

    # Vision
    'vision': {
        'can_receive_from': ['screenshot.*', 'image.*', 'file.*', 'flow.*'],
        'can_connect_to': ['data.*', 'test.*', 'file.*', 'flow.*', 'ui.*'],
    },
}

# =============================================================================
# SPECIAL MODULE OVERRIDES
# =============================================================================

SPECIAL_MODULES: Dict[str, Dict[str, List[str]]] = {
    # browser.launch - Only connects to browser modules
    'browser.launch': {
        'can_receive_from': ['start', 'flow.*'],
        'can_connect_to': ['browser.*'],
    },
    'core.browser.launch': {
        'can_receive_from': ['start', 'flow.*'],
        'can_connect_to': ['browser.*'],
    },

    # browser.close - End of browser chain
    'browser.close': {
        'can_receive_from': ['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
        'can_connect_to': ['notification.*', 'data.*', 'file.*', 'flow.*', 'end'],
    },
    'core.browser.close': {
        'can_receive_from': ['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],
        'can_connect_to': ['notification.*', 'data.*', 'file.*', 'flow.*', 'end'],
    },

    # flow.start - Beginning of workflow
    'flow.start': {
        'can_receive_from': [],
        'can_connect_to': ['*'],
    },

    # flow.end - End of workflow
    'flow.end': {
        'can_receive_from': ['*'],
        'can_connect_to': [],
    },

    # flow.trigger - Like start
    'flow.trigger': {
        'can_receive_from': [],
        'can_connect_to': ['*'],
    },
}


def extract_category(content: str) -> Optional[str]:
    """Extract category from module file content."""
    # Try to find category='xxx' in @register_module
    match = re.search(r"category\s*=\s*['\"](\w+)['\"]", content)
    if match:
        return match.group(1)

    # Try to extract from module_id
    match = re.search(r"module_id\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        module_id = match.group(1)
        parts = module_id.split('.')
        if len(parts) >= 2:
            # Handle core.browser.launch -> browser
            if parts[0] == 'core' and len(parts) >= 2:
                return parts[1]
            return parts[0]

    return None


def extract_module_id(content: str) -> Optional[str]:
    """Extract module_id from module file content."""
    match = re.search(r"module_id\s*=\s*['\"]([^'\"]+)['\"]", content)
    if match:
        return match.group(1)
    return None


def has_connection_rules(content: str) -> bool:
    """Check if the module already has connection rules defined."""
    return 'can_receive_from' in content or 'can_connect_to' in content


def get_rules_for_module(category: str, module_id: str) -> Dict[str, List[str]]:
    """Get the appropriate connection rules for a module."""
    # Check special modules first
    if module_id in SPECIAL_MODULES:
        return SPECIAL_MODULES[module_id]

    # Fall back to category rules
    if category in CATEGORY_RULES:
        return CATEGORY_RULES[category]

    # Default: permissive
    return {
        'can_receive_from': ['*'],
        'can_connect_to': ['*'],
    }


def format_rules(rules: Dict[str, List[str]], indent: str = '    ') -> str:
    """Format rules as Python code."""
    lines = []

    # can_receive_from
    if rules['can_receive_from']:
        items = ', '.join(f"'{x}'" for x in rules['can_receive_from'])
        lines.append(f"{indent}can_receive_from=[{items}],")
    else:
        lines.append(f"{indent}can_receive_from=[],")

    # can_connect_to
    if rules['can_connect_to']:
        items = ', '.join(f"'{x}'" for x in rules['can_connect_to'])
        lines.append(f"{indent}can_connect_to=[{items}],")
    else:
        lines.append(f"{indent}can_connect_to=[],")

    return '\n' + '\n'.join(lines)


def find_insertion_point(content: str) -> Optional[int]:
    """Find the best insertion point for connection rules."""
    # Look for patterns like:
    # - After output_types=...
    # - After input_types=...
    # - After color=...
    # - After icon=...

    patterns = [
        r"output_types\s*=\s*\[[^\]]*\],?\s*\n",
        r"input_types\s*=\s*\[[^\]]*\],?\s*\n",
        r"color\s*=\s*['\"][^'\"]+['\"],?\s*\n",
        r"icon\s*=\s*['\"][^'\"]+['\"],?\s*\n",
        r"category\s*=\s*['\"][^'\"]+['\"],?\s*\n",
    ]

    best_pos = None
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            pos = match.end()
            if best_pos is None or pos > best_pos:
                best_pos = pos

    return best_pos


def update_module_file(filepath: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """
    Update a module file with connection rules.

    Returns: (success, message)
    """
    content = filepath.read_text(encoding='utf-8')

    # Skip if already has rules
    if has_connection_rules(content):
        return False, "Already has connection rules"

    # Skip if no @register_module
    if '@register_module' not in content:
        return False, "No @register_module found"

    # Extract info
    category = extract_category(content)
    module_id = extract_module_id(content)

    if not category and not module_id:
        return False, "Could not determine category or module_id"

    if not category:
        category = module_id.split('.')[0] if module_id else 'unknown'

    # Get rules
    rules = get_rules_for_module(category, module_id or '')

    # Find insertion point
    insert_pos = find_insertion_point(content)
    if insert_pos is None:
        return False, "Could not find insertion point"

    # Format rules
    rules_code = format_rules(rules)

    # Insert rules
    new_content = content[:insert_pos] + rules_code + content[insert_pos:]

    if dry_run:
        return True, f"Would add rules for {module_id} (category: {category})"

    # Write back
    filepath.write_text(new_content, encoding='utf-8')
    return True, f"Updated {module_id} (category: {category})"


def main():
    """Main function to batch update modules."""
    import argparse

    parser = argparse.ArgumentParser(description='Batch update connection rules')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--category', type=str, help='Only update specific category')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print(f"Scanning modules in: {BASE_DIR}")
    print(f"Dry run: {args.dry_run}")
    print()

    updated = 0
    skipped = 0
    errors = 0

    for filepath in sorted(BASE_DIR.rglob('*.py')):
        if filepath.name == '__init__.py':
            continue

        # Filter by category if specified
        if args.category:
            content = filepath.read_text(encoding='utf-8')
            category = extract_category(content)
            if category != args.category:
                continue

        success, message = update_module_file(filepath, dry_run=args.dry_run)

        if success:
            updated += 1
            print(f"[OK] {filepath.relative_to(BASE_DIR)}: {message}")
        else:
            skipped += 1
            if args.verbose:
                print(f"[SKIP] {filepath.relative_to(BASE_DIR)}: {message}")

    print()
    print(f"Summary:")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")

    if args.dry_run and updated > 0:
        print()
        print("Run without --dry-run to apply changes")


if __name__ == '__main__':
    main()
