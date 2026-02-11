#!/usr/bin/env python3
"""
Schema Fixer v2 - Fix remaining schema quality issues (Q013/Q014)

Uses the runtime quality validator to identify issues, then patches source files.
Handles both dict-style params_schema AND field()/compose() style schemas.

Usage:
    python scripts/fix_schema_v2.py --dry-run
    python scripts/fix_schema_v2.py
"""
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Setup path
SCRIPT_DIR = Path(__file__).resolve().parent
CORE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CORE_ROOT / 'src'))

# Placeholder defaults by field name pattern
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
    'hostname': 'localhost',
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
    'container': 'my-container',
    'region': 'us-east-1',
    'database': 'mydb',
    'database_id': 'database-id',
    'table_name': 'my_table',
    'collection': 'my_collection',
    'table': 'table_name',
    'index': 'index_name',
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
    'format': 'format-string',
    'template': 'Hello {{name}}!',
    'separator': ',',
    'delimiter': ',',
    'prefix': 'prefix-',
    'suffix': '-suffix',
    'from_number': '+1234567890',
    'to_number': '+1234567890',
    'phone': '+1234567890',
    'subject': 'Email Subject',
    'webhook_url': 'https://example.com/webhook',
    'callback_url': 'https://example.com/callback',
    'redirect_url': 'https://example.com/redirect',
    'endpoint': '/api/v1/resource',
    'context': 'Additional context...',
    'goal': 'Describe the goal...',
    'input': 'Input data...',
    'code': 'print("hello")',
    'script': 'console.log("hello")',
    'expression': '1 + 1',
    'command': 'echo hello',
    'pages': '1-5',
    'ruleset_path': '/path/to/ruleset.yaml',
    'detail': 'Details here...',
    'comparison_type': 'visual',
    'analysis_type': 'full',
    'output_format': 'json',
    'images_output_dir': '/path/to/images',
    'header_name': 'X-Custom-Header',
    'user_agent': 'Mozilla/5.0...',
    'proxy': 'http://proxy:8080',
    'prompt_text': 'Enter text here',
    'frame_name': 'frame-name',
    'page_url': 'https://example.com/page',
}

# Description defaults by field name pattern
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
    'connection_string': 'Database connection string',
    'base_url': 'Base URL for API requests',
    'context': 'Additional context data',
    'original': 'Original content for comparison',
    'modified': 'Modified content for comparison',
    'context_lines': 'Number of context lines around changes',
    'filename': 'Name of the file',
    'old_string': 'Text to find and replace',
    'new_string': 'Replacement text',
    'replace_all': 'Whether to replace all occurrences',
    'trigger_type': 'Type of trigger event',
    'include_context': 'Whether to include execution context',
    'operation': 'Operation to perform',
}


def get_placeholder(field_name: str) -> str:
    """Get a sensible placeholder for a field name."""
    name_lower = field_name.lower()

    # Exact match
    if name_lower in PLACEHOLDER_MAP:
        return PLACEHOLDER_MAP[name_lower]

    # Partial match
    for key, val in PLACEHOLDER_MAP.items():
        if key in name_lower:
            return val

    # Fallback
    readable = field_name.replace('_', ' ').title()
    return f'Enter {readable}...'


def get_description(field_name: str) -> str:
    """Get a sensible description for a field name."""
    name_lower = field_name.lower()

    if name_lower in DESCRIPTION_MAP:
        return DESCRIPTION_MAP[name_lower]

    for key, val in DESCRIPTION_MAP.items():
        if key in name_lower:
            return val

    readable = field_name.replace('_', ' ').title()
    return f'{readable} parameter'


def get_issues() -> List[Dict[str, str]]:
    """Run quality validator and collect Q013/Q014 issues."""
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

            # Q013: missing description
            if 'description' not in fdef:
                issues.append({
                    'module_id': mid,
                    'field': fkey,
                    'issue': 'Q013',
                    'fix_value': get_description(fkey),
                })

            # Q014: string without placeholder (skip selects)
            if ftype in ('string', 'text') and not has_options and 'placeholder' not in fdef:
                issues.append({
                    'module_id': mid,
                    'field': fkey,
                    'issue': 'Q014',
                    'fix_value': get_placeholder(fkey),
                })

    return issues


def find_module_file(module_id: str) -> Optional[Path]:
    """Find the source file for a module_id."""
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


def fix_dict_field(content: str, field_name: str, prop_name: str, prop_value: str) -> str:
    """Add a property to a dict-style field definition.

    Matches: 'field_name': { ... } and adds 'prop_name': 'prop_value'
    """
    # Pattern: 'field_name': {<anything>}
    escaped_field = re.escape(field_name)
    pattern = rf"('{escaped_field}'\s*:\s*\{{)([^}}]*?)(\}})"

    def replacer(m):
        prefix = m.group(1)
        body = m.group(2)
        suffix = m.group(3)

        # Skip if already has the property
        if f"'{prop_name}'" in body or f'"{prop_name}"' in body:
            return m.group(0)

        # Add property before closing brace
        body_stripped = body.rstrip()
        if not body_stripped.endswith(','):
            body_stripped += ','
        # Detect indentation
        indent = '            '
        for line in body.split('\n'):
            stripped = line.lstrip()
            if stripped.startswith("'") or stripped.startswith('"'):
                indent = line[:len(line) - len(stripped)]
                break

        escaped_val = prop_value.replace("'", "\\'")
        body_stripped += f"\n{indent}'{prop_name}': '{escaped_val}',"
        return prefix + body_stripped + '\n' + indent.rstrip('    ') + suffix

    return re.sub(pattern, replacer, content, count=1, flags=re.DOTALL)


def fix_field_call(content: str, field_name: str, prop_name: str, prop_value: str) -> str:
    """Add a kwarg to a field() call.

    Matches: field('field_name', ...) or field(key, ...) where key='field_name'
    and adds prop_name='prop_value' before the closing paren.
    """
    # Skip if property already exists in the field() call context
    if f"{prop_name}='" in content or f'{prop_name}="' in content:
        # Need to check within the specific field() call for this field_name
        pass

    escaped_field = re.escape(field_name)

    # Pattern 1: field('field_name', ...)
    pattern = rf"(field\(\s*'{escaped_field}'\s*,)(.*?)(\s*\))"

    def replacer(m):
        prefix = m.group(1)
        body = m.group(2)
        suffix = m.group(3)

        if f"{prop_name}=" in body:
            return m.group(0)

        body_stripped = body.rstrip()
        if not body_stripped.endswith(','):
            body_stripped += ','

        # Detect indentation
        indent = '        '
        for line in body.split('\n'):
            stripped = line.lstrip()
            if stripped and '=' in stripped:
                indent = line[:len(line) - len(stripped)]
                break

        escaped_val = prop_value.replace("'", "\\'")
        body_stripped += f"\n{indent}{prop_name}='{escaped_val}',"
        return prefix + body_stripped + suffix

    new_content = re.sub(pattern, replacer, content, count=1, flags=re.DOTALL)
    if new_content != content:
        return new_content

    # Pattern 2: field with key as variable default matching field_name
    # e.g., key: str = "field_name" ... return field(key, ...)
    # This is for presets - handled separately
    return content


def apply_fix(file_path: Path, field_name: str, issue: str, fix_value: str, dry_run: bool) -> bool:
    """Apply a single fix to a file. Returns True if fixed."""
    content = file_path.read_text(encoding='utf-8')
    original = content

    prop_name = 'description' if issue == 'Q013' else 'placeholder'

    # Try dict-style first
    content = fix_dict_field(content, field_name, prop_name, fix_value)

    # Try field() call style
    if content == original:
        content = fix_field_call(content, field_name, prop_name, fix_value)

    if content != original:
        if not dry_run:
            file_path.write_text(content, encoding='utf-8')
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description='Fix schema quality issues (Q013/Q014)')
    parser.add_argument('--dry-run', action='store_true', help='Preview without modifying')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show details')
    args = parser.parse_args()

    print("=" * 70)
    print("Schema Fixer v2 - Q013/Q014 Issues")
    print("=" * 70)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    # Collect issues from runtime
    print("Loading modules and scanning...")
    issues = get_issues()
    print(f"Found {len(issues)} issues")

    q013 = [i for i in issues if i['issue'] == 'Q013']
    q014 = [i for i in issues if i['issue'] == 'Q014']
    print(f"  Q013 (missing description): {len(q013)}")
    print(f"  Q014 (missing placeholder): {len(q014)}")
    print()

    # Group by module
    by_module = {}
    for issue in issues:
        mid = issue['module_id']
        if mid not in by_module:
            by_module[mid] = []
        by_module[mid].append(issue)

    # Fix each module
    fixed = 0
    skipped = 0
    file_cache = {}

    for mid in sorted(by_module.keys()):
        module_issues = by_module[mid]

        # Find source file
        if mid not in file_cache:
            file_cache[mid] = find_module_file(mid)
        file_path = file_cache[mid]

        if not file_path:
            if args.verbose:
                print(f"  SKIP {mid}: source file not found")
            skipped += len(module_issues)
            continue

        for issue in module_issues:
            ok = apply_fix(
                file_path,
                issue['field'],
                issue['issue'],
                issue['fix_value'],
                args.dry_run,
            )
            if ok:
                fixed += 1
                if args.verbose:
                    print(f"  FIX  {mid}.{issue['field']}: +{issue['issue']} = {issue['fix_value'][:40]}")
            else:
                skipped += 1
                if args.verbose:
                    print(f"  SKIP {mid}.{issue['field']}: could not patch")

    print()
    print("=" * 70)
    print(f"Fixed:   {fixed}")
    print(f"Skipped: {skipped}")
    print("=" * 70)

    if args.dry_run:
        print("DRY RUN - no files modified. Run without --dry-run to apply.")


if __name__ == '__main__':
    main()
