"""
Quality Standards - Defines schema quality requirements

This module defines what constitutes a "good" schema and provides
default values for missing fields.
"""
from enum import Enum
from typing import Dict, List, Set


class QualityLevel(str, Enum):
    """Quality level classification for issues."""
    CRITICAL = "critical"  # Must fix - breaks functionality
    WARNING = "warning"    # Should fix - impacts UX
    INFO = "info"          # Nice to have - best practice


# Required fields for each parameter in params_schema
REQUIRED_PARAM_FIELDS: List[str] = ['type']

# Recommended fields that should be present
RECOMMENDED_PARAM_FIELDS: List[str] = ['label', 'description']

# Fields that string-type params should have
STRING_PARAM_FIELDS: List[str] = ['placeholder']

# Required fields for output_schema entries
REQUIRED_OUTPUT_FIELDS: List[str] = ['type', 'description']

# Types that should have placeholder
TYPES_REQUIRING_PLACEHOLDER: Set[str] = {
    'string', 'url', 'selector', 'file_path', 'path', 'email',
}

# Default placeholders by field type
DEFAULT_PLACEHOLDERS: Dict[str, str] = {
    'string': 'Enter text...',
    'text': 'Enter text...',
    'number': '0',
    'integer': '0',
    'url': 'https://example.com',
    'selector': '#element-id or .class-name',
    'file_path': '/path/to/file',
    'path': '/path/to/file',
    'email': 'user@example.com',
    'password': '********',
    'json': '{"key": "value"}',
    'array': '[1, 2, 3]',
    'object': '{"key": "value"}',
    'regex': r'\d+',
    'script': 'return document.title',
    'code': '// code here',
    'datetime': '2024-01-01T00:00:00Z',
    'date': '2024-01-01',
    'time': '12:00:00',
    'duration': '1000',
    'color': '#000000',
    'phone': '+1234567890',
    'ip': '192.168.1.1',
    'uuid': '550e8400-e29b-41d4-a716-446655440000',
    'cron': '0 0 * * *',
}

# Default descriptions by field type (when no description is provided)
DEFAULT_DESCRIPTIONS: Dict[str, str] = {
    'string': 'Text input',
    'text': 'Text input',
    'number': 'Numeric value',
    'integer': 'Whole number value',
    'boolean': 'True or false toggle',
    'url': 'URL address',
    'selector': 'CSS/XPath selector to locate element',
    'file_path': 'Path to file on disk',
    'path': 'File or directory path',
    'email': 'Email address',
    'password': 'Password (hidden)',
    'json': 'JSON formatted data',
    'array': 'List of items',
    'object': 'Key-value data structure',
    'select': 'Select an option',
    'regex': 'Regular expression pattern',
    'script': 'JavaScript code to execute',
    'code': 'Code snippet',
    'datetime': 'Date and time value',
    'date': 'Date value',
    'time': 'Time value',
    'duration': 'Duration in milliseconds',
    'color': 'Color value in hex format',
    'phone': 'Phone number',
    'ip': 'IP address',
    'uuid': 'Universally unique identifier',
    'cron': 'Cron schedule expression',
}

# Default descriptions by common field names (key-based)
DEFAULT_DESCRIPTIONS_BY_KEY: Dict[str, str] = {
    'url': 'URL to navigate or request',
    'selector': 'CSS/XPath selector to locate element',
    'text': 'Text content',
    'value': 'The value to use',
    'key': 'The key name',
    'name': 'Name identifier',
    'path': 'File or directory path',
    'timeout': 'Maximum time to wait in milliseconds',
    'delay': 'Time to wait before action',
    'limit': 'Maximum number of items',
    'offset': 'Number of items to skip',
    'format': 'Output format',
    'encoding': 'Text encoding (e.g., utf-8)',
    'separator': 'Character(s) to separate items',
    'delimiter': 'Character(s) to split on',
    'pattern': 'Pattern to match',
    'replace': 'Replacement text',
    'prefix': 'Text to add at start',
    'suffix': 'Text to add at end',
    'default': 'Default value if not set',
    'message': 'Message content',
    'title': 'Title text',
    'description': 'Description text',
    'content': 'Content data',
    'data': 'Input data',
    'result': 'Operation result',
    'output': 'Output data',
    'input': 'Input data',
    'source': 'Source data or path',
    'target': 'Target data or path',
    'destination': 'Destination path',
    'query': 'Query string or parameters',
    'filter': 'Filter criteria',
    'sort': 'Sort order',
    'order': 'Order direction',
    'count': 'Number of items',
    'index': 'Position index',
    'start': 'Starting position',
    'end': 'Ending position',
    'length': 'Length value',
    'width': 'Width in pixels',
    'height': 'Height in pixels',
    'size': 'Size value',
    'quality': 'Quality level (0-100)',
    'level': 'Level value',
    'mode': 'Operation mode',
    'type': 'Type selection',
    'method': 'HTTP method or operation',
    'action': 'Action to perform',
    'operation': 'Operation type',
    'headers': 'HTTP headers',
    'body': 'Request body',
    'params': 'Parameters',
    'options': 'Additional options',
    'config': 'Configuration settings',
    'settings': 'Settings',
    'enabled': 'Enable or disable',
    'visible': 'Visibility toggle',
    'required': 'Whether required',
    'optional': 'Whether optional',
    'async': 'Run asynchronously',
    'wait': 'Wait for completion',
    'retry': 'Retry on failure',
    'condition': 'Condition expression',
    'expression': 'Expression to evaluate',
    'script': 'Script code to execute',
    'command': 'Command to run',
    'args': 'Command arguments',
    'env': 'Environment variables',
    'cwd': 'Working directory',
    'shell': 'Use shell execution',
}

# Default placeholders by common field names (key-based)
DEFAULT_PLACEHOLDERS_BY_KEY: Dict[str, str] = {
    'url': 'https://example.com',
    'selector': '#id, .class, or //xpath',
    'text': 'Enter text...',
    'value': 'Enter value...',
    'key': 'key_name',
    'name': 'Enter name...',
    'path': '/path/to/file',
    'timeout': '30000',
    'delay': '1000',
    'limit': '10',
    'offset': '0',
    'format': 'json',
    'encoding': 'utf-8',
    'separator': ',',
    'delimiter': ',',
    'pattern': r'\d+',
    'replace': '',
    'prefix': '',
    'suffix': '',
    'default': '',
    'message': 'Enter message...',
    'title': 'Enter title...',
    'description': 'Enter description...',
    'content': 'Enter content...',
    'query': 'search term',
    'filter': '',
    'index': '0',
    'start': '0',
    'end': '',
    'length': '10',
    'width': '1920',
    'height': '1080',
    'size': '100',
    'quality': '80',
    'level': '1',
    'headers': '{"Content-Type": "application/json"}',
    'body': '{}',
    'condition': 'value > 0',
    'expression': 'value',
    'script': 'return document.title',
    'command': 'echo "hello"',
    'args': '[]',
    'cwd': '.',
}

# Categories that are expected to have modules (for validation)
EXPECTED_CATEGORIES: Set[str] = {
    'string', 'array', 'object', 'math', 'datetime',
    'browser', 'http', 'file', 'data', 'flow',
    'ai', 'llm', 'notification', 'database',
    'image', 'document', 'validate', 'encode',
    'convert', 'check', 'logic', 'format',
    'set', 'random', 'hash', 'regex', 'path',
    'process', 'storage', 'compare', 'text',
    'stats', 'crypto', 'utility', 'vector',
    'training', 'testing', 'analysis', 'search',
    'error', 'vision', 'huggingface',
}

# Flow control module IDs that need special type handling
FLOW_CONTROL_MODULES: Set[str] = {
    'flow.start', 'flow.end', 'flow.branch', 'flow.switch',
    'flow.merge', 'flow.parallel', 'flow.fork', 'flow.join',
    'flow.invoke', 'flow.batch', 'flow.breakpoint',
    'flow.container', 'flow.error_handle', 'flow.subflow',
}
