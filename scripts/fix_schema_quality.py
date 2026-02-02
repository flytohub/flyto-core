#!/usr/bin/env python3
"""
Auto-fix script for params_schema quality issues.
Adds missing descriptions and placeholders based on field types and names.
"""
import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Default descriptions based on common field names
DEFAULT_DESCRIPTIONS = {
    'url': 'URL to navigate to or request',
    'path': 'File or directory path',
    'file_path': 'Path to the file',
    'text': 'Text content',
    'content': 'Content to process',
    'message': 'Message text',
    'query': 'Search query or database query',
    'selector': 'CSS selector or element identifier',
    'timeout': 'Maximum time to wait',
    'timeout_ms': 'Maximum time to wait in milliseconds',
    'timeout_s': 'Maximum time to wait in seconds',
    'name': 'Name identifier',
    'key': 'Key identifier',
    'value': 'Value to set or compare',
    'format': 'Output format',
    'encoding': 'Character encoding',
    'mode': 'Operation mode',
    'type': 'Type identifier',
    'id': 'Unique identifier',
    'title': 'Title text',
    'description': 'Description text',
    'email': 'Email address',
    'password': 'Password (sensitive)',
    'username': 'Username',
    'api_key': 'API key for authentication',
    'token': 'Authentication token',
    'host': 'Host address or hostname',
    'port': 'Port number',
    'method': 'HTTP method or operation method',
    'headers': 'HTTP headers',
    'body': 'Request body content',
    'data': 'Data to process',
    'json': 'JSON data',
    'params': 'Parameters',
    'options': 'Configuration options',
    'config': 'Configuration settings',
    'settings': 'Settings',
    'args': 'Arguments',
    'kwargs': 'Keyword arguments',
    'command': 'Command to execute',
    'script': 'Script code to run',
    'code': 'Code to execute',
    'expression': 'Expression to evaluate',
    'pattern': 'Pattern to match',
    'regex': 'Regular expression pattern',
    'template': 'Template string',
    'prompt': 'Prompt text for AI',
    'model': 'AI model identifier',
    'temperature': 'Sampling temperature for AI',
    'max_tokens': 'Maximum tokens for AI response',
    'width': 'Width in pixels',
    'height': 'Height in pixels',
    'size': 'Size value',
    'count': 'Number of items',
    'limit': 'Maximum number of items',
    'offset': 'Starting offset',
    'page': 'Page number',
    'sort': 'Sort order',
    'order': 'Ordering direction',
    'filter': 'Filter expression',
    'condition': 'Condition to evaluate',
    'from': 'Source or sender',
    'to': 'Destination or recipient',
    'subject': 'Subject line',
    'cc': 'Carbon copy recipients',
    'bcc': 'Blind carbon copy recipients',
    'attachments': 'File attachments',
    'priority': 'Priority level',
    'status': 'Status value',
    'state': 'State value',
    'level': 'Level value',
    'output': 'Output destination',
    'input': 'Input source',
    'source': 'Source location',
    'destination': 'Destination location',
    'target': 'Target element or location',
    'action': 'Action to perform',
    'operation': 'Operation type',
    'env': 'Environment name',
    'environment': 'Environment settings',
    'cwd': 'Current working directory',
    'shell': 'Shell to use',
    'stdin': 'Standard input',
    'stdout': 'Standard output',
    'stderr': 'Standard error output',
    'pid': 'Process ID',
    'delay': 'Delay duration',
    'interval': 'Interval between operations',
    'retry': 'Number of retry attempts',
    'retries': 'Maximum retry attempts',
    'wait': 'Wait duration',
    'duration': 'Duration of operation',
    'start': 'Start position or time',
    'end': 'End position or time',
    'begin': 'Beginning position',
    'finish': 'Finish condition',
    'enabled': 'Whether feature is enabled',
    'disabled': 'Whether feature is disabled',
    'active': 'Whether item is active',
    'visible': 'Whether element is visible',
    'hidden': 'Whether element is hidden',
    'async': 'Whether to run asynchronously',
    'sync': 'Whether to run synchronously',
    'recursive': 'Whether to process recursively',
    'force': 'Whether to force operation',
    'overwrite': 'Whether to overwrite existing',
    'append': 'Whether to append to existing',
    'create': 'Whether to create if not exists',
    'delete': 'Whether to delete',
    'update': 'Whether to update',
    'insert': 'Whether to insert',
    'merge': 'Whether to merge',
    'replace': 'Whether to replace',
    'skip': 'Items to skip',
    'include': 'Items to include',
    'exclude': 'Items to exclude',
    'ignore': 'Items to ignore',
    'allow': 'Items to allow',
    'deny': 'Items to deny',
    'verbose': 'Enable verbose output',
    'debug': 'Enable debug mode',
    'quiet': 'Suppress output',
    'silent': 'Run silently',
    'dry_run': 'Simulate without making changes',
    'headless': 'Run without visible window',
    'browser': 'Browser type',
    'browser_type': 'Type of browser to use',
    'user_agent': 'Custom user agent string',
    'viewport': 'Viewport dimensions',
    'proxy': 'Proxy server address',
    'auth': 'Authentication credentials',
    'credentials': 'Login credentials',
    'cookies': 'Browser cookies',
    'storage': 'Storage type',
    'cache': 'Cache settings',
    'session': 'Session identifier',
    'connection': 'Database connection',
    'database': 'Database name',
    'table': 'Database table name',
    'collection': 'Collection name',
    'schema': 'Schema definition',
    'fields': 'Field definitions',
    'columns': 'Column names',
    'rows': 'Row data',
    'records': 'Record data',
    'bucket': 'Storage bucket name',
    'container': 'Container name',
    'region': 'Cloud region',
    'zone': 'Availability zone',
    'account': 'Account identifier',
    'project': 'Project identifier',
    'namespace': 'Namespace identifier',
    'service': 'Service name',
    'endpoint': 'API endpoint',
    'base_url': 'Base URL for requests',
    'callback': 'Callback URL',
    'webhook': 'Webhook URL',
    'redirect': 'Redirect URL',
    'return_url': 'Return URL after operation',
}

# Default placeholders based on field names
DEFAULT_PLACEHOLDERS = {
    'url': 'https://example.com',
    'path': '/path/to/file',
    'file_path': '/path/to/file.txt',
    'text': 'Enter text here...',
    'content': 'Content goes here...',
    'message': 'Enter message...',
    'query': 'SELECT * FROM table',
    'selector': '#element-id or .class-name',
    'name': 'my-name',
    'key': 'key-name',
    'value': 'value',
    'email': 'user@example.com',
    'username': 'username',
    'password': '••••••••',
    'api_key': 'sk-...',
    'token': 'token-value',
    'host': 'localhost',
    'command': 'echo "Hello"',
    'script': 'console.log("Hello")',
    'code': 'print("Hello")',
    'pattern': '.*pattern.*',
    'regex': '^regex$',
    'template': 'Hello {{name}}!',
    'prompt': 'Ask a question...',
    'model': 'gpt-4',
    'from': 'sender@example.com',
    'to': 'recipient@example.com',
    'subject': 'Email Subject',
    'title': 'Title',
    'description': 'Description text',
    'id': 'unique-id',
    'format': 'json',
    'encoding': 'utf-8',
    'mode': 'default',
    'type': 'default',
    'bucket': 'my-bucket',
    'container': 'my-container',
    'region': 'us-east-1',
    'account': 'account-id',
    'project': 'project-id',
    'namespace': 'default',
    'service': 'my-service',
    'endpoint': '/api/v1/resource',
    'base_url': 'https://api.example.com',
    'callback': 'https://example.com/callback',
    'webhook': 'https://example.com/webhook',
    'database': 'my_database',
    'table': 'my_table',
    'collection': 'my_collection',
    'cwd': '/working/directory',
    'shell': '/bin/bash',
    'user_agent': 'Mozilla/5.0...',
    'proxy': 'http://proxy:8080',
}


def get_default_description(field_name: str, field_type: str) -> str:
    """Get default description for a field based on its name and type."""
    # Try exact match first
    name_lower = field_name.lower()
    if name_lower in DEFAULT_DESCRIPTIONS:
        return DEFAULT_DESCRIPTIONS[name_lower]

    # Try partial matches
    for key, desc in DEFAULT_DESCRIPTIONS.items():
        if key in name_lower or name_lower in key:
            return desc

    # Generate based on type
    type_defaults = {
        'string': f'{field_name.replace("_", " ").title()} value',
        'number': f'{field_name.replace("_", " ").title()} number',
        'boolean': f'Whether to enable {field_name.replace("_", " ")}',
        'array': f'List of {field_name.replace("_", " ")}',
        'object': f'{field_name.replace("_", " ").title()} configuration',
        'select': f'Select {field_name.replace("_", " ")}',
    }

    return type_defaults.get(field_type, f'{field_name.replace("_", " ").title()} parameter')


def get_default_placeholder(field_name: str, field_type: str) -> str:
    """Get default placeholder for a string field."""
    # Try exact match first
    name_lower = field_name.lower()
    if name_lower in DEFAULT_PLACEHOLDERS:
        return DEFAULT_PLACEHOLDERS[name_lower]

    # Try partial matches
    for key, ph in DEFAULT_PLACEHOLDERS.items():
        if key in name_lower:
            return ph

    # Generate based on name
    return f'Enter {field_name.replace("_", " ")}...'


def analyze_module_schema(module_id: str, metadata: Dict) -> List[Dict]:
    """Analyze a module's params_schema for missing fields."""
    issues = []
    params_schema = metadata.get('params_schema', {})

    if not params_schema or not isinstance(params_schema, dict):
        return issues

    for field_key, field_def in params_schema.items():
        if field_key.startswith('__'):
            continue
        if not isinstance(field_def, dict):
            continue

        field_type = field_def.get('type', 'string')

        if 'description' not in field_def:
            issues.append({
                'module_id': module_id,
                'field': field_key,
                'issue': 'missing_description',
                'suggested': get_default_description(field_key, field_type),
            })

        if field_type == 'string' and 'placeholder' not in field_def:
            issues.append({
                'module_id': module_id,
                'field': field_key,
                'issue': 'missing_placeholder',
                'suggested': get_default_placeholder(field_key, field_type),
            })

    return issues


def main():
    """Main function to analyze and report schema issues."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

    from core.modules.registry import ModuleRegistry
    from core.modules import *  # Load all modules

    all_issues = []

    for mid in sorted(ModuleRegistry._modules.keys()):
        meta = ModuleRegistry.get_metadata(mid)
        issues = analyze_module_schema(mid, meta)
        all_issues.extend(issues)

    # Group by module
    by_module = {}
    for issue in all_issues:
        mid = issue['module_id']
        if mid not in by_module:
            by_module[mid] = []
        by_module[mid].append(issue)

    # Print report
    print(f"Schema Quality Report")
    print("=" * 60)
    print(f"Total issues: {len(all_issues)}")
    print(f"Modules affected: {len(by_module)}")
    print()

    # Print issues with suggested fixes
    for mid in sorted(by_module.keys()):
        issues = by_module[mid]
        print(f"\n{mid}:")
        for issue in issues:
            print(f"  - {issue['field']}: {issue['issue']}")
            print(f"    Suggested: {issue['suggested']}")


if __name__ == '__main__':
    main()
