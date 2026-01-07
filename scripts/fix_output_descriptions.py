#!/usr/bin/env python3
"""
Fix output_schema descriptions in modules.

This script adds missing 'description' fields to output_schema entries.
"""
import re
import os
import sys
from pathlib import Path

# Standard descriptions for common field names
FIELD_DESCRIPTIONS = {
    # Status fields
    'status': 'Operation status (success/error)',
    'ok': 'Whether the operation succeeded',
    'success': 'Whether the operation completed successfully',
    'message': 'Result message describing the outcome',
    'error': 'Error message if operation failed',
    'error_code': 'Error code for programmatic handling',

    # Data fields
    'result': 'The operation result',
    'data': 'Output data from the operation',
    'output': 'Operation output',
    'value': 'The returned value',
    'content': 'Content returned by the operation',
    'text': 'Text content',
    'html': 'HTML content',

    # Identifiers
    'id': 'Unique identifier',
    'name': 'Name of the item',
    'key': 'Key identifier',
    'url': 'URL address',
    'path': 'File or resource path',
    'filepath': 'Path to the file',

    # Browser specific
    'selector': 'CSS selector that was used',
    'element': 'Element that was found or manipulated',
    'duration_ms': 'Duration in milliseconds',
    'cookies': 'Browser cookies',
    'screenshot': 'Screenshot file path or data',
    'title': 'Page title',
    'page_url': 'Current page URL',

    # Network/API
    'response': 'Response from the operation',
    'headers': 'HTTP headers',
    'body': 'Response body content',
    'status_code': 'HTTP status code',

    # Count/numeric fields
    'count': 'Number of items',
    'total': 'Total count',
    'length': 'Length of data',
    'size': 'Size in bytes',
    'index': 'Item index',

    # Time fields
    'timestamp': 'Unix timestamp',
    'created_at': 'Creation timestamp',
    'updated_at': 'Last update timestamp',
    'year': 'Year component',
    'month': 'Month component',
    'day': 'Day component',
    'hour': 'Hour component',
    'minute': 'Minute component',
    'second': 'Second component',

    # List/array fields
    'items': 'List of items',
    'results': 'List of results',
    'rows': 'Data rows',
    'keys': 'List of keys',
    'values': 'List of values',

    # File operations
    'filename': 'Name of the file',
    'bytes_written': 'Number of bytes written',
    'bytes_read': 'Number of bytes read',
    'lines': 'Lines of text',

    # Test/validation
    'passed': 'Number of tests passed',
    'failed': 'Number of tests failed',
    'skipped': 'Number of tests skipped',
    'errors': 'Number of errors encountered',

    # GitHub/API
    'repo': 'Repository information',
    'full_name': 'Full repository name',
    'description': 'Item description',
    'stars': 'Number of stars',
    'forks': 'Number of forks',
    'issue': 'Issue information',
    'number': 'Issue or PR number',
    'html_url': 'HTML URL for web access',

    # Cloud/storage
    'bucket': 'Storage bucket name',
    'object_name': 'Object name in storage',
    'public_url': 'Public accessible URL',
    'etag': 'Entity tag for caching',

    # Payment
    'amount': 'Payment amount',
    'currency': 'Currency code',
    'client_secret': 'Client secret for payment',
    'balance': 'Account balance',
    'email': 'Email address',
    'created': 'Creation timestamp',

    # AI/ML
    'model': 'Model name or identifier',
    'context': 'Context information',
    'total_duration': 'Total processing duration',
    'load_duration': 'Model loading duration',
    'prompt_eval_count': 'Number of prompt tokens evaluated',
    'eval_count': 'Number of tokens generated',

    # Element
    'found': 'Whether element was found',
    'visible': 'Whether element is visible',
    'enabled': 'Whether element is enabled',
    'attributes': 'Element attributes',
    'tag_name': 'HTML tag name',

    # Frame
    'frames': 'List of frames',
    'frame_url': 'Frame URL',

    # Network
    'requests': 'Captured network requests',
    'responses': 'Captured network responses',

    # Scroll
    'scroll_x': 'Horizontal scroll position',
    'scroll_y': 'Vertical scroll position',

    # Storage
    'storage_type': 'Type of storage used',

    # Console
    'logs': 'Console log entries',

    # Dialog
    'dialog_type': 'Type of dialog',
    'dialog_message': 'Dialog message content',

    # Geolocation
    'latitude': 'Geographic latitude',
    'longitude': 'Geographic longitude',
    'accuracy': 'Location accuracy in meters',

    # PDF
    'pdf_path': 'Path to generated PDF',
    'page_count': 'Number of pages',

    # Upload/Download
    'download_path': 'Path to downloaded file',
    'upload_status': 'Status of upload operation',

    # Tab management
    'tab_id': 'Tab identifier',
    'tabs': 'List of open tabs',
    'active_tab': 'Currently active tab',

    # Record
    'recording': 'Recording data or path',
    'duration': 'Recording duration',

    # Notification
    'notification_id': 'Notification identifier',
    'sent': 'Whether notification was sent',
    'recipients': 'List of recipients',
    'message_id': 'Message identifier',

    # Database
    'row_count': 'Number of rows affected',
    'columns': 'Column names',
    'inserted_count': 'Number of rows inserted',
    'updated_count': 'Number of rows updated',
    'deleted_count': 'Number of rows deleted',
    'returning_data': 'Data returned from operation',

    # Flow control
    'branch': 'Branch that was taken',
    'condition_met': 'Whether condition was met',
    'iteration': 'Current iteration number',
    'completed': 'Whether operation completed',

    # Meta
    'version': 'Version string',
    'metadata': 'Additional metadata',
    'info': 'Information object',

    # Evaluation
    'eval_result': 'JavaScript evaluation result',
    'console_output': 'Console output from evaluation',
}


def fix_output_schema_in_file(filepath: Path) -> tuple[int, list]:
    """Fix output_schema descriptions in a single file."""
    content = filepath.read_text()
    original = content
    fixes = []

    # Find output_schema blocks
    # Pattern: output_schema={...}
    pattern = r"output_schema\s*=\s*\{"
    match = re.search(pattern, content)

    if not match:
        return 0, fixes

    # Find all field definitions that are missing description
    # Pattern: 'field_name': {'type': 'xxx'}  (no description)
    # Should become: 'field_name': {'type': 'xxx', 'description': 'xxx'}

    field_pattern = r"'([a-z_]+)':\s*\{\s*'type':\s*'([^']+)'\s*\}"

    def replace_field(m):
        field_name = m.group(1)
        field_type = m.group(2)

        # Get description
        desc = FIELD_DESCRIPTIONS.get(field_name, f'The {field_name.replace("_", " ")}')
        fixes.append(f"  Added description for '{field_name}'")

        return f"'{field_name}': {{'type': '{field_type}', 'description': '{desc}'}}"

    content = re.sub(field_pattern, replace_field, content)

    if content != original:
        filepath.write_text(content)
        return len(fixes), fixes

    return 0, fixes


def main():
    project_root = Path(__file__).parent.parent
    modules_dir = project_root / 'src' / 'core' / 'modules'

    total_fixed = 0
    files_modified = 0

    # Find all Python files in modules
    for py_file in modules_dir.rglob('*.py'):
        if '__pycache__' in str(py_file):
            continue
        if py_file.name == '__init__.py':
            continue

        fixed, fixes = fix_output_schema_in_file(py_file)
        if fixed > 0:
            files_modified += 1
            total_fixed += fixed
            rel_path = py_file.relative_to(project_root)
            print(f"Fixed {rel_path}: {fixed} fields")
            for fix in fixes:
                print(fix)
            print()

    print(f"\nTotal: {total_fixed} descriptions added in {files_modified} files")


if __name__ == '__main__':
    main()
