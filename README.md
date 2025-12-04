# Flyto Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

**Open-source YAML workflow automation engine.** Build automation pipelines with 127+ atomic modules - no code required.

## The Problem

Building automation workflows today is painful:

- **Low-code platforms** lock you into proprietary formats and vendor ecosystems
- **Scripting** requires programming knowledge and results in unmaintainable code
- **Enterprise tools** are expensive and over-engineered for simple tasks
- **No version control** - most tools don't play well with Git

## The Solution

Flyto Core is a **YAML-based workflow engine** that treats automation as configuration:

- **Human-readable YAML** - Anyone can read and understand workflows
- **Git-native** - Version control, code review, and CI/CD integration
- **127+ atomic modules** - Compose complex workflows from simple building blocks
- **Zero vendor lock-in** - MIT licensed, runs anywhere Python runs
- **Extensible** - Write custom modules in Python

## Quick Start

```bash
# Clone the repository
git clone https://github.com/anthropics/flyto-core.git
cd flyto-core

# Install dependencies
pip install -r requirements.txt

# Run your first workflow
python run.py workflows/_test/test_text_reverse.yaml
```

## Example Workflow

Create `hello.yaml`:

```yaml
name: "Hello World"
description: "A simple text processing workflow"

steps:
  - id: reverse_text
    module: string.reverse
    params:
      text: "Hello World"

  - id: uppercase
    module: string.uppercase
    params:
      text: "${reverse_text.result}"
```

Run it:

```bash
python run.py hello.yaml
# Output: { "result": "DLROW OLLEH" }
```

## Core Features

### Atomic Module Design

Every module does **one thing well**. Complex workflows emerge from composing simple, tested modules:

```yaml
steps:
  # Launch browser
  - id: browser
    module: browser.launch
    params:
      headless: true

  # Navigate to page
  - id: navigate
    module: browser.goto
    params:
      url: "https://example.com"

  # Extract data
  - id: extract
    module: browser.extract
    params:
      selector: "h1"
```

### Variable Resolution

Reference outputs from previous steps using `${step_id.field}` syntax:

```yaml
steps:
  - id: fetch_data
    module: api.http_get
    params:
      url: "https://api.example.com/users"

  - id: process
    module: array.filter
    params:
      items: "${fetch_data.data}"
      condition: "item.active == true"
```

### Built-in Error Handling

```yaml
steps:
  - id: risky_operation
    module: api.http_post
    params:
      url: "https://api.example.com/submit"
    retry:
      max_attempts: 3
      delay_ms: 1000
    on_error: continue  # or: stop, skip
```

## Available Modules

**127+ modules** across multiple categories:

| Category | Modules | Description |
|----------|---------|-------------|
| `string.*` | 8 | Text manipulation (split, replace, trim, reverse) |
| `array.*` | 10 | Array operations (filter, sort, map, reduce, unique) |
| `object.*` | 5 | Object manipulation (keys, values, merge, pick) |
| `file.*` | 6 | File system (read, write, copy, move, delete) |
| `datetime.*` | 4 | Date/time operations (parse, format, add, subtract) |
| `math.*` | 7 | Mathematical operations (calculate, round, abs) |
| `data.*` | 5 | Data parsing (json, csv, xml) |
| `browser.*` | 9 | Browser automation via Playwright |
| `api.*` | 4 | HTTP requests (GET, POST, PUT, DELETE) |
| `utility.*` | 7 | Utilities (delay, random, hash) |
| `ai.*` | 4 | AI integrations (OpenAI, Anthropic, Ollama) |

View all modules:
```bash
python run.py  # Interactive mode → "List modules"
```

## Installation

### Requirements

- Python 3.8 or higher
- pip package manager

### Basic Installation

```bash
pip install -r requirements.txt
```

### Browser Automation (Optional)

For browser modules (`browser.*`):

```bash
pip install playwright
playwright install chromium
```

### Third-Party Integrations (Optional)

For AI and API integrations:

```bash
pip install -r requirements-integrations.txt
```

## Usage

### Command Line

```bash
# Run a workflow file
python run.py workflow.yaml

# Pass parameters
python run.py workflow.yaml --params '{"url": "https://example.com"}'

# Interactive mode
python run.py
```

### Programmatic Usage

```python
import asyncio
from src.core.engine.workflow_engine import WorkflowEngine

workflow = {
    "name": "Example",
    "steps": [
        {
            "id": "step1",
            "module": "string.reverse",
            "params": {"text": "hello"}
        }
    ]
}

engine = WorkflowEngine(workflow)
result = asyncio.run(engine.execute())
print(result)  # {"result": "olleh"}
```

## Project Structure

```
flyto-core/
├── run.py                  # CLI entry point
├── src/
│   ├── cli/                # Command-line interface
│   └── core/
│       ├── constants.py    # Centralized configuration
│       ├── utils.py        # Shared utilities
│       ├── engine/         # Workflow execution engine
│       ├── browser/        # Playwright integration
│       └── modules/
│           ├── atomic/     # 127+ atomic modules
│           └── third_party/# External service integrations
├── workflows/              # Example workflows
├── i18n/                   # Internationalization (en, zh, ja)
└── docs/                   # Documentation
```

## Documentation

- **[Module Specification](docs/MODULE_SPECIFICATION.md)** - Complete module API reference
- **[Writing Modules](docs/WRITING_MODULES.md)** - Guide to creating custom modules
- **[CLI Reference](docs/CLI.md)** - Command-line options and usage
- **[DSL Reference](docs/DSL.md)** - YAML workflow syntax

## Use Cases

- **Web Scraping** - Extract data from websites with browser automation
- **Data Pipelines** - Transform and process data through multiple stages
- **API Orchestration** - Chain multiple API calls with error handling
- **Automated Testing** - Build end-to-end test workflows
- **DevOps Automation** - Automate deployment and infrastructure tasks
- **AI Workflows** - Integrate LLMs into automated pipelines

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-module`)
3. Make your changes following our [coding standards](CONTRIBUTING.md#quality-standards)
4. Write tests for new functionality
5. Submit a pull request

## Security

For security concerns, please see our [Security Policy](SECURITY.md).

**Do not** report security vulnerabilities through public GitHub issues.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 Flyto

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

## Acknowledgments

- [Playwright](https://playwright.dev/) - Browser automation
- [PyYAML](https://pyyaml.org/) - YAML parsing
- [aiohttp](https://docs.aiohttp.org/) - Async HTTP client

---

**Built with clarity. Designed for automation.**
