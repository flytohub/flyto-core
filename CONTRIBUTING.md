# Contributing to Flyto Core

Thank you for your interest in contributing to Flyto Core! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Module Development](#module-development)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Community](#community)

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@flyto.dev.

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- pip package manager

### Development Setup

```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/flyto-core.git
cd flyto-core

# 3. Add upstream remote
git remote add upstream https://github.com/anthropics/flyto-core.git

# 4. Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 5. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies

# 6. Install Playwright (for browser modules)
pip install playwright
playwright install chromium

# 7. Verify setup
python run.py  # Should launch interactive mode
```

## How to Contribute

### Types of Contributions

We welcome many types of contributions:

- **Bug Reports**: Found a bug? Open an issue with a clear description
- **Feature Requests**: Have an idea? Open an issue to discuss it
- **Documentation**: Improve docs, fix typos, add examples
- **Bug Fixes**: Fix issues labeled `good first issue` or `help wanted`
- **New Modules**: Add new atomic modules following our specification
- **Tests**: Improve test coverage
- **Translations**: Add or improve i18n translations

### Finding Something to Work On

1. Check [open issues](../../issues) for bugs and feature requests
2. Look for issues labeled:
   - `good first issue` - Great for newcomers
   - `help wanted` - We need community help
   - `documentation` - Docs improvements needed
3. Check the [project board](../../projects) for planned work

## Module Development

### Design Philosophy

**Atomic Design**: Each module should do ONE thing and do it well.

```python
# GOOD: Single responsibility
@register_module('string.uppercase')
class UppercaseModule(BaseModule):
    """Convert text to uppercase"""
    async def execute(self):
        return {"result": self.text.upper()}

# BAD: Too many responsibilities
@register_module('string.process')
class ProcessModule(BaseModule):
    """Uppercase, lowercase, trim, and reverse text"""  # Too much!
```

### Module Structure

```python
"""
Module description - what this module does.

Keep docstrings in English only.
"""
import logging
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import EnvVars  # Use centralized constants

logger = logging.getLogger(__name__)


@register_module(
    module_id='category.action',           # e.g., 'string.reverse'
    version='1.0.0',
    category='category',                   # e.g., 'string'
    tags=['tag1', 'tag2'],

    # Labels (English defaults)
    label='Action Name',
    label_key='modules.category.action.label',
    description='What this module does',
    description_key='modules.category.action.description',

    # Visual
    icon='IconName',                       # Lucide icon name
    color='#4A90E2',                       # Hex color

    # Type definitions
    input_types=['text'],
    output_types=['text'],

    # Parameters
    params_schema={
        'param_name': {
            'type': 'string',
            'label': 'Parameter Label',
            'description': 'What this parameter does',
            'required': True,
            'default': None
        }
    },

    # Output
    output_schema={
        'result': {'type': 'string'}
    },

    # Examples
    examples=[
        {
            'name': 'Basic usage',
            'params': {'param_name': 'example'}
        }
    ],

    # Metadata
    author='Your Name',
    license='MIT'
)
class YourModule(BaseModule):
    """Module implementation"""

    module_name = "Action Name"
    module_description = "Short description"

    def validate_params(self) -> None:
        """Validate and extract parameters"""
        self.param = self.require_param('param_name')

    async def execute(self) -> Dict[str, Any]:
        """Execute the module logic"""
        result = process(self.param)
        return {
            "result": result,
            "status": "success"
        }
```

### Module Guidelines

1. **No Hardcoded Values**
   ```python
   # BAD
   url = "http://localhost:11434"
   api_key = os.environ.get('OPENAI_API_KEY')

   # GOOD
   from ....constants import OLLAMA_DEFAULT_URL, EnvVars
   url = OLLAMA_DEFAULT_URL
   api_key = os.environ.get(EnvVars.OPENAI_API_KEY)
   ```

2. **Use Logging, Not Print**
   ```python
   # BAD
   print(f"Processing: {data}")

   # GOOD
   logger.debug(f"Processing: {data}")
   ```

3. **Use Relative Imports**
   ```python
   # BAD
   from src.core.modules.base import BaseModule

   # GOOD
   from ...base import BaseModule
   ```

4. **Handle Errors Gracefully**
   ```python
   async def execute(self) -> Dict[str, Any]:
       try:
           result = await risky_operation()
           return {"status": "success", "result": result}
       except SpecificError as e:
           logger.error(f"Operation failed: {e}")
           raise ValueError(f"Operation failed: {e}")
   ```

### Required Reading

Before creating modules, read:

- [MODULE_SPECIFICATION.md](docs/MODULE_SPECIFICATION.md) - Complete specification
- [MODULE_QUICK_REFERENCE.md](docs/MODULE_QUICK_REFERENCE.md) - Quick reference
- [WRITING_MODULES.md](docs/WRITING_MODULES.md) - Step-by-step guide

## Coding Standards

### Code Style

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use [Black](https://black.readthedocs.io/) for code formatting
- Maximum line length: 100 characters
- Use type hints for all function signatures

### Formatting Tools

```bash
# Format code with Black
black src/

# Check with flake8
flake8 src/

# Type checking (optional)
mypy src/
```

### Documentation

- All modules must have docstrings
- Keep documentation in English
- Include examples for complex functionality
- Update relevant docs when changing behavior

### Commit Messages

Follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(modules): add string.titlecase module

fix(browser): handle timeout in page.goto

docs(readme): update installation instructions

refactor(constants): centralize API endpoints
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/modules/test_string.py

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/modules/test_string.py::test_reverse_basic
```

### Writing Tests

```python
import pytest
from src.core.modules.registry import ModuleRegistry


@pytest.mark.asyncio
async def test_string_reverse():
    """Test string reverse module"""
    params = {'text': 'hello'}
    context = {}

    result = await ModuleRegistry.execute(
        'string.reverse',
        params,
        context
    )

    assert result['status'] == 'success'
    assert result['result'] == 'olleh'


@pytest.mark.asyncio
async def test_string_reverse_empty():
    """Test string reverse with empty string"""
    params = {'text': ''}
    context = {}

    result = await ModuleRegistry.execute(
        'string.reverse',
        params,
        context
    )

    assert result['result'] == ''


@pytest.mark.asyncio
async def test_string_reverse_missing_param():
    """Test string reverse with missing parameter"""
    params = {}
    context = {}

    with pytest.raises(ValueError):
        await ModuleRegistry.execute(
            'string.reverse',
            params,
            context
        )
```

### Test Coverage

- Aim for >80% coverage on new code
- Test both success and error cases
- Test edge cases (empty inputs, large inputs, special characters)

## Pull Request Process

### Before Submitting

1. **Update your fork**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow coding standards
   - Add tests for new functionality
   - Update documentation if needed

4. **Run checks locally**
   ```bash
   # Format code
   black src/

   # Run tests
   pytest

   # Check for issues
   flake8 src/
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

### Submitting

1. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template with:
   - Description of changes
   - Related issue numbers
   - Testing performed
   - Screenshots (if UI changes)

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added for new functionality
- [ ] All tests pass locally
- [ ] Documentation updated (if needed)
- [ ] No hardcoded values or secrets
- [ ] Commit messages follow convention
- [ ] PR description is complete

### Review Process

1. A maintainer will review your PR
2. Address any feedback or requested changes
3. Once approved, a maintainer will merge your PR

## Community

### Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and community discussions
- **Documentation**: Check the [docs](docs/) folder

### Communication Guidelines

- Be respectful and inclusive
- Provide context and details in issues
- Search existing issues before creating new ones
- Be patient - maintainers are volunteers

### Recognition

Contributors are recognized in:
- Release notes for significant contributions
- The project's contributors list
- Security advisories (for security researchers)

---

## License

By contributing to Flyto Core, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

Thank you for contributing to Flyto Core!
