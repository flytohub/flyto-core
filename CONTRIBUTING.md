# Contributing to Flyto2

Thank you for your interest in contributing! This guide covers everything you need to know about contributing modules, understanding our design philosophy, and following best practices.

---

## Table of Contents

- [Module Specification (REQUIRED READING)](#module-specification)
- [Getting Started](#getting-started)
- [Atomic Design Philosophy](#atomic-design-philosophy)
- [Internationalization (i18n)](#internationalization-i18n)
- [Module Development](#module-development)
- [Quality Standards](#quality-standards)
- [Testing](#testing)
- [Submission Process](#submission-process)

---

## Module Specification

### ⚠️ REQUIRED READING

**Before creating any module**, you MUST read and follow the Module Specification:

📘 **[Complete Specification](docs/MODULE_SPECIFICATION.md)** - Comprehensive rules and guidelines
📋 **[Quick Reference](docs/MODULE_QUICK_REFERENCE.md)** - Fast lookup guide
🚀 **[Phase 2 Features](docs/MODULE_PHASE2_FEATURES.md)** - Execution control & security features

### Why This Matters

Our module system powers the visual UI. Inconsistent modules break:
- ✗ UI block generation
- ✗ Module connection logic
- ✗ Type compatibility checking
- ✗ Professional appearance

Following the specification ensures:
- ✅ Your module works in the UI
- ✅ Users can connect modules properly
- ✅ Professional quality
- ✅ Faster PR approval

### Quick Checklist

Before submitting a module PR:

- [ ] Read [MODULE_SPECIFICATION.md](docs/MODULE_SPECIFICATION.md)
- [ ] Module ID follows `category.subcategory.action` format
- [ ] All required fields present (17 required)
- [ ] `input_types` and `output_types` declared
- [ ] Label is Title Case, 2-5 words
- [ ] Color is valid hex (#RRGGBB)
- [ ] i18n keys follow pattern: `modules.category.subcategory.action.field`
- [ ] At least 1 working example included
- [ ] **Phase 2**: Added `timeout`, `retryable`, `concurrent_safe` if applicable
- [ ] **Phase 2**: Added security settings (`requires_credentials`, `handles_sensitive_data`)
- [ ] Ran `python scripts/validate_all_modules.py` with no errors
- [ ] Added i18n translations to `i18n/en.json`

### Tools Available

**Create a new module:**
```bash
python scripts/create_module.py \
    --category data \
    --subcategory xml \
    --action parse \
    --label "Parse XML"
```

**Validate your module:**
```bash
python scripts/lint_modules.py src/core/modules/your_module.py
```

**Validate all modules:**
```bash
python scripts/lint_modules.py --strict
```

### Module Connection Example

```python
@register_module(
    module_id='browser.page.screenshot',
    # ... other fields ...

    # Define what types this module accepts
    input_types=['browser_instance'],

    # Define what types this module produces
    output_types=['screenshot', 'image'],

    # Define which modules can send data to this one
    can_receive_from=[
        'browser.instance.launch',
        'browser.page.navigate',
    ],

    # Define which modules can receive this module's output
    can_connect_to=[
        'file.write',
        'cloud.s3.upload',
        'ai.vision.*',
    ],
)
```

---

## Getting Started

### Prerequisites

```bash
# Required
Python 3.8+
pip
git

# Recommended
pytest (for testing)
black (for code formatting)
pylint (for linting)
```

### Setup Development Environment

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/flyto2.git
cd flyto2

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install Playwright browsers
playwright install chromium

# Run tests to verify setup
pytest
```

---

## Atomic Design Philosophy

### Core Principle

**Each module should do ONE thing and do it well.**

Complex workflows are built by combining simple atomic modules, like LEGO blocks.

### Module Categories

#### 1. Browser Control (`core.browser.*`)
- `core.browser.launch` - Launch browser
- `core.browser.goto` - Navigate to URL
- `core.browser.close` - Close browser
- `core.browser.screenshot` - Take screenshot
- `core.browser.wait` - Wait for condition

#### 2. Element Operations (`core.element.*`)
- `core.element.find` - Find element(s) by selector
- `core.element.click` - Click element
- `core.element.type` - Type text into element
- `core.element.get_text` - Get element text
- `core.element.get_attribute` - Get element attribute

#### 3. Flow Control (`core.flow.*`)
- `core.flow.loop` - Loop through items
- `core.flow.condition` - If/else branching
- `core.flow.retry` - Retry on failure
- `core.flow.parallel` - Run steps in parallel

#### 4. Data Operations (`core.data.*`)
- `core.data.extract` - Extract data from structure
- `core.data.transform` - Transform data
- `core.data.filter` - Filter data

### Example: Google Search (Atomic Way)

Instead of a monolithic "google_search" module, compose atomic modules:

```yaml
steps:
  # 1. Launch browser
  - id: browser
    module: core.browser.launch
    params:
      headless: false

  # 2. Navigate
  - id: nav
    module: core.browser.goto
    params:
      url: "https://www.google.com"

  # 3. Find search input
  - id: search_input
    module: core.element.find
    params:
      selector: 'input[name="q"]'

  # 4. Type keyword
  - id: type
    module: core.element.type
    params:
      element_id: "${search_input.element_id}"
      text: "${params.keyword}"

  # 5. Press Enter
  - id: submit
    module: core.element.press_key
    params:
      element_id: "${search_input.element_id}"
      key: "Enter"

  # 6. Loop through results
  - id: extract
    module: core.flow.loop
    params:
      items: "${results.element_ids}"
      steps:
        - id: title
          module: core.element.get_text
          params:
            element_id: "${item}"
```

### Benefits

1. **Flexibility** - Combine modules in any way
2. **Reusability** - Each module useful in many contexts
3. **Testability** - Easy to test small modules
4. **Community** - Easy for others to contribute
5. **No limits** - Can build anything

### Guidelines for Module Authors

1. **Single Responsibility** - One module = one action
2. **No Business Logic** - Keep modules generic
3. **Clear Inputs/Outputs** - Well-defined interface
4. **Composable** - Works with other modules
5. **Documented** - Clear examples

---

## Internationalization (i18n)

### Design Principle

**Code is in English, translations are in i18n files.**

Module code should never contain non-English text. Instead, use i18n keys that reference translation files.

### Module Registration with i18n

#### English Only (Simplest)

For modules that don't need translation:

```python
@register_module(
    module_id='core.browser.launch',
    label='Launch Browser',
    description='Launch a new browser instance',
    # ... other params
)
class BrowserLaunchModule(BaseModule):
    pass
```

#### With i18n Keys (Recommended for UI)

For modules that need translation in UI:

```python
@register_module(
    module_id='core.browser.launch',
    label='Launch Browser',           # Default English
    label_key='modules.browser.launch.label',  # i18n key
    description='Launch a new browser instance',
    description_key='modules.browser.launch.description',
    params_schema={
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'label_key': 'modules.browser.launch.params.headless.label',
            'description': 'Run browser without UI',
            'description_key': 'modules.browser.launch.params.headless.description',
            'default': False
        }
    }
)
class BrowserLaunchModule(BaseModule):
    pass
```

### Translation Files

Translation files live in `i18n/` directory:

```
i18n/
├── en.json  (English - optional, uses code defaults)
├── zh.json  (Chinese)
├── ja.json  (Japanese)
└── ...
```

#### Example: i18n/en.json

```json
{
  "modules": {
    "browser": {
      "launch": {
        "label": "Launch Browser",
        "description": "Launch a new browser instance",
        "params": {
          "headless": {
            "label": "Headless Mode",
            "description": "Run browser without UI (headless mode)"
          }
        }
      }
    }
  }
}
```

**Note:** While the example shows English, the i18n system supports multiple languages (zh, ja, etc.). Translation files are optional - the system falls back to English defaults in code.

### i18n Best Practices

1. **Always provide English defaults** in code
2. **Use i18n keys** for anything shown in UI
3. **Never hardcode non-English** text in Python files
4. **Namespace keys** logically: `modules.{category}.{action}.{field}`
5. **Keep translations in sync** with code

---

## Module Development

### Naming Convention

#### Format
```
{namespace}.{vendor}.{action}
```

#### Good Examples
- `core.browser.launch` - Core namespace, browser category, launch action
- `ai.openai.chat` - AI namespace, OpenAI vendor, chat action
- `cloud.aws.s3.upload` - Cloud namespace, AWS vendor, S3 service, upload action

#### Bad Examples
- `openai_chat` - No namespace
- `ai.chat` - Missing vendor (for non-core modules)
- `AI.OpenAI.Chat` - Should be lowercase
- `ai-openai-chat` - Use dots, not dashes

### Module Template

```python
"""
{Module Description}

This module provides {functionality description}.
"""
from typing import Any
from .base import BaseModule
from .registry import register_module


@register_module(
    module_id='core.{category}.{action}',
    version='1.0.0',
    category='{category}',
    tags=['{tag1}', '{tag2}', '{tag3}'],

    # English defaults with i18n keys
    label='{English Label}',
    label_key='modules.{category}.{action}.label',
    description='{English description}',
    description_key='modules.{category}.{action}.description',

    # Visual
    icon='{IconName}',
    color='#{HexColor}',

    # Parameters
    params_schema={
        'param_name': {
            'type': 'string',
            'label': 'Parameter Label',
            'label_key': 'modules.{category}.{action}.params.param_name.label',
            'description': 'What this parameter does',
            'description_key': 'modules.{category}.{action}.params.param_name.description',
            'placeholder': 'example value',
            'required': True,
            'default': None
        }
    },

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'data': {'type': 'object'}
    },

    # Examples
    examples=[
        {
            'name': 'Basic usage',
            'params': {
                'param_name': 'example value'
            }
        }
    ],

    # Metadata
    author='Your Name',
    license='MIT'
)
class YourModule(BaseModule):
    """Module implementation - English docstrings only"""

    module_name = "{Module Name}"
    module_description = "{Short description}"
    required_permission = "{permission.name}"

    def validate_params(self):
        """Validate input parameters"""
        if 'param_name' not in self.params:
            raise ValueError("Missing required parameter: param_name")
        self.param = self.params['param_name']

    async def execute(self) -> Any:
        """Execute the module logic"""
        # Your implementation here
        result = await some_operation(self.param)

        return {
            "status": "success",
            "data": result
        }
```

### Real-World Example

```python
"""
Browser Launch Module

Launch a new browser instance with Playwright.
Supports: Chromium, Firefox, WebKit
"""
from typing import Any
from .base import BaseModule
from .registry import register_module


@register_module(
    module_id='core.browser.launch',
    version='1.0.0',
    category='browser',
    tags=['browser', 'automation', 'setup'],

    label='Launch Browser',
    label_key='modules.browser.launch.label',
    description='Launch a new browser instance with Playwright',
    description_key='modules.browser.launch.description',

    icon='Monitor',
    color='#4A90E2',

    params_schema={
        'headless': {
            'type': 'boolean',
            'label': 'Headless Mode',
            'label_key': 'modules.browser.launch.params.headless.label',
            'description': 'Run browser in headless mode (no UI)',
            'description_key': 'modules.browser.launch.params.headless.description',
            'default': False,
            'required': False
        }
    },

    output_schema={
        'status': {'type': 'string'},
        'message': {'type': 'string'}
    },

    examples=[
        {
            'name': 'Launch headless browser',
            'params': {'headless': True}
        },
        {
            'name': 'Launch visible browser',
            'params': {'headless': False}
        }
    ],

    author='Workflow Engine Team',
    license='MIT'
)
class BrowserLaunchModule(BaseModule):
    """Launch Browser Module"""

    module_name = "Launch Browser"
    module_description = "Launch a new browser instance"
    required_permission = "browser.launch"

    def validate_params(self):
        self.headless = self.params.get('headless', False)

    async def execute(self) -> Any:
        from src.core.browser.driver import BrowserDriver

        driver = BrowserDriver(headless=self.headless)
        await driver.launch()

        self.context['browser'] = driver

        return {"status": "success", "message": "Browser launched successfully"}
```

---

## Quality Standards

Before submitting your module:

- [ ] Follows naming convention (`{namespace}.{category}.{action}`)
- [ ] i18n support with keys (English defaults required)
- [ ] Complete params_schema with i18n keys
- [ ] At least 2 usage examples
- [ ] Error handling for all edge cases
- [ ] Input validation in `validate_params()`
- [ ] Docstrings in English only
- [ ] Unit tests (>80% coverage)
- [ ] No Chinese in code (only in i18n translation files)
- [ ] No hardcoded secrets (use environment variables)
- [ ] Type hints for all methods
- [ ] Async/await where applicable
- [ ] Follows atomic design (single responsibility)

---

## Testing

### Writing Tests

Create a test file in `tests/modules/test_{your_module}.py`:

```python
import pytest
from src.core.modules.registry import ModuleRegistry


@pytest.mark.asyncio
async def test_browser_launch_basic():
    """Test basic browser launch"""
    params = {
        'headless': True
    }
    context = {}

    result = await ModuleRegistry.execute(
        'core.browser.launch',
        params,
        context
    )

    assert result['status'] == 'success'
    assert 'browser' in context


@pytest.mark.asyncio
async def test_module_atomic_composition():
    """Test composing atomic modules"""
    # Test that modules can be chained together
    context = {}

    # Step 1: Launch browser
    await ModuleRegistry.execute(
        'core.browser.launch',
        {'headless': True},
        context
    )

    # Step 2: Navigate
    result = await ModuleRegistry.execute(
        'core.browser.goto',
        {'url': 'https://example.com'},
        context
    )

    assert result['status'] == 'success'
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/modules/test_browser.py

# With coverage
pytest --cov=src --cov-report=html

# Watch mode
pytest-watch
```

---

## Submission Process

### 1. Fork and Branch

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/flyto2.git
cd flyto2

# Create feature branch
git checkout -b module/{namespace}-{category}-{action}
```

### 2. Develop

```bash
# Make your changes
# - Add module code (atomic design)
# - Add i18n keys
# - Write tests
# - Update translation files

# Format code
black src/
pylint src/

# Run tests
pytest
```

### 3. Commit

```bash
git add .
git commit -m "Add module: {namespace}.{category}.{action}

- Implement {action} for {category}
- Follow atomic design principle
- Add i18n support (en, zh, ja)
- Add comprehensive tests
- Include documentation and examples"
```

### 4. Push and PR

```bash
# Push to your fork
git push origin module/{namespace}-{category}-{action}

# Create Pull Request on GitHub
```

### PR Checklist

- [ ] Follows atomic design (single responsibility)
- [ ] Uses i18n keys (English defaults + translation keys)
- [ ] No Chinese in Python code
- [ ] Complete params_schema with i18n
- [ ] At least 2 examples
- [ ] Error handling
- [ ] Unit tests (>80% coverage)
- [ ] Updated i18n translation files
- [ ] No hardcoded secrets
- [ ] **Phase 2: Execution settings configured**
  - [ ] `timeout` set if module can hang (API calls, browser operations, network requests)
  - [ ] `retryable` enabled if temporary failures expected (network errors, rate limits)
  - [ ] `max_retries` appropriate for use case (typically 2-3)
  - [ ] `concurrent_safe` set to `False` if uses shared resources (browser, files, global state)
- [ ] **Phase 2: Security settings declared**
  - [ ] `requires_credentials` set to `True` if needs API keys or authentication
  - [ ] `handles_sensitive_data` set to `True` if processes PII, passwords, or user data
  - [ ] `required_permissions` list all permissions needed (e.g., `['network.access', 'file.write']`)
- [ ] Ran `python scripts/validate_all_modules.py` with no errors

---

## Getting Help

- **GitHub Issues**: [Report bugs or request features](https://github.com/flytohub/flyto2/issues)
- **Discussions**: [Ask questions](https://github.com/flytohub/flyto2/discussions)

---

## Repository Maintenance (For Maintainers)

### GitHub Repository Settings

**Repository Description:**
```
Git-native workflow automation. Browser + AI + APIs in YAML. MIT open source engine with free visual builder.
```

**Recommended Topics (max 20):**
```
workflow-automation, workflow-engine, automation, playwright, yaml,
git-native, browser-automation, python, ai-integration, openai,
web-scraping, data-pipeline, devops, api-integration, n8n-alternative,
zapier-alternative, airflow, asyncio, anthropic-claude, ci-cd
```

**Features to Enable:**
- ✅ Wikis (for community documentation)
- ✅ Issues (for bug reports and feature requests)
- ✅ Discussions (for Q&A and community)
- ✅ Projects (for roadmap tracking)

### Social Media Card Text

```
Flyto2 - Git-Native Workflow Automation

Write automation workflows in YAML. Version control with Git. Deploy anywhere.

✅ Browser automation (Playwright)
✅ AI integrations (OpenAI, Claude)
✅ API connectors (Slack, GitHub, AWS)
✅ MIT open source engine

Like n8n, but Git-first.
```

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing!**

