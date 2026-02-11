#!/usr/bin/env python3
"""
Schema Fixer v4 - Handles field(), schema_field(), and dict-style schemas.
Each change validated with ast.parse() before writing.
"""
import ast
import re
import sys
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
CORE_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(CORE_ROOT / 'src'))

PLACEHOLDER_MAP = {
    'url': 'https://example.com', 'base_url': 'https://api.example.com',
    'ollama_url': 'http://localhost:11434', 'api_key': 'sk-...',
    'auth_token': 'Bearer your-token', 'token': 'your-token',
    'model': 'gpt-4o', 'prompt': 'Enter your prompt...',
    'system_message': 'You are a helpful assistant.',
    'text': 'Enter text...', 'content': 'Enter content...',
    'message': 'Your message here', 'body': 'Request body',
    'query': 'SELECT * FROM table', 'selector': '#element',
    'name': 'my-name', 'title': 'Title',
    'description': 'Description text', 'comment': 'Your comment',
    'file_path': '/path/to/file', 'path': '/path/to/file',
    'input_path': '/path/to/input', 'output_path': '/path/to/output',
    'output_dir': '/path/to/output', 'directory': '/path/to/dir',
    'source': '/path/to/source', 'destination': '/path/to/dest',
    'bucket': 'my-bucket', 'region': 'us-east-1',
    'container': 'my-container', 'container_name': 'my-container',
    'database': 'mydb', 'database_id': 'database-id',
    'table_name': 'my_table', 'collection': 'my_collection',
    'key': 'my-key', 'value': 'value', 'id': 'unique-id',
    'base_id': 'app12345', 'account_id': 'account-id',
    'project_id': 'project-id', 'repo': 'username/repo',
    'owner': 'username', 'branch': 'main',
    'pattern': '^pattern$', 'format': 'json',
    'template': 'Hello {{name}}!', 'separator': ',',
    'endpoint': '/api/v1/resource', 'context': 'Additional context...',
    'goal': 'Describe the goal...', 'input': 'Input data...',
    'code': 'print("hello")', 'expression': '1 + 1',
    'command': 'echo hello', 'header': 'Header text',
    'footer': 'Footer text', 'header_name': 'X-Custom-Header',
    'prompt_text': 'Enter text here', 'method': 'GET',
    'content_type': 'application/json', 'phone': '+1234567890',
    'to_number': '+1234567890', 'from_number': '+1234567890',
    'account_sid': 'ACxxxxxxxx', 'auth_token_val': 'your-token',
    'table_id': 'tblXXXXXXXX', 'record_id': 'recXXXXXXXX',
    'ruleset_path': '/path/to/ruleset.yaml',
    'figma_file_id': 'xxxxxxxxx', 'figma_token': 'figd_...',
    'report_format': 'html', 'item_var': 'item',
    'index_var': 'index', 'target': 'target',
    'trigger_type': 'manual', 'operation': 'add',
    'customer_id': 'cus_xxxxx', 'amount': '1000',
    'currency': 'usd', 'webhook_url': 'https://example.com/webhook',
    'channel': '#general', 'username': 'username',
}

DESCRIPTION_MAP = {
    'url': 'Target URL', 'api_key': 'API key for authentication',
    'model': 'AI model identifier', 'prompt': 'Prompt text',
    'text': 'Text content', 'file_path': 'Path to the file',
    'path': 'File or directory path', 'query': 'Query string',
    'selector': 'CSS selector', 'name': 'Name identifier',
    'header_name': 'HTTP header name', 'headers': 'HTTP headers',
    'timeout': 'Maximum wait time in ms',
    'include_context': 'Whether to include execution context',
    'trigger_type': 'Type of trigger event',
    'operation': 'Operation to perform',
    'context': 'Additional context data',
}


def get_placeholder(name: str) -> str:
    n = name.lower()
    if n in PLACEHOLDER_MAP:
        return PLACEHOLDER_MAP[n]
    for k, v in PLACEHOLDER_MAP.items():
        if k in n:
            return v
    return f'Enter {name.replace("_", " ")}...'


def get_description(name: str) -> str:
    n = name.lower()
    if n in DESCRIPTION_MAP:
        return DESCRIPTION_MAP[n]
    for k, v in DESCRIPTION_MAP.items():
        if k in n:
            return v
    return f'{name.replace("_", " ")} parameter'


def find_matching_close(content: str, start: int, open_ch: str, close_ch: str) -> Optional[int]:
    """Find matching closing bracket/paren, respecting strings."""
    depth = 0
    i = start
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
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def add_kwarg_to_call(content: str, field_name: str, prop: str, value: str,
                      call_name: str = 'field') -> Optional[str]:
    """Add kwarg to field() or schema_field() call."""
    escaped = re.escape(field_name)
    pattern = rf"{re.escape(call_name)}\(\s*['\"]({escaped})['\"]"

    for m in re.finditer(pattern, content):
        paren_pos = content.index('(', m.start())
        close = find_matching_close(content, paren_pos, '(', ')')
        if close is None:
            continue

        body = content[paren_pos:close + 1]
        if f"{prop}=" in body:
            return None  # already has it

        # Get indent from existing kwargs
        indent = '        '
        for line in body.split('\n')[1:]:
            stripped = line.lstrip()
            if stripped and ('=' in stripped or stripped.startswith("'")):
                indent = line[:len(line) - len(stripped)]
                break

        # Insert before closing paren
        before = content[paren_pos + 1:close].rstrip()
        comma = '' if before.endswith(',') else ','
        escaped_val = value.replace("'", "\\'")
        insert = f"{comma}\n{indent}{prop}='{escaped_val}',"
        return content[:close] + insert + '\n' + content[close:]

    return None


def add_to_dict(content: str, field_name: str, prop: str, value: str) -> Optional[str]:
    """Add property to dict-style field definition."""
    escaped = re.escape(field_name)
    pattern = rf"['\"]({escaped})['\"]:\s*\{{"

    for m in re.finditer(pattern, content):
        brace_pos = content.index('{', m.start() + len(field_name))
        close = find_matching_close(content, brace_pos, '{', '}')
        if close is None:
            continue

        body = content[brace_pos:close + 1]
        if f"'{prop}'" in body or f'"{prop}"' in body:
            return None  # already has it

        # Get indent
        indent = '            '
        for line in body.split('\n')[1:]:
            stripped = line.lstrip()
            if stripped.startswith("'") or stripped.startswith('"'):
                indent = line[:len(line) - len(stripped)]
                break

        before = content[brace_pos + 1:close].rstrip()
        comma = '' if before.endswith(',') else ','
        escaped_val = value.replace("'", "\\'")
        insert = f"{comma}\n{indent}'{prop}': '{escaped_val}',"
        return content[:close] + insert + '\n' + content[close:]

    return None


def apply_fix(file_path: Path, field_name: str, issue: str, fix_value: str, dry_run: bool) -> bool:
    content = file_path.read_text(encoding='utf-8')
    original = content
    prop = 'description' if issue == 'Q013' else 'placeholder'

    # Try field() call
    result = add_kwarg_to_call(content, field_name, prop, fix_value, 'field')
    # Try schema_field() call
    if result is None:
        result = add_kwarg_to_call(content, field_name, prop, fix_value, 'schema_field')
    # Try dict-style
    if result is None:
        result = add_to_dict(content, field_name, prop, fix_value)

    if result is None or result == original:
        return False

    try:
        ast.parse(result)
    except SyntaxError:
        return False

    if not dry_run:
        file_path.write_text(result, encoding='utf-8')
    return True


def get_issues():
    from core.modules.registry import ModuleRegistry
    import core.modules.atomic
    try:
        import core.modules.third_party
    except Exception:
        pass

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
                issues.append({'module_id': mid, 'field': fkey,
                              'issue': 'Q013', 'fix_value': get_description(fkey)})
            if ftype in ('string', 'text') and not has_options and 'placeholder' not in fdef:
                issues.append({'module_id': mid, 'field': fkey,
                              'issue': 'Q014', 'fix_value': get_placeholder(fkey)})
    return issues


def find_module_file(module_id: str) -> Optional[Path]:
    search_dirs = [
        CORE_ROOT / 'src' / 'core' / 'modules' / 'atomic',
        CORE_ROOT / 'src' / 'core' / 'modules' / 'third_party',
    ]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob('*.py'):
            if py_file.name == '__init__.py':
                continue
            try:
                content = py_file.read_text(encoding='utf-8')
            except Exception:
                continue
            if f"'{module_id}'" in content or f'"{module_id}"' in content:
                return py_file
    return None


def main():
    dry_run = '--dry-run' in sys.argv
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    print("=" * 60)
    print("Schema Fixer v4 - field/schema_field/dict + AST safe")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    issues = get_issues()
    q013 = [i for i in issues if i['issue'] == 'Q013']
    q014 = [i for i in issues if i['issue'] == 'Q014']
    print(f"Found {len(issues)} issues (Q013: {len(q013)}, Q014: {len(q014)})")

    by_module = {}
    for issue in issues:
        by_module.setdefault(issue['module_id'], []).append(issue)

    fixed = 0
    skipped = 0
    file_cache = {}

    for mid in sorted(by_module.keys()):
        if mid not in file_cache:
            file_cache[mid] = find_module_file(mid)
        fp = file_cache[mid]
        if not fp:
            skipped += len(by_module[mid])
            if verbose:
                print(f"  SKIP {mid}: file not found")
            continue

        for issue in by_module[mid]:
            ok = apply_fix(fp, issue['field'], issue['issue'], issue['fix_value'], dry_run)
            if ok:
                fixed += 1
                if verbose:
                    print(f"  FIX  {mid}.{issue['field']}: +{issue['issue']}")
            else:
                skipped += 1
                if verbose:
                    print(f"  SKIP {mid}.{issue['field']}")

    print()
    print("=" * 60)
    print(f"Fixed:   {fixed}")
    print(f"Skipped: {skipped}")
    print("=" * 60)


if __name__ == '__main__':
    main()
