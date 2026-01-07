#!/usr/bin/env python3
"""
migrate_output_schema_i18n.py - Add description_key to output_schema fields

Usage:
    python scripts/migrate_output_schema_i18n.py [--dry-run] [--verbose]

Options:
    --dry-run    Show what would be changed without modifying files
    --verbose    Print detailed information about changes

This script:
1. Scans all module files with @register_module decorators
2. Finds output_schema definitions
3. Adds description_key to each field (if not present)
4. Preserves existing description as fallback
"""

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
MODULES_DIR = PROJECT_ROOT / 'src' / 'core' / 'modules' / 'atomic'


def extract_module_id(content: str, decorator_line: int) -> Optional[str]:
    """Extract module_id from a register_module decorator."""
    # Find the decorator and extract module_id
    lines = content.split('\n')

    # Look for module_id in lines after decorator
    in_decorator = False
    paren_count = 0

    for i, line in enumerate(lines[decorator_line - 1:], start=decorator_line):
        if '@register_module' in line:
            in_decorator = True

        if in_decorator:
            paren_count += line.count('(') - line.count(')')

            # Look for module_id
            match = re.search(r"module_id\s*=\s*['\"]([^'\"]+)['\"]", line)
            if match:
                return match.group(1)

            if paren_count <= 0 and in_decorator and '(' in ''.join(lines[decorator_line - 1:i]):
                break

    return None


def find_output_schema_in_decorator(content: str, decorator_line: int) -> Optional[Tuple[int, int, str]]:
    """Find output_schema definition in a decorator and return (start_line, end_line, schema_text)."""
    lines = content.split('\n')

    # Find where output_schema starts
    in_decorator = False
    in_output_schema = False
    brace_count = 0
    schema_start_line = None
    schema_lines = []

    for i, line in enumerate(lines[decorator_line - 1:], start=decorator_line):
        if '@register_module' in line:
            in_decorator = True

        if in_decorator and not in_output_schema:
            if 'output_schema=' in line or 'output_schema =' in line:
                in_output_schema = True
                schema_start_line = i
                # Get the part after output_schema=
                idx = line.find('output_schema')
                rest = line[idx:]
                schema_lines.append(rest)
                brace_count = rest.count('{') - rest.count('}')
                if brace_count == 0 and '{' in rest:
                    return (schema_start_line, i, '\n'.join(schema_lines))
                continue

        if in_output_schema:
            schema_lines.append(line)
            brace_count += line.count('{') - line.count('}')

            if brace_count <= 0:
                return (schema_start_line, i, '\n'.join(schema_lines))

    return None


def parse_output_schema(schema_text: str) -> Optional[Dict]:
    """Parse output_schema text to extract field names."""
    # Try to extract just the dict part
    match = re.search(r'output_schema\s*=\s*(\{[\s\S]*\})', schema_text)
    if not match:
        return None

    dict_text = match.group(1)

    # Try to parse as Python dict (may fail for complex cases)
    try:
        # Clean up the text for eval
        # Replace single quotes with double quotes for JSON compatibility
        clean = dict_text.replace("'", '"')
        import json
        return json.loads(clean)
    except:
        pass

    # Fallback: use regex to extract field names
    fields = {}
    # Match patterns like 'field_name': {
    for m in re.finditer(r"['\"](\w+)['\"]\s*:\s*\{", dict_text):
        fields[m.group(1)] = {}

    return fields if fields else None


def add_description_keys_to_schema(schema_text: str, module_id: str) -> str:
    """Add description_key to each field in output_schema."""
    lines = schema_text.split('\n')
    result_lines = []
    current_field = None
    field_indent = None
    has_description_key = False

    for i, line in enumerate(lines):
        # Detect field definition like 'status': {
        field_match = re.match(r"(\s*)['\"](\w+)['\"]\s*:\s*\{", line)
        if field_match:
            # Check if previous field needs description_key
            if current_field and not has_description_key and field_indent:
                # Insert description_key before this line
                key = f"modules.{module_id}.output.{current_field}.description"
                result_lines.append(f"{field_indent}    'description_key': '{key}',")

            current_field = field_match.group(2)
            field_indent = field_match.group(1)
            has_description_key = False
            result_lines.append(line)
            continue

        # Check if this line has description_key
        if current_field and 'description_key' in line:
            has_description_key = True

        # Detect end of field (closing brace at same or lower indent)
        if current_field:
            close_match = re.match(r"(\s*)\}", line)
            if close_match:
                close_indent = len(close_match.group(1))
                field_expected_indent = len(field_indent) + 4 if field_indent else 4

                # If this closes the field
                if close_indent <= field_expected_indent:
                    if not has_description_key:
                        # Insert description_key before closing brace
                        key = f"modules.{module_id}.output.{current_field}.description"
                        # Add proper indentation
                        desc_indent = ' ' * (close_indent + 4)
                        # Insert before the closing brace
                        result_lines.append(f"{desc_indent}'description_key': '{key}'")
                    current_field = None
                    has_description_key = False

        result_lines.append(line)

    return '\n'.join(result_lines)


def process_file(file_path: Path, dry_run: bool = False, verbose: bool = False) -> List[str]:
    """Process a single file and add description_key to output_schema fields."""
    changes = []

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return [f"Error reading {file_path}: {e}"]

    # Parse AST to find decorators
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [f"Syntax error in {file_path}"]

    modified = False
    new_content = content

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    func = decorator.func
                    if isinstance(func, ast.Name) and func.id == 'register_module':
                        # Extract module_id
                        module_id = extract_module_id(content, decorator.lineno)
                        if not module_id:
                            continue

                        # Find output_schema
                        schema_info = find_output_schema_in_decorator(content, decorator.lineno)
                        if not schema_info:
                            continue

                        start_line, end_line, schema_text = schema_info

                        # Check if already has description_key
                        if 'description_key' in schema_text:
                            if verbose:
                                changes.append(f"  {module_id}: already has description_key")
                            continue

                        # Add description_key
                        new_schema = add_description_keys_to_schema(schema_text, module_id)

                        if new_schema != schema_text:
                            changes.append(f"  {module_id}: added description_key to output_schema")

                            # Replace in content
                            lines = new_content.split('\n')
                            before = lines[:start_line - 1]
                            after = lines[end_line:]

                            new_content = '\n'.join(before) + '\n' + new_schema + '\n' + '\n'.join(after)
                            modified = True

    if modified and not dry_run:
        file_path.write_text(new_content, encoding='utf-8')

    return changes


def main():
    parser = argparse.ArgumentParser(description='Add description_key to output_schema fields')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without modifying')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("Scanning modules for output_schema migration...")
    print(f"Modules directory: {MODULES_DIR}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    total_changes = 0
    files_modified = 0

    for py_file in sorted(MODULES_DIR.rglob('*.py')):
        if '__pycache__' in str(py_file):
            continue
        if py_file.name.startswith('_'):
            continue

        changes = process_file(py_file, args.dry_run, args.verbose)

        if changes:
            rel_path = py_file.relative_to(PROJECT_ROOT)
            print(f"{rel_path}:")
            for change in changes:
                print(change)
            files_modified += 1
            total_changes += len(changes)

    print()
    print(f"{'Would modify' if args.dry_run else 'Modified'}: {files_modified} files")
    print(f"Total changes: {total_changes}")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes")

    return 0


if __name__ == '__main__':
    sys.exit(main())
