#!/usr/bin/env python3
"""
Schema Fixer - Automatically fix schema issues in flyto-core modules

This script fixes missing schema properties in @register_module decorators by:
1. Adding placeholders to params_schema string/number fields
2. Adding descriptions to params_schema and output_schema fields
3. Adding labels to params_schema fields
4. Adding input_types/output_types based on category

The script uses regex-based text replacement to preserve code formatting.

Usage:
    # Preview changes
    python scripts/fix_schema.py --dry-run --verbose

    # Fix all modules
    python scripts/fix_schema.py

    # Fix specific module
    python scripts/fix_schema.py --module-id string.uppercase

    # Fix and show verbose output
    python scripts/fix_schema.py --verbose

Author: Claude (Anthropic)
Date: 2026-02-11
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional


# ==============================================================================
# PLACEHOLDER GENERATION
# ==============================================================================

PLACEHOLDER_PATTERNS = [
    # URLs and network
    (r'.*url.*', 'https://example.com'),
    (r'.*uri.*', 'https://api.example.com/endpoint'),
    (r'.*endpoint.*', 'https://api.example.com/v1'),
    (r'.*host(name)?.*', 'localhost'),
    (r'.*port.*', '8080'),
    (r'.*ip.*', '127.0.0.1'),
    (r'.*domain.*', 'example.com'),

    # Paths and files
    (r'.*path.*', '/path/to/file'),
    (r'.*file.*', '/path/to/file.txt'),
    (r'.*dir(ectory)?.*', '/path/to/directory'),
    (r'.*folder.*', '/path/to/folder'),

    # Authentication
    (r'.*api[_-]?key.*', 'your-api-key'),
    (r'.*token.*', 'your-token'),
    (r'.*secret.*', 'your-secret'),
    (r'.*password.*', 'password'),
    (r'.*user(name)?.*', 'username'),
    (r'.*email.*', 'user@example.com'),

    # Data formats
    (r'.*json.*', '{"key": "value"}'),
    (r'.*xml.*', '<root></root>'),
    (r'.*html.*', '<div>content</div>'),
    (r'.*sql.*', 'SELECT * FROM table'),
    (r'.*query.*', 'SELECT * FROM table'),
    (r'.*regex.*', '^[a-zA-Z0-9]+$'),
    (r'.*pattern.*', '^pattern$'),

    # Text fields
    (r'.*text.*', 'Enter text...'),
    (r'.*content.*', 'Enter content...'),
    (r'.*message.*', 'Your message here'),
    (r'.*body.*', 'Request body'),
    (r'.*title.*', 'Title'),
    (r'.*name.*', 'Name'),
    (r'.*description.*', 'Description'),
    (r'.*comment.*', 'Comment'),

    # Database
    (r'.*table.*', 'table_name'),
    (r'.*database.*', 'database_name'),
    (r'.*collection.*', 'collection_name'),
    (r'.*index.*', 'index_name'),

    # Identifiers
    (r'.*(uuid|guid).*', '550e8400-e29b-41d4-a716-446655440000'),
    (r'.*id.*', 'example-id'),
    (r'.*key.*', 'key'),

    # Numbers and time
    (r'.*timeout.*', '30000'),
    (r'.*delay.*', '1000'),
    (r'.*duration.*', '1000'),
    (r'.*limit.*', '100'),
    (r'.*offset.*', '0'),
    (r'.*page.*', '1'),
    (r'.*size.*', '10'),
    (r'.*count.*', '10'),
    (r'.*max.*', '100'),
    (r'.*min.*', '0'),
    (r'.*date.*', '2024-01-01'),
    (r'.*time.*', '12:00:00'),

    # Misc
    (r'.*format.*', 'format-string'),
    (r'.*type.*', 'type'),
    (r'.*mode.*', 'mode'),
    (r'.*method.*', 'GET'),
    (r'.*status.*', 'active'),
    (r'.*code.*', 'code'),
    (r'.*value.*', 'value'),
]


def generate_placeholder(field_name: str, field_type: str) -> Optional[str]:
    """Generate a smart placeholder based on field name and type."""
    name_lower = field_name.lower()

    # Try pattern matching (first match wins)
    for pattern, placeholder in PLACEHOLDER_PATTERNS:
        if re.match(pattern, name_lower):
            return placeholder

    # Fallback based on type
    if field_type == 'string':
        # Generate generic placeholder from field name
        readable = field_name.replace('_', ' ').title()
        return f'Enter {readable}...'
    elif field_type == 'number':
        return '0'

    return None


def generate_label(field_name: str) -> str:
    """Generate a human-readable label from field name."""
    words = field_name.replace('_', ' ').split()
    return ' '.join(word.capitalize() for word in words)


def generate_description(field_name: str, field_type: str) -> str:
    """Generate a description from field name and type."""
    label = generate_label(field_name)

    if field_type == 'boolean':
        return f'Whether to {label.lower()}'
    elif field_type == 'select':
        return f'{label} option'
    elif field_type == 'array':
        return f'{label} list'
    elif field_type == 'object':
        return f'{label} data'
    elif field_type == 'number':
        return f'{label} value'
    else:
        return label


# ==============================================================================
# CATEGORY TYPES
# ==============================================================================

CATEGORY_TYPES = {
    'string': (['string'], ['string']),
    'array': (['array'], ['array']),
    'object': (['object'], ['object']),
    'number': (['number'], ['number']),
    'boolean': (['boolean'], ['boolean']),
    'math': (['number'], ['number']),
    'datetime': (['string', 'number'], ['string']),
    'file': (['string', 'file'], ['file', 'string']),
    'database': (['string', 'object'], ['array', 'object']),
    'api': (['object'], ['object']),
    'http': (['string', 'object'], ['object']),
    'browser': (['string'], ['page', 'object']),
    'element': (['element'], ['any']),
    'page': (['page'], ['any']),
    'data': (['any'], ['any']),
    'flow': (['any'], ['any']),
    'validate': (['string'], ['object']),
    'convert': (['string'], ['string']),
    'encode': (['string'], ['string']),
    'decode': (['string'], ['string']),
    'hash': (['string'], ['string']),
    'crypto': (['string'], ['string']),
    'image': (['file', 'string'], ['file', 'string']),
    'document': (['file', 'string'], ['object', 'string']),
    'notification': (['string', 'object'], ['object']),
    'ai': (['string', 'object'], ['string', 'object']),
    'format': (['any'], ['string']),
    'compare': (['any'], ['boolean']),
    'logic': (['any'], ['any']),
    'meta': (['any'], ['any']),
    'port': (['string', 'number'], ['boolean']),
    'test': (['any'], ['boolean']),
    'testing': (['any'], ['object']),
    'utility': (['any'], ['any']),
}


# ==============================================================================
# STATISTICS
# ==============================================================================

class Stats:
    """Track what was fixed."""
    def __init__(self):
        self.files_scanned = 0
        self.files_modified = 0
        self.missing_placeholder = 0
        self.missing_description = 0
        self.missing_label = 0
        self.missing_input_types = 0
        self.missing_output_types = 0
        self.output_missing_description = 0


# ==============================================================================
# CORE FIXING LOGIC
# ==============================================================================

def fix_module_file(file_path: Path, dry_run: bool, stats: Stats, verbose: bool) -> bool:
    """
    Fix a single module file.

    Returns True if file was modified (when not in dry-run mode).
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
    except Exception as e:
        if verbose:
            print(f"⚠️  Failed to read {file_path}: {e}")
        return False

    stats.files_scanned += 1

    # Extract module metadata for context
    module_id_match = re.search(r"module_id\s*=\s*['\"]([^'\"]+)['\"]", content)
    module_id = module_id_match.group(1) if module_id_match else file_path.stem

    category_match = re.search(r"category\s*=\s*['\"]([^'\"]+)['\"]", content)
    category = category_match.group(1) if category_match else None

    # Fix params_schema fields
    content = fix_schema_section(content, 'params_schema', False, stats)

    # Fix output_schema fields
    content = fix_schema_section(content, 'output_schema', True, stats)

    # Fix decorator-level types
    if category and category in CATEGORY_TYPES:
        content = fix_decorator_types(content, category, stats)

    # Save if modified
    if content != original_content:
        if dry_run:
            if verbose:
                print(f"📝 Would fix {file_path.name} ({module_id})")
            return False
        else:
            file_path.write_text(content, encoding='utf-8')
            stats.files_modified += 1
            if verbose:
                print(f"✅ Fixed {file_path.name} ({module_id})")
            return True

    return False


def fix_schema_section(content: str, schema_name: str, is_output: bool, stats: Stats) -> str:
    """
    Fix all fields in a schema section (params_schema or output_schema).

    Adds missing placeholder, description, label to each field dict.
    """
    # Match the schema section: schema_name={...}
    # This regex handles nested braces (one level)
    pattern = rf"{schema_name}\s*=\s*\{{([^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*)\}}"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return content

    schema_block = match.group(0)
    schema_content = match.group(1)

    # Find all field definitions: 'field_name': { ... }
    field_pattern = r"'([^']+)'\s*:\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}"

    def replace_field(field_match):
        field_name = field_match.group(1)
        field_content = field_match.group(2)

        # Extract field type
        type_match = re.search(r"'type'\s*:\s*'([^']+)'", field_content)
        field_type = type_match.group(1) if type_match else 'string'

        # Check what's missing
        has_placeholder = "'placeholder'" in field_content or '"placeholder"' in field_content
        has_description = "'description'" in field_content or '"description"' in field_content
        has_label = "'label'" in field_content or '"label"' in field_content

        additions = []

        if not is_output:
            # params_schema - add placeholder, description, label
            if not has_placeholder and field_type in ['string', 'number']:
                placeholder = generate_placeholder(field_name, field_type)
                if placeholder:
                    additions.append(('placeholder', placeholder))
                    stats.missing_placeholder += 1

            if not has_description:
                desc = generate_description(field_name, field_type)
                additions.append(('description', desc))
                stats.missing_description += 1

            if not has_label:
                label = generate_label(field_name)
                additions.append(('label', label))
                stats.missing_label += 1
        else:
            # output_schema - only add description
            if not has_description:
                desc = generate_description(field_name, field_type)
                additions.append(('description', desc))
                stats.output_missing_description += 1

        if not additions:
            return field_match.group(0)

        # Add missing properties before the closing brace
        # Find the last line before }
        lines = field_content.rstrip().split('\n')
        last_line = lines[-1].rstrip()

        # Ensure last line ends with comma
        if not last_line.endswith(','):
            field_content = field_content.rstrip() + ','

        # Add new properties (with proper indentation)
        for prop_name, prop_value in additions:
            # Escape single quotes in value
            escaped_value = prop_value.replace("'", "\\'")
            field_content += f"\n            '{prop_name}': '{escaped_value}',"

        return f"'{field_name}': {{{field_content}\n        }}"

    new_schema_content = re.sub(field_pattern, replace_field, schema_content)

    if new_schema_content != schema_content:
        new_schema_block = f"{schema_name}={{{new_schema_content}}}"
        return content.replace(schema_block, new_schema_block, 1)

    return content


def fix_decorator_types(content: str, category: str, stats: Stats) -> str:
    """Add missing input_types/output_types based on category."""
    input_types, output_types = CATEGORY_TYPES[category]

    # Check if input_types exists
    if 'input_types=' not in content:
        # Insert after category line
        pattern = rf"(category\s*=\s*['\"]{ re.escape(category)}['\"],?\s*\n)"
        replacement = rf"\1    input_types={input_types},\n"
        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            stats.missing_input_types += 1
            content = new_content

    # Check if output_types exists
    if 'output_types=' not in content:
        # Try to insert after input_types first, then after category
        if 'input_types=' in content:
            pattern = r"(input_types\s*=\s*\[[^\]]*\],?\s*\n)"
            replacement = rf"\1    output_types={output_types},\n"
        else:
            pattern = rf"(category\s*=\s*['\"]{ re.escape(category)}['\"],?\s*\n)"
            replacement = rf"\1    output_types={output_types},\n"

        new_content = re.sub(pattern, replacement, content)
        if new_content != content:
            stats.missing_output_types += 1
            content = new_content

    return content


# ==============================================================================
# FILE DISCOVERY
# ==============================================================================

def discover_module_files(base_path: Path) -> List[Path]:
    """Find all module files in the atomic directory."""
    atomic_path = base_path / 'src' / 'core' / 'modules' / 'atomic'

    if not atomic_path.exists():
        return []

    return sorted(
        p for p in atomic_path.rglob('*.py')
        if p.name != '__init__.py' and not p.name.startswith('test_')
    )


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Fix schema issues in flyto-core modules',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview all changes
  python scripts/fix_schema.py --dry-run --verbose

  # Fix all modules
  python scripts/fix_schema.py

  # Fix specific module
  python scripts/fix_schema.py --module-id string.uppercase --verbose
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying files')
    parser.add_argument('--module-id', metavar='ID',
                       help='Only fix specific module (e.g., string.uppercase)')
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed progress')
    args = parser.parse_args()

    # Find flyto-core root
    script_path = Path(__file__).resolve()
    core_root = script_path.parent.parent

    # Header
    print("=" * 70)
    print("🔧 Flyto Core Schema Fixer")
    print("=" * 70)
    print(f"📁 Root: {core_root}")
    print(f"🎯 Mode: {'DRY RUN (preview only)' if args.dry_run else 'LIVE (will modify files)'}")
    if args.module_id:
        print(f"🔍 Filter: {args.module_id}")
    print()

    # Discover modules
    module_files = discover_module_files(core_root)
    print(f"📦 Found {len(module_files)} module files")
    print()

    # Initialize stats
    stats = Stats()

    # Fix each module
    for file_path in module_files:
        # Filter by module_id if specified
        if args.module_id:
            try:
                source = file_path.read_text(encoding='utf-8')
                if f"module_id='{args.module_id}'" not in source and f'module_id="{args.module_id}"' not in source:
                    continue
            except Exception:
                continue

        fix_module_file(file_path, args.dry_run, stats, args.verbose)

    # Summary
    print()
    print("=" * 70)
    print("📊 Summary")
    print("=" * 70)
    print(f"Files scanned:                  {stats.files_scanned}")
    print(f"Files modified:                 {stats.files_modified}")
    print(f"Missing placeholders fixed:     {stats.missing_placeholder}")
    print(f"Missing descriptions fixed:     {stats.missing_description}")
    print(f"Missing labels fixed:           {stats.missing_label}")
    print(f"Missing input_types fixed:      {stats.missing_input_types}")
    print(f"Missing output_types fixed:     {stats.missing_output_types}")
    print(f"Output descriptions fixed:      {stats.output_missing_description}")
    print("=" * 70)

    if args.dry_run:
        print()
        print("⚠️  DRY RUN - No files were modified.")
        print("    Run without --dry-run to apply changes.")
    else:
        print()
        print("✅ Done! All schema issues have been fixed.")
        print("   Remember to commit your changes.")


if __name__ == '__main__':
    main()
