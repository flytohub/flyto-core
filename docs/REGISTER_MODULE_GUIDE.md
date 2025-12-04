# Register Module Guide

A beginner-friendly guide to creating your first Flyto Core module using the `@register_module` decorator.

---

## Quick Start (3 Minutes)

Create a new module in 3 steps:

### Step 1: Create the File

```python
# src/core/modules/atomic/string/hello.py

from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module


@register_module('string.hello')
class HelloModule(BaseModule):
    """Say hello to someone"""

    module_name = "Hello"
    module_description = "Say hello to someone"

    def validate_params(self):
        self.name = self.require_param('name')

    async def execute(self):
        return {
            "result": f"Hello, {self.name}!",
            "status": "success"
        }
```

### Step 2: Register in `__init__.py`

```python
# src/core/modules/atomic/string/__init__.py

from .hello import HelloModule
```

### Step 3: Test It

```python
import asyncio
from src.core.modules.registry import ModuleRegistry

async def main():
    result = await ModuleRegistry.execute(
        'string.hello',
        params={'name': 'World'},
        context={}
    )
    print(result)  # {"result": "Hello, World!", "status": "success"}

asyncio.run(main())
```

Or use YAML:

```yaml
# workflows/hello.yaml
name: Hello World
steps:
  - id: greet
    module: string.hello
    params:
      name: "Flyto"
```

```bash
python run.py workflows/hello.yaml
```

---

## Full Module Template

For production-ready modules, use the complete decorator:

```python
"""
Hello Module - Greets a user by name

All docstrings should be in English.
"""
import logging
from typing import Any, Dict

from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module

logger = logging.getLogger(__name__)


@register_module(
    # Required: Unique identifier
    module_id='string.hello',
    version='1.0.0',
    category='string',

    # Tags for search and filtering (2-5 recommended)
    tags=['string', 'greeting', 'text', 'utility'],

    # Display information
    label='Say Hello',
    label_key='modules.string.hello.label',  # i18n key
    description='Generate a greeting message for the given name',
    description_key='modules.string.hello.description',

    # Visual (for UI)
    icon='MessageCircle',  # Lucide icon name
    color='#10B981',       # Hex color

    # Input/Output types
    input_types=['text'],
    output_types=['text'],

    # Parameter definitions
    params_schema={
        'name': {
            'type': 'string',
            'label': 'Name',
            'description': 'The name to greet',
            'required': True,
            'placeholder': 'Enter a name...'
        },
        'uppercase': {
            'type': 'boolean',
            'label': 'Uppercase',
            'description': 'Convert to uppercase',
            'required': False,
            'default': False
        }
    },

    # Output structure
    output_schema={
        'result': {'type': 'string', 'description': 'The greeting message'},
        'status': {'type': 'string'}
    },

    # Examples for documentation and AI
    examples=[
        {
            'name': 'Basic greeting',
            'params': {'name': 'World'},
            'expected_output': {'result': 'Hello, World!'}
        },
        {
            'name': 'Uppercase greeting',
            'params': {'name': 'World', 'uppercase': True},
            'expected_output': {'result': 'HELLO, WORLD!'}
        }
    ],

    # Metadata
    author='Your Name',
    license='MIT'
)
class HelloModule(BaseModule):
    """
    Hello Module

    Generates a greeting message for the given name.
    Optionally converts to uppercase.
    """

    module_name = "Say Hello"
    module_description = "Generate a greeting message"

    def validate_params(self) -> None:
        """Validate and extract parameters"""
        self.name = self.require_param('name')
        self.uppercase = self.get_param('uppercase', False)

    async def execute(self) -> Dict[str, Any]:
        """Execute the module logic"""
        logger.debug(f"Generating greeting for: {self.name}")

        greeting = f"Hello, {self.name}!"

        if self.uppercase:
            greeting = greeting.upper()

        return {
            "result": greeting,
            "status": "success"
        }
```

---

## @register_module Parameters

### Required Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `module_id` | `str` | Unique identifier (e.g., `'string.hello'`) |

### Recommended Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `version` | `str` | Semantic version (default: `'1.0.0'`) |
| `category` | `str` | Primary category (auto-extracted from `module_id`) |
| `tags` | `List[str]` | Search tags (2-5 recommended) |
| `label` | `str` | Display name (Title Case) |
| `description` | `str` | What the module does |
| `params_schema` | `Dict` | Parameter definitions |
| `output_schema` | `Dict` | Output structure |
| `examples` | `List[Dict]` | Usage examples |

### Visual Parameters (for UI)

| Parameter | Type | Description |
|-----------|------|-------------|
| `icon` | `str` | [Lucide icon](https://lucide.dev/) name |
| `color` | `str` | Hex color code |
| `input_types` | `List[str]` | Accepted input types |
| `output_types` | `List[str]` | Produced output types |

### i18n Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `label_key` | `str` | Translation key for label |
| `description_key` | `str` | Translation key for description |

### Advanced Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout` | `int` | `None` | Execution timeout in seconds |
| `retryable` | `bool` | `False` | Can be retried on failure |
| `max_retries` | `int` | `3` | Maximum retry attempts |
| `requires_credentials` | `bool` | `False` | Needs API keys |
| `author` | `str` | `None` | Module author |
| `license` | `str` | `'MIT'` | License |

---

## Module ID Naming Convention

```
category.subcategory.action
```

### Examples

```
string.reverse      # Simple: category.action
string.case.upper   # With subcategory
data.json.parse     # Third-party data format
api.http.get        # API operations
browser.page.click  # Browser automation
ai.openai.chat      # AI service
```

### Allowed Categories

**Atomic (No external dependencies):**
- `string` - Text manipulation
- `array` - Array operations
- `object` - Object manipulation
- `file` - File operations
- `data` - Data transformation
- `math` - Mathematical operations
- `utility` - Helper functions
- `browser` - Browser automation

**Third-party (External services):**
- `api` - HTTP/REST APIs
- `ai` - AI services (OpenAI, Anthropic, Ollama)
- `notification` - Messaging (Slack, Discord, Email)
- `database` - Database operations
- `cloud` - Cloud storage
- `developer` - Developer tools (GitHub)

---

## params_schema Reference

### Supported Types

```python
params_schema={
    # String input
    'text': {
        'type': 'string',
        'label': 'Text',
        'required': True,
        'placeholder': 'Enter text...',
        'multiline': False  # True for textarea
    },

    # Number input
    'count': {
        'type': 'number',
        'label': 'Count',
        'default': 10,
        'min': 1,
        'max': 100
    },

    # Boolean toggle
    'enabled': {
        'type': 'boolean',
        'label': 'Enabled',
        'default': True
    },

    # Dropdown select
    'format': {
        'type': 'select',
        'label': 'Format',
        'options': [
            {'value': 'json', 'label': 'JSON'},
            {'value': 'xml', 'label': 'XML'},
            {'value': 'csv', 'label': 'CSV'}
        ],
        'default': 'json'
    },

    # Array input
    'items': {
        'type': 'array',
        'label': 'Items',
        'items_type': 'string'
    },

    # Object/JSON input
    'config': {
        'type': 'object',
        'label': 'Configuration'
    }
}
```

---

## BaseModule Methods

Your module class should inherit from `BaseModule` and implement:

### `validate_params(self) -> None`

Extract and validate parameters. Use these helper methods:

```python
def validate_params(self):
    # Required parameter (raises ValueError if missing)
    self.text = self.require_param('text')

    # Optional parameter with default
    self.uppercase = self.get_param('uppercase', False)
    self.timeout = self.get_param('timeout', 30)
```

### `async execute(self) -> Dict[str, Any]`

The main logic. Must be async and return a dict:

```python
async def execute(self) -> Dict[str, Any]:
    # Your logic here
    result = process(self.text)

    return {
        "result": result,
        "status": "success"
    }
```

### Accessing Context

The `context` dict contains shared state:

```python
async def execute(self):
    # Access browser instance (for browser modules)
    browser = self.context.get('browser')
    page = self.context.get('page')

    # Access results from previous steps
    previous_result = self.context.get('step_results', {})
```

---

## Function-Based Modules

For simpler modules, you can use a function instead of a class:

```python
@register_module(
    module_id='string.reverse',
    params_schema={
        'text': {'type': 'string', 'required': True}
    }
)
async def string_reverse(context):
    """Reverse a string"""
    text = context['params']['text']
    return {'result': text[::-1]}
```

---

## Error Handling

Use proper error handling:

```python
async def execute(self) -> Dict[str, Any]:
    try:
        result = await risky_operation()
        return {"result": result, "status": "success"}

    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        raise ValueError(f"Invalid input: {e}")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise RuntimeError(f"Module execution failed: {e}")
```

---

## Testing Your Module

### Unit Test

```python
# tests/modules/test_hello.py

import pytest
from src.core.modules.registry import ModuleRegistry


@pytest.mark.asyncio
async def test_hello_basic():
    result = await ModuleRegistry.execute(
        'string.hello',
        params={'name': 'World'},
        context={}
    )
    assert result['status'] == 'success'
    assert result['result'] == 'Hello, World!'


@pytest.mark.asyncio
async def test_hello_uppercase():
    result = await ModuleRegistry.execute(
        'string.hello',
        params={'name': 'World', 'uppercase': True},
        context={}
    )
    assert result['result'] == 'HELLO, WORLD!'


@pytest.mark.asyncio
async def test_hello_missing_name():
    with pytest.raises(ValueError):
        await ModuleRegistry.execute(
            'string.hello',
            params={},
            context={}
        )
```

### Run Tests

```bash
pytest tests/modules/test_hello.py -v
```

---

## Checklist Before PR

- [ ] Module ID follows `category.action` or `category.subcategory.action`
- [ ] `validate_params()` validates all required parameters
- [ ] `execute()` returns a dict with `result` and `status`
- [ ] Use `logger.debug()` instead of `print()`
- [ ] Use constants from `src/core/constants.py` (no hardcoded values)
- [ ] Use relative imports (e.g., `from ...base import BaseModule`)
- [ ] At least one example in `examples` parameter
- [ ] Tests written for success and error cases
- [ ] No hardcoded API keys or secrets

---

## See Also

- [MODULE_SPECIFICATION.md](MODULE_SPECIFICATION.md) - Complete specification
- [MODULE_QUICK_REFERENCE.md](MODULE_QUICK_REFERENCE.md) - Quick reference
- [WRITING_MODULES.md](WRITING_MODULES.md) - Detailed writing guide
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
