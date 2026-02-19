"""
Env Load Dotenv Module
Load environment variables from a .env file.
Parses the file manually without external dependencies.
"""
import logging
import os
from typing import Any, Dict, List, Tuple

from ...registry import register_module
from ...schema import compose
from ...schema.builders import field
from ...schema.constants import FieldGroup
from ...errors import ValidationError, ModuleError
from ....utils import validate_path_with_env_config, PathTraversalError

logger = logging.getLogger(__name__)


def _parse_dotenv(content: str) -> List[Tuple[str, str]]:
    """
    Parse .env file content into a list of (key, value) pairs.

    Handles:
    - Comments (lines starting with #)
    - Empty lines
    - Quoted values (single and double quotes)
    - Inline comments after unquoted values
    - export prefix (e.g., export KEY=value)
    - Whitespace trimming
    """
    result = []

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue

        # Strip optional 'export ' prefix
        if line.startswith('export '):
            line = line[7:].strip()

        # Split on first '='
        if '=' not in line:
            continue

        key, raw_value = line.split('=', 1)
        key = key.strip()

        if not key:
            continue

        raw_value = raw_value.strip()

        # Handle quoted values
        if len(raw_value) >= 2:
            if (raw_value[0] == '"' and raw_value[-1] == '"'):
                # Double-quoted: strip quotes, process escape sequences
                value = raw_value[1:-1]
                value = value.replace('\\n', '\n')
                value = value.replace('\\t', '\t')
                value = value.replace('\\"', '"')
                value = value.replace('\\\\', '\\')
            elif (raw_value[0] == "'" and raw_value[-1] == "'"):
                # Single-quoted: strip quotes, no escape processing
                value = raw_value[1:-1]
            else:
                # Unquoted: strip inline comments
                comment_idx = raw_value.find(' #')
                if comment_idx != -1:
                    value = raw_value[:comment_idx].strip()
                else:
                    value = raw_value
        else:
            value = raw_value

        result.append((key, value))

    return result


@register_module(
    module_id='env.load_dotenv',
    version='1.0.0',
    category='env',
    tags=['env', 'environment', 'dotenv', 'config', 'load'],
    label='Load .env File',
    label_key='modules.env.load_dotenv.label',
    description='Load environment variables from a .env file',
    description_key='modules.env.load_dotenv.description',
    icon='Settings',
    color='#059669',

    input_types=['string'],
    output_types=['string'],

    can_receive_from=['*'],
    can_connect_to=['*'],

    timeout_ms=10000,
    retryable=False,
    concurrent_safe=False,

    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['filesystem.read'],

    params_schema=compose(
        field(
            'path',
            type='string',
            label='File Path',
            label_key='modules.env.load_dotenv.params.path.label',
            description='Path to the .env file',
            description_key='modules.env.load_dotenv.params.path.description',
            required=True,
            default='.env',
            placeholder='.env',
            group=FieldGroup.BASIC,
            format='path',
        ),
        field(
            'override',
            type='boolean',
            label='Override Existing',
            label_key='modules.env.load_dotenv.params.override.label',
            description='Whether to override existing environment variables',
            description_key='modules.env.load_dotenv.params.override.description',
            default=False,
            group=FieldGroup.OPTIONS,
        ),
    ),
    output_schema={
        'loaded_count': {
            'type': 'number',
            'description': 'Number of variables loaded',
            'description_key': 'modules.env.load_dotenv.output.loaded_count.description',
        },
        'variables': {
            'type': 'array',
            'description': 'List of variable names that were loaded',
            'description_key': 'modules.env.load_dotenv.output.variables.description',
        },
    },
    examples=[
        {
            'title': 'Load .env file',
            'title_key': 'modules.env.load_dotenv.examples.basic.title',
            'params': {
                'path': '.env',
                'override': False,
            },
        }
    ],
)
async def env_load_dotenv(context: Dict[str, Any]) -> Dict[str, Any]:
    """Load environment variables from a .env file."""
    params = context['params']
    path = params.get('path', '.env')
    override = params.get('override', False)

    if not path:
        raise ValidationError("Missing required parameter: path", field="path")

    # Validate path
    try:
        safe_path = validate_path_with_env_config(path)
    except PathTraversalError as e:
        raise ModuleError(str(e), code="PATH_TRAVERSAL")

    if not os.path.exists(safe_path):
        raise ModuleError(
            "File not found: {}".format(path),
            code="FILE_NOT_FOUND",
        )

    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise ModuleError("Failed to read .env file: {}".format(str(e)))

    pairs = _parse_dotenv(content)
    loaded_vars = []

    for key, value in pairs:
        if override or key not in os.environ:
            os.environ[key] = value
            loaded_vars.append(key)

    return {
        'ok': True,
        'data': {
            'loaded_count': len(loaded_vars),
            'variables': loaded_vars,
        },
    }
