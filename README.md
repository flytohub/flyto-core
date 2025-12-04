# Flyto Core

> Open-source YAML-based workflow automation engine

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)

## Overview

Flyto Core is a lightweight, modular workflow engine that executes YAML-defined workflows. It provides 180+ atomic modules for browser automation, data processing, API integration, and more.

## Features

- **YAML Workflows**: Define automation tasks in simple YAML files
- **180+ Atomic Modules**: Browser, data, file, API, and utility operations
- **Variable Resolution**: Use `${variable}` syntax for dynamic values
- **Multi-language**: i18n support (English, Chinese, Japanese)
- **Extensible**: Easy to add custom modules

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/flytohub/flyto-core.git
cd flyto-core

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Usage

```bash
# Interactive mode (select workflow from menu)
python -m src.cli.main

# Run a specific workflow
python -m src.cli.main workflows/example.yaml

# Run with parameters
python -m src.cli.main workflow.yaml --params '{"keyword":"nodejs"}'
python -m src.cli.main workflow.yaml --params-file params.json
python -m src.cli.main workflow.yaml --param keyword=nodejs --param max=20
```

## Workflow Example

```yaml
id: google_search
version: 1
name: Google Search Top 10
description: Search Google and extract top 10 results

params:
  keyword:
    type: string
    required: true
    description: Search keyword

steps:
  - id: launch
    module: browser.launch
    params:
      headless: true

  - id: search
    module: browser.goto
    params:
      url: "https://www.google.com/search?q=${keyword}"

  - id: extract
    module: browser.extract
    params:
      selector: "div.g"
      fields:
        - name: title
          selector: "h3"
        - name: url
          selector: "a"
          attribute: href
      limit: 10

  - id: close
    module: browser.close
```

## Module Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `browser.*` | Browser automation | launch, goto, click, type, extract |
| `array.*` | Array operations | filter, map, sort, unique, chunk |
| `string.*` | String manipulation | split, replace, trim, lowercase |
| `math.*` | Mathematical operations | calculate, abs, ceil, round |
| `file.*` | File operations | read, write, copy, delete |
| `datetime.*` | Date/time handling | parse, format, add, now |
| `utility.*` | Utility functions | delay, hash, random |
| `api.*` | API integration | http, webhook, graphql |

## Project Structure

```
flyto-core/
├── src/
│   ├── cli/              # CLI interface
│   │   └── main.py       # Entry point
│   └── core/
│       ├── engine/       # Workflow execution engine
│       ├── modules/      # Atomic modules (180+)
│       │   ├── atomic/   # Core atomic modules
│       │   └── third_party/  # Integration modules
│       └── browser/      # Playwright driver
├── workflows/            # Example workflows
├── i18n/                 # Internationalization
├── requirements.txt      # Core dependencies
└── requirements-integrations.txt  # Optional integrations
```

## Requirements

- Python 3.8+
- Playwright
- PyYAML
- Pydantic

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Related Projects

- [flyto-cloud](https://github.com/flytohub/flyto-cloud) - Web UI and SaaS platform
- [flyto-pro](https://github.com/flytohub/flyto-pro) - AI-powered evolution engine (private)
