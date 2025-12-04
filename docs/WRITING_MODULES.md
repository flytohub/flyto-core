# Writing Custom Modules for Flyto2

This guide covers everything you need to know to create your own modules for Flyto2.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Module Basics](#module-basics)
- [Step-by-Step Tutorial](#step-by-step-tutorial)
- [Module Registration](#module-registration)
- [Input/Output Conventions](#inputoutput-conventions)
- [Error Handling](#error-handling)
- [Testing Your Module](#testing-your-module)
- [Publishing Your Module](#publishing-your-module)

---

## Quick Start

**The simplest possible module:**

```python
from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module

@register_module(
    module_id='custom.hello.greet',
    label='Greet User',
    description='Print a greeting message'
)
class HelloModule(BaseModule):
    """A simple greeting module"""

    async def execute(self):
        name = self.params.get('name', 'World')
        message = f"Hello, {name}!"

        return {
            "message": message,
            "status": "success"
        }
```

**Use it in a workflow:**

```yaml
steps:
  - id: greet
    module: custom.hello.greet
    params:
      name: "Alice"

output:
  greeting: "${greet.message}"
```

---

## Module Basics

### Core Principles

1. **One module = One action** - Keep modules focused and atomic
2. **Pure functions** - Same input → same output (when possible)
3. **Clear contracts** - Well-defined inputs and outputs
4. **No side effects** - Avoid global state, prefer explicit parameters
5. **Composable** - Modules should work well with other modules

### Module Lifecycle

```
1. Registration → @register_module decorator
2. Validation → validate_params() called by engine
3. Execution → execute() called by engine
4. Output → Return dict stored in steps.<id>.output
```

---

## Step-by-Step Tutorial

### 1. Create Your Module File

Create a new file in `src/core/modules/` (or your custom modules directory):

```bash
# For core modules
touch src/core/modules/my_custom_module.py

# For third-party modules
mkdir -p modules/custom
touch modules/custom/my_module.py
```

### 2. Import Required Classes

```python
from typing import Any, Dict
from src.core.modules.base import BaseModule
from src.core.modules.registry import register_module
```

### 3. Define Your Module Class

```python
@register_module(
    module_id='custom.text.uppercase',
    version='1.0.0',
    category='text',
    tags=['text', 'transform', 'string'],

    # Display metadata
    label='Convert to Uppercase',
    label_key='modules.text.uppercase.label',
    description='Convert text to uppercase',
    description_key='modules.text.uppercase.description',

    # Visual metadata (for UI)
    icon='Type',
    color='#6366F1',

    # Parameter schema
    params_schema={
        'text': {
            'type': 'string',
            'label': 'Input Text',
            'description': 'The text to convert',
            'required': True,
            'placeholder': 'enter text here'
        }
    },

    # Output schema
    output_schema={
        'result': {'type': 'string'},
        'length': {'type': 'number'}
    },

    # Usage examples
    examples=[
        {
            'name': 'Basic usage',
            'params': {
                'text': 'hello world'
            },
            'expected_output': {
                'result': 'HELLO WORLD',
                'length': 11
            }
        }
    ],

    # Metadata
    author='Your Name',
    license='MIT'
)
class UppercaseModule(BaseModule):
    """Convert text to uppercase"""

    def validate_params(self):
        """Validate input parameters before execution"""
        if 'text' not in self.params:
            raise ValueError("Missing required parameter: text")

        if not isinstance(self.params['text'], str):
            raise TypeError("Parameter 'text' must be a string")

        # Store validated params as instance variables
        self.text = self.params['text']

    async def execute(self) -> Dict[str, Any]:
        """Execute the module logic"""
        result = self.text.upper()

        return {
            "result": result,
            "length": len(result),
            "status": "success"
        }
```

### 4. Register in NAMESPACES.yaml

Add your module to the taxonomy:

```yaml
custom:
  text:
    - id: uppercase
      description: Convert text to uppercase
      params: [text]
```

### 5. Use in a Workflow

```yaml
name: "Text Transformation Test"

params:
  - name: user_input
    type: string
    required: true

steps:
  - id: transform
    module: custom.text.uppercase
    params:
      text: "${params.user_input}"

output:
  original: "${params.user_input}"
  transformed: "${transform.result}"
```

---

## Module Registration

### @register_module Decorator

The `@register_module` decorator registers your module with the engine and provides metadata for the UI.

**Required fields:**
- `module_id` (string) - Unique identifier in format `namespace.category.action`
- `label` (string) - Human-readable name
- `description` (string) - What the module does

**Recommended fields:**
- `params_schema` (dict) - Parameter definitions
- `output_schema` (dict) - Output structure
- `examples` (list) - Usage examples
- `tags` (list) - For search/filtering
- `version` (string) - Module version

**Optional fields:**
- `label_key`, `description_key` - i18n keys
- `icon`, `color` - UI visual metadata
- `author`, `license` - Attribution

### Naming Conventions

**Module ID format:** `{namespace}.{category}.{action}`

**Good examples:**
- `core.browser.launch`
- `api.http.post`
- `ai.openai.chat`
- `custom.text.uppercase`

**Bad examples:**
- `launch_browser` (no namespace)
- `core.LaunchBrowser` (use lowercase)
- `core-browser-launch` (use dots, not dashes)

---

## Input/Output Conventions

### Input Parameters

Access parameters via `self.params`:

```python
async def execute(self):
    url = self.params.get('url')
    headers = self.params.get('headers', {})  # with default
    timeout = self.params.get('timeout_ms', 5000)
```

### Parameter Validation

Always validate in `validate_params()`:

```python
def validate_params(self):
    # Check required params
    if 'url' not in self.params:
        raise ValueError("Missing required parameter: url")

    # Type validation
    if not isinstance(self.params['url'], str):
        raise TypeError("Parameter 'url' must be a string")

    # Value validation
    if not self.params['url'].startswith('http'):
        raise ValueError("URL must start with http:// or https://")

    # Store validated params
    self.url = self.params['url']
```

### Output Format

Always return a dictionary from `execute()`:

```python
async def execute(self) -> Dict[str, Any]:
    # Your logic here
    result = do_something()

    # Return dict - this becomes steps.<id>.output
    return {
        "data": result,
        "status": "success",
        "timestamp": datetime.now().isoformat()
    }
```

**The returned dict is accessible in workflows as:**
- `${<step_id>.data}`
- `${<step_id>.status}`
- `${<step_id>.timestamp}`

### Context and State

Access shared context via `self.context`:

```python
async def execute(self):
    # Get browser instance from previous step
    browser = self.context.get('browser')

    # Your logic
    result = await browser.goto('https://example.com')

    # Store in context for next steps
    self.context['current_url'] = 'https://example.com'

    return {"status": "success"}
```

---

## Error Handling

### Raising Errors

Use standard Python exceptions:

```python
async def execute(self):
    if not self.is_valid():
        raise ValueError("Invalid input data")

    try:
        result = await api_call()
    except TimeoutError:
        raise TimeoutError("API request timed out after 5s")
    except ConnectionError as e:
        raise ConnectionError(f"Failed to connect: {str(e)}")

    return {"data": result}
```

### Error Types

Common exceptions to use:

| Exception | When to Use |
|-----------|-------------|
| `ValueError` | Invalid parameter values |
| `TypeError` | Wrong parameter types |
| `TimeoutError` | Operation timed out |
| `ConnectionError` | Network/connection issues |
| `FileNotFoundError` | Missing files |
| `PermissionError` | Access denied |
| `RuntimeError` | General runtime errors |

### Retry Support

The engine handles retries automatically if configured in the workflow:

```yaml
steps:
  - id: api_call
    module: api.http.get
    params:
      url: "https://api.example.com"
    retry:
      max_attempts: 3
      delay_ms: 1000
      backoff: "exponential"
      retry_on:
        - "TimeoutError"
        - "ConnectionError"
```

---

## Testing Your Module

### Unit Test Template

Create a test file: `tests/modules/test_my_module.py`

```python
import pytest
from src.core.modules.registry import ModuleRegistry

@pytest.mark.asyncio
async def test_uppercase_basic():
    """Test basic uppercase conversion"""
    params = {'text': 'hello'}
    context = {}

    result = await ModuleRegistry.execute(
        'custom.text.uppercase',
        params,
        context
    )

    assert result['result'] == 'HELLO'
    assert result['length'] == 5
    assert result['status'] == 'success'

@pytest.mark.asyncio
async def test_uppercase_empty_string():
    """Test with empty string"""
    params = {'text': ''}
    context = {}

    result = await ModuleRegistry.execute(
        'custom.text.uppercase',
        params,
        context
    )

    assert result['result'] == ''
    assert result['length'] == 0

@pytest.mark.asyncio
async def test_uppercase_missing_param():
    """Test missing required parameter"""
    params = {}
    context = {}

    with pytest.raises(ValueError, match="Missing required parameter"):
        await ModuleRegistry.execute(
            'custom.text.uppercase',
            params,
            context
        )
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/modules/test_my_module.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/modules/test_my_module.py::test_uppercase_basic
```

---

## Publishing Your Module

### 1. For Core Modules (Contributing to Flyto2)

Follow the [CONTRIBUTING.md](../CONTRIBUTING.md) guide:

1. Fork the repository
2. Create a feature branch: `git checkout -b module/custom-text-uppercase`
3. Add your module to `src/core/modules/`
4. Add tests to `tests/modules/`
5. Update `NAMESPACES.yaml`
6. Add i18n keys to `i18n/*.json`
7. Submit a Pull Request

### 2. For Third-Party Modules

Create a separate package:

```
my-flyto2-modules/
├── setup.py
├── README.md
├── modules/
│   └── my_custom_modules.py
└── tests/
    └── test_my_modules.py
```

**setup.py:**
```python
from setuptools import setup, find_packages

setup(
    name='flyto2-custom-modules',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'flyto2>=1.0.0',
    ],
    entry_points={
        'flyto2.modules': [
            'custom = modules.my_custom_modules',
        ],
    },
)
```

Users can install via:
```bash
pip install flyto2-custom-modules
```

---

## Advanced Topics

### Async Operations

Modules can be fully async:

```python
async def execute(self):
    # Async HTTP request
    async with aiohttp.ClientSession() as session:
        async with session.get(self.url) as response:
            data = await response.json()

    return {"data": data}
```

### Using Third-Party Libraries

Install dependencies separately:

```python
# In your module
try:
    import redis
except ImportError:
    raise ImportError(
        "Redis module requires 'redis' package. "
        "Install with: pip install redis"
    )

async def execute(self):
    r = redis.Redis(host=self.host, port=self.port)
    value = r.get(self.key)
    return {"value": value}
```

### Module Composition

Modules can call other modules:

```python
from src.core.modules.registry import ModuleRegistry

async def execute(self):
    # Call another module
    http_result = await ModuleRegistry.execute(
        'api.http.get',
        {'url': self.params['api_url']},
        self.context
    )

    # Process result
    data = http_result['data']
    processed = self.process(data)

    return {"result": processed}
```

---

## Best Practices

1. **Keep it atomic** - One module should do one thing well
2. **Validate early** - Check all inputs in `validate_params()`
3. **Clear errors** - Use descriptive error messages
4. **Type hints** - Use Python type hints for better IDE support
5. **Document well** - Add docstrings and examples
6. **Test thoroughly** - Aim for >80% test coverage
7. **Follow conventions** - Use standard naming and output formats
8. **No secrets in code** - Use environment variables or parameters

---

## Examples

See real module implementations in:
- [`src/core/modules/browser_modules.py`](../src/core/modules/browser_modules.py) - Browser automation
- [`src/core/modules/api_modules.py`](../src/core/modules/api_modules.py) - HTTP/API modules
- [`src/core/modules/flow_modules.py`](../src/core/modules/flow_modules.py) - Flow control

---

## Getting Help

- **GitHub Issues**: [Report bugs](https://github.com/flytohub/flyto2/issues)
- **Discussions**: [Ask questions](https://github.com/flytohub/flyto2/discussions)
- **Contributing Guide**: [CONTRIBUTING.md](../CONTRIBUTING.md)

---

**Happy module building!** 🚀
