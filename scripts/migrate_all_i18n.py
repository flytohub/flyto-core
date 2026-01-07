#!/usr/bin/env python3
"""
migrate_all_i18n.py - Complete i18n migration for output_schema and params_schema

Usage:
    python scripts/migrate_all_i18n.py [--dry-run] [--verbose]

This script:
1. Scans ALL module directories (atomic, composite, third_party, integrations)
2. Adds description_key to output_schema fields
3. Adds description_key to params_schema fields
4. Handles nested structures (properties, items)
5. Preserves existing description as fallback
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
MODULES_DIRS = [
    PROJECT_ROOT / 'src' / 'core' / 'modules' / 'atomic',
    PROJECT_ROOT / 'src' / 'core' / 'modules' / 'composite',
    PROJECT_ROOT / 'src' / 'core' / 'modules' / 'third_party',
    PROJECT_ROOT / 'src' / 'core' / 'modules' / 'integrations',
]


def extract_module_id(content: str) -> Optional[str]:
    """Extract module_id from @register_module decorator."""
    # Pattern: @register_module("module.id" or module_id="module.id"
    patterns = [
        r'@register_module\s*\(\s*["\']([^"\']+)["\']',
        r'@register_module\s*\([^)]*module_id\s*=\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1)
    return None


def find_schema_block(content: str, schema_name: str) -> Optional[Tuple[int, int, str]]:
    """
    Find a schema block (output_schema or params_schema) in content.
    Returns (start_pos, end_pos, schema_text) or None.
    """
    # Find schema_name={
    pattern = rf'{schema_name}\s*=\s*\{{'
    match = re.search(pattern, content)
    if not match:
        return None

    start_pos = match.start()
    brace_start = match.end() - 1  # Position of opening brace

    # Find matching closing brace
    brace_count = 1
    pos = brace_start + 1

    while pos < len(content) and brace_count > 0:
        if content[pos] == '{':
            brace_count += 1
        elif content[pos] == '}':
            brace_count -= 1
        pos += 1

    if brace_count != 0:
        return None

    end_pos = pos
    schema_text = content[start_pos:end_pos]
    return (start_pos, end_pos, schema_text)


def add_description_key_to_field(
    field_text: str,
    module_id: str,
    schema_type: str,
    field_name: str,
    prefix: str = ""
) -> Tuple[str, int]:
    """
    Add description_key to a field definition if it has description but no description_key.
    Returns (modified_text, keys_added_count).
    """
    keys_added = 0

    # Check if field has description but not description_key
    has_description = re.search(r"['\"]description['\"]\s*:", field_text)
    has_description_key = re.search(r"['\"]description_key['\"]\s*:", field_text)

    if has_description and not has_description_key:
        # Build the key path
        if prefix:
            key = f"modules.{module_id}.{schema_type}.{prefix}.{field_name}.description"
        else:
            key = f"modules.{module_id}.{schema_type}.{field_name}.description"

        # Find the description line and add description_key after it
        desc_match = re.search(
            r"(['\"])description\1\s*:\s*['\"]([^'\"]*)['\"](\s*,?)",
            field_text
        )
        if desc_match:
            # Add description_key after description
            old_text = desc_match.group(0)
            quote = desc_match.group(1)
            comma = desc_match.group(3)
            if not comma.strip().endswith(','):
                new_text = f"{old_text.rstrip(',')},\n                {quote}description_key{quote}: {quote}{key}{quote}"
            else:
                new_text = f"{old_text}\n                {quote}description_key{quote}: {quote}{key}{quote},"
            field_text = field_text.replace(old_text, new_text, 1)
            keys_added += 1

    return field_text, keys_added


def process_schema(schema_text: str, module_id: str, schema_type: str) -> Tuple[str, int]:
    """
    Process a schema block and add description_key to all fields.
    Returns (modified_schema_text, keys_added_count).
    """
    total_keys_added = 0
    result = schema_text

    # Find all top-level fields: 'field_name': {
    field_pattern = r"['\"](\w+)['\"]\s*:\s*\{"

    # Process each field
    for match in re.finditer(field_pattern, schema_text):
        field_name = match.group(1)
        field_start = match.start()

        # Find the matching closing brace for this field
        brace_start = schema_text.find('{', field_start)
        if brace_start == -1:
            continue

        brace_count = 1
        pos = brace_start + 1
        while pos < len(schema_text) and brace_count > 0:
            if schema_text[pos] == '{':
                brace_count += 1
            elif schema_text[pos] == '}':
                brace_count -= 1
            pos += 1

        field_end = pos
        field_text = schema_text[field_start:field_end]

        # Add description_key to this field
        new_field_text, keys_added = add_description_key_to_field(
            field_text, module_id, schema_type, field_name
        )
        total_keys_added += keys_added

        if new_field_text != field_text:
            result = result.replace(field_text, new_field_text, 1)

        # Check for nested 'properties'
        if "'properties'" in field_text or '"properties"' in field_text:
            # Find properties block
            props_match = re.search(r"['\"]properties['\"]\s*:\s*\{", field_text)
            if props_match:
                # Process nested properties
                props_start = props_match.end() - 1
                props_brace_count = 1
                props_pos = props_start + 1

                while props_pos < len(field_text) and props_brace_count > 0:
                    if field_text[props_pos] == '{':
                        props_brace_count += 1
                    elif field_text[props_pos] == '}':
                        props_brace_count -= 1
                    props_pos += 1

                props_text = field_text[props_start:props_pos]

                # Find nested fields in properties
                for nested_match in re.finditer(field_pattern, props_text):
                    nested_name = nested_match.group(1)
                    nested_start = nested_match.start()

                    # Find nested field bounds
                    nested_brace = props_text.find('{', nested_start)
                    if nested_brace == -1:
                        continue

                    nested_brace_count = 1
                    nested_pos = nested_brace + 1
                    while nested_pos < len(props_text) and nested_brace_count > 0:
                        if props_text[nested_pos] == '{':
                            nested_brace_count += 1
                        elif props_text[nested_pos] == '}':
                            nested_brace_count -= 1
                        nested_pos += 1

                    nested_text = props_text[nested_start:nested_pos]

                    # Add description_key with nested path
                    new_nested_text, nested_keys = add_description_key_to_field(
                        nested_text, module_id, schema_type, nested_name,
                        prefix=f"{field_name}.properties"
                    )
                    total_keys_added += nested_keys

                    if new_nested_text != nested_text:
                        result = result.replace(nested_text, new_nested_text, 1)

    return result, total_keys_added


def process_file(file_path: Path, dry_run: bool = False, verbose: bool = False) -> Dict:
    """Process a single file and add description_key to schemas."""
    stats = {
        'output_schema_keys': 0,
        'params_schema_keys': 0,
        'modified': False,
        'errors': []
    }

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        stats['errors'].append(f"Read error: {e}")
        return stats

    # Check if this is a module file
    if '@register_module' not in content:
        return stats

    # Extract module_id
    module_id = extract_module_id(content)
    if not module_id:
        stats['errors'].append("Could not extract module_id")
        return stats

    new_content = content
    total_keys = 0

    # Process output_schema
    output_result = find_schema_block(content, 'output_schema')
    if output_result:
        start, end, schema_text = output_result
        new_schema, keys_added = process_schema(schema_text, module_id, 'output')
        stats['output_schema_keys'] = keys_added
        total_keys += keys_added
        if new_schema != schema_text:
            new_content = new_content.replace(schema_text, new_schema, 1)

    # Process params_schema
    params_result = find_schema_block(new_content, 'params_schema')
    if params_result:
        start, end, schema_text = params_result
        new_schema, keys_added = process_schema(schema_text, module_id, 'params')
        stats['params_schema_keys'] = keys_added
        total_keys += keys_added
        if new_schema != schema_text:
            new_content = new_content.replace(schema_text, new_schema, 1)

    # Write changes
    if new_content != content:
        stats['modified'] = True
        if not dry_run:
            file_path.write_text(new_content, encoding='utf-8')

    return stats


def main():
    parser = argparse.ArgumentParser(description='Complete i18n migration')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without modifying')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("=" * 60)
    print("i18n Migration: output_schema + params_schema")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    total_files = 0
    modified_files = 0
    total_output_keys = 0
    total_params_keys = 0
    errors = []

    for modules_dir in MODULES_DIRS:
        if not modules_dir.exists():
            continue

        print(f"\nScanning: {modules_dir.relative_to(PROJECT_ROOT)}")
        print("-" * 40)

        for py_file in sorted(modules_dir.rglob('*.py')):
            if '__pycache__' in str(py_file):
                continue
            if py_file.name.startswith('_'):
                continue

            total_files += 1
            stats = process_file(py_file, args.dry_run, args.verbose)

            if stats['errors']:
                for err in stats['errors']:
                    errors.append(f"{py_file}: {err}")

            if stats['modified'] or stats['output_schema_keys'] > 0 or stats['params_schema_keys'] > 0:
                rel_path = py_file.relative_to(PROJECT_ROOT)
                output_info = f"output: +{stats['output_schema_keys']}" if stats['output_schema_keys'] else ""
                params_info = f"params: +{stats['params_schema_keys']}" if stats['params_schema_keys'] else ""
                info = ", ".join(filter(None, [output_info, params_info]))
                if info:
                    print(f"  {rel_path}: {info}")
                    modified_files += 1

            total_output_keys += stats['output_schema_keys']
            total_params_keys += stats['params_schema_keys']

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Files scanned:    {total_files}")
    print(f"Files modified:   {modified_files}")
    print(f"Output keys:      +{total_output_keys}")
    print(f"Params keys:      +{total_params_keys}")
    print(f"Total new keys:   +{total_output_keys + total_params_keys}")

    if errors:
        print()
        print("Errors:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

    if args.dry_run:
        print()
        print("Run without --dry-run to apply changes")

    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
