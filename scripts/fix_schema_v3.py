#!/usr/bin/env python3
"""
Schema Fixer v3 - Safe per-field patching with AST rollback.

Each change is verified with ast.parse(). If a change breaks syntax, it's rolled back.

Usage:
    python scripts/fix_schema_v3.py --dry-run
    python scripts/fix_schema_v3.py
"""
import ast
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
CORE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CORE_ROOT / 'src'))

# Sensible placeholder defaults
PLACEHOLDER_MAP = {
    'url': 'https://example.com',
    'base_url': 'https://api.example.com',
    'ollama_url': 'http://localhost:11434',
    'api_key': 'sk-...',
    'auth_token': 'Bearer your-token',
    'token': 'your-token',
    'secret': 'your-secret',
    'password': '********',
    'username': 'username',
    'email': 'user@example.com',
    'host': 'localhost',
    'port': '8080',
    'model': 'gpt-4o',
    'prompt': 'Enter your prompt...',
    'system_prompt': 'You are a helpful assistant.',
    'system_message': 'You are a helpful assistant.',
    'system': 'You are a helpful assistant.',
    'html': '<html><body>content</body></html>',
    'text': 'Enter text...',
    'content': 'Enter content...',
    'message': 'Your message here',
    'body': 'Request body content',
    'query': 'SELECT * FROM table',
    'sql': 'SELECT * FROM table',
    'selector': '#element or .class',
    'name': 'my-name',
    'title': 'Title',
    'description': 'Description text',
    'comment': 'Your comment',
    'file_path': '/path/to/file',
    'path': '/path/to/file',
    'input_path': '/path/to/input',
    'output_path': '/path/to/output',
    'output_dir': '/path/to/output',
    'save_path': '/path/to/save',
    'directory': '/path/to/directory',
    'source': '/path/to/source',
    'destination': '/path/to/destination',
    'bucket': 'my-bucket',
    'region': 'us-east-1',
    'database': 'mydb',
    'database_id': 'database-id',
    'table_name': 'my_table',
    'collection': 'my_collection',
    'key': 'my-key',
    'value': 'value',
    'id': 'unique-id',
    'base_id': 'app12345',
    'account_id': 'account-id',
    'project_id': 'project-id',
    'repo': 'username/repo',
    'owner': 'username',
    'branch': 'main',
    'pattern': '^pattern$',
    'regex': '^regex$',
    'format': 'json',
    'template': 'Hello {{name}}!',
    'separator': ',',
    'delimiter': ',',
    'prefix': 'prefix-',
    'suffix': '-suffix',
    'phone': '+1234567890',
    'subject': 'Email Subject',
    'webhook_url': 'https://example.com/webhook',
    'endpoint': '/api/v1/resource',
    'context': 'Additional context...',
    'goal': 'Describe the goal...',
    'input': 'Input data...',
    'code': 'print("hello")',
    'script': 'console.log("hello")',
    'expression': '1 + 1',
    'command': 'echo hello',
    'header': 'Header text',
    'footer': 'Footer text',
    'header_name': 'X-Custom-Header',
    'prompt_text': 'Enter text here',
    'images_output_dir': '/path/to/images',
    'method': 'GET',
    'content_type': 'application/json',
}

DESCRIPTION_MAP = {
    'url': 'Target URL',
    'api_key': 'API key for authentication',
    'auth_token': 'Authentication token',
    'model': 'AI model identifier',
    'prompt': 'Prompt text for AI',
    'html': 'HTML content to process',
    'text': 'Text content',
    'file_path': 'Path to the file',
    'path': 'File or directory path',
    'query': 'Query string',
    'selector': 'CSS selector or element identifier',
    'name': 'Name identifier',
    'header_name': 'HTTP header name',
    'headers': 'HTTP request headers',
    'timeout': 'Maximum time to wait in milliseconds',
    'include_context': 'Whether to include execution context',
    'trigger_type': 'Type of trigger event',
    'operation': 'Operation to perform',
    'context': 'Additional context data',
}


def get_placeholder(field_name: str) -> str:
    name_lower = field_name.lower()
    if name_lower in PLACEHOLDER_MAP:
        return PLACEHOLDER_MAP[name_lower]
    for key, val in PLACEHOLDER_MAP.items():
        if key in name_lower:
            return val
    readable = field_name.replace('_', ' ').title()
    return f'Enter {readable}...'


def get_description(field_name: str) -> str:
    name_lower = field_name.lower()
    if name_lower in DESCRIPTION_MAP:
        return DESCRIPTION_MAP[name_lower]
    for key, val in DESCRIPTION_MAP.items():
        if key in name_lower:
            return val
    readable = field_name.replace('_', ' ')
    return f'{readable} parameter'


def get_issues() -> List[Dict]:
    from core.modules.registry import ModuleRegistry
    import core.modules.atomic  # noqa: F401

    issues = []
    for mid in sorted(ModuleRegistry._modules.keys()):
        meta = ModuleRegistry.get_metadata(mid)
        params = meta.get('params_schema')
        if not params or not isinstance(params, dict):
            continue
        for fkey, fdef in params.items():
            if fkey.startswith('__') or not isinstance(fdef, dict):
                continue
            ftype = fdef.get('type', 'string')
            has_options = 'options' in fdef or 'enum' in fdef
            if 'description' not in fdef:
                issues.append({
                    'module_id': mid, 'field': fkey,
                    'issue': 'Q013', 'fix_value': get_description(fkey),
                })
            if ftype in ('string', 'text') and not has_options and 'placeholder' not in fdef:
                issues.append({
                    'module_id': mid, 'field': fkey,
                    'issue': 'Q014', 'fix_value': get_placeholder(fkey),
                })
    return issues


def find_module_file(module_id: str) -> Optional[Path]:
    atomic_dir = CORE_ROOT / 'src' / 'core' / 'modules' / 'atomic'
    for py_file in atomic_dir.rglob('*.py'):
        if py_file.name == '__init__.py':
            continue
        try:
            content = py_file.read_text(encoding='utf-8')
        except Exception:
            continue
        if f"'{module_id}'" in content or f'"{module_id}"' in content:
            if 'module_id' in content or '@register_module' in content:
                return py_file
    return None


def safe_add_to_field_call(content: str, field_name: str, prop: str, value: str) -> Optional[str]:
    """Add a kwarg to a field() call. Returns new content or None if not found."""
    # Find field('field_name', ...) — careful to not match inside strings
    escaped = re.escape(field_name)
    # Look for the field() call start
    pattern = rf"field\(\s*['\"]({escaped})['\"]"
    for m in re.finditer(pattern, content):
        start = m.start()
        # Find the matching closing paren by counting nesting
        depth = 0
        i = start
        field_start = None
        field_end = None
        in_string = None
        escape_next = False

        while i < len(content):
            ch = content[i]
            if escape_next:
                escape_next = False
                i += 1
                continue
            if ch == '\\':
                escape_next = True
                i += 1
                continue
            if in_string:
                if ch == in_string:
                    in_string = None
                i += 1
                continue
            if ch in ("'", '"'):
                in_string = ch
                i += 1
                continue
            if ch == '(':
                if depth == 0:
                    field_start = i
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    field_end = i
                    break
            i += 1

        if field_end is None:
            continue

        field_body = content[field_start:field_end + 1]
        if f"{prop}=" in field_body or f"'{prop}'" in field_body:
            return None  # already has it

        # Insert before the closing paren
        # Find the last non-whitespace before closing paren
        before_close = content[field_start + 1:field_end].rstrip()
        if not before_close.endswith(','):
            insert_text = ','
        else:
            insert_text = ''

        # Detect indentation from the field body
        indent = '            '
        for line in content[field_start:field_end].split('\n')[1:]:
            stripped = line.lstrip()
            if stripped and '=' in stripped:
                indent = line[:len(line) - len(stripped)]
                break

        escaped_val = value.replace("'", "\\'")
        insert_text += f"\n{indent}{prop}='{escaped_val}',"

        # Insert before the closing paren
        new_content = content[:field_end] + insert_text + '\n' + indent.rstrip('    ') + content[field_end:]
        return new_content

    return None


def safe_add_to_dict_field(content: str, field_name: str, prop: str, value: str) -> Optional[str]:
    """Add a property to a dict-style field. Returns new content or None if not found."""
    escaped = re.escape(field_name)
    # Pattern: 'field_name': {
    pattern = rf"['\"]({escaped})['\"]:\s*\{{"
    for m in re.finditer(pattern, content):
        start = m.start()
        brace_start = content.index('{', m.start() + len(field_name))

        # Find matching closing brace by counting
        depth = 0
        i = brace_start
        brace_end = None
        in_string = None
        escape_next = False

        while i < len(content):
            ch = content[i]
            if escape_next:
                escape_next = False
                i += 1
                continue
            if ch == '\\':
                escape_next = True
                i += 1
                continue
            if in_string:
                if ch == in_string:
                    in_string = None
                i += 1
                continue
            if ch in ("'", '"'):
                in_string = ch
                i += 1
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break
            i += 1

        if brace_end is None:
            continue

        field_body = content[brace_start:brace_end + 1]
        if f"'{prop}'" in field_body or f'"{prop}"' in field_body:
            return None  # already has it

        # Detect indentation
        indent = '            '
        for line in content[brace_start:brace_end].split('\n')[1:]:
            stripped = line.lstrip()
            if stripped.startswith("'") or stripped.startswith('"'):
                indent = line[:len(line) - len(stripped)]
                break

        escaped_val = value.replace("'", "\\'")

        # Find position just before closing brace
        before_close = content[brace_start + 1:brace_end].rstrip()
        if before_close and not before_close.endswith(','):
            comma = ','
        else:
            comma = ''

        # Find the last content line before closing brace
        insert_pos = brace_end
        new_line = f"{comma}\n{indent}'{prop}': '{escaped_val}',"
        new_content = content[:insert_pos] + new_line + '\n' + content[insert_pos:]
        return new_content

    return None


def apply_fix(file_path: Path, field_name: str, issue: str, fix_value: str, dry_run: bool) -> bool:
    """Apply a single fix with AST validation. Returns True if fixed."""
    content = file_path.read_text(encoding='utf-8')
    original = content

    prop = 'description' if issue == 'Q013' else 'placeholder'

    # Try field() call first
    result = safe_add_to_field_call(content, field_name, prop, fix_value)
    if result is None:
        # Try dict-style
        result = safe_add_to_dict_field(content, field_name, prop, fix_value)

    if result is None or result == original:
        return False

    # AST validation - CRITICAL safety check
    try:
        ast.parse(result)
    except SyntaxError:
        return False  # Rollback - don't apply broken changes

    if not dry_run:
        file_path.write_text(result, encoding='utf-8')
    return True


def main():
    parser = argparse.ArgumentParser(description='Fix schema quality issues (safe)')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    print("=" * 60)
    print("Schema Fixer v3 - Safe (AST-validated)")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    print("Loading modules...")
    issues = get_issues()
    q013 = [i for i in issues if i['issue'] == 'Q013']
    q014 = [i for i in issues if i['issue'] == 'Q014']
    print(f"Found {len(issues)} issues (Q013: {len(q013)}, Q014: {len(q014)})")
    print()

    by_module = {}
    for issue in issues:
        mid = issue['module_id']
        by_module.setdefault(mid, []).append(issue)

    fixed = 0
    skipped = 0
    file_cache = {}

    for mid in sorted(by_module.keys()):
        if mid not in file_cache:
            file_cache[mid] = find_module_file(mid)
        file_path = file_cache[mid]

        if not file_path:
            skipped += len(by_module[mid])
            if args.verbose:
                print(f"  SKIP {mid}: file not found")
            continue

        for issue in by_module[mid]:
            ok = apply_fix(file_path, issue['field'], issue['issue'], issue['fix_value'], args.dry_run)
            if ok:
                fixed += 1
                if args.verbose:
                    print(f"  FIX  {mid}.{issue['field']}: +{issue['issue']}")
            else:
                skipped += 1
                if args.verbose:
                    print(f"  SKIP {mid}.{issue['field']}: no match or AST fail")

    print()
    print("=" * 60)
    print(f"Fixed:   {fixed}")
    print(f"Skipped: {skipped}")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN - no files modified.")


if __name__ == '__main__':
    main()
