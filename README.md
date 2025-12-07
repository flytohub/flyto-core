# Flyto Core

[![License: Source Available](https://img.shields.io/badge/License-Source%20Available-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

> A Git-native workflow engine and atomic module runtime for building local-first AI agents.

## What is Flyto Core?

Flyto Core is an **open-source workflow automation engine** designed with three principles:

- **Atomic-first** — 127+ fine-grained modules that compose like LEGO bricks
- **Local-first & Git-native** — YAML workflows that version, diff, and test like code
- **Designed for AI automation** — Rich module metadata lets AI understand and compose workflows

## Quick Start

```bash
# Clone the repository
git clone https://github.com/flytohub/flyto-core.git
cd flyto-core

# Install dependencies
pip install -r requirements.txt

# Run your first workflow
python run.py workflows/_test/test_text_reverse.yaml
```

## 30-Second Example

**workflow.yaml**
```yaml
name: Hello World
steps:
  - id: reverse
    module: string.reverse
    params:
      text: "Hello Flyto"

  - id: shout
    module: string.uppercase
    params:
      text: "${reverse.result}"
```

**Run it:**
```bash
python run.py workflow.yaml
# Output: "OTYFL OLLEH"
```

**Or use Python directly:**
```python
import asyncio
from src.core.modules.registry import ModuleRegistry

async def main():
    result = await ModuleRegistry.execute(
        "string.reverse",
        params={"text": "Hello"},
        context={}
    )
    print(result)  # {"result": "olleH"}

asyncio.run(main())
```

## Use Cases

### 🧪 Local AI Agent Lab
Build AI agents that run entirely on your machine with Ollama integration.

```yaml
steps:
  - id: ask_ai
    module: ai.ollama.chat
    params:
      model: llama3
      prompt: "Summarize this: ${input.text}"
```

### 🕷️ Web Automation & Scraping
Automate browsers with the `browser.*` module family.

```yaml
steps:
  - id: browser
    module: browser.launch
    params: { headless: true }

  - id: navigate
    module: browser.goto
    params: { url: "https://example.com" }

  - id: extract
    module: browser.extract
    params: { selector: "h1" }
```

### 🔗 API Orchestration
Chain API calls with built-in retry and error handling.

```yaml
steps:
  - id: fetch
    module: api.http_get
    params:
      url: "https://api.example.com/data"
    retry:
      max_attempts: 3
      delay_ms: 1000
```

### 🏗️ Internal Tooling
Companies can build custom `crm.*`, `billing.*`, `internal.*` modules versioned in Git.

## Four-Level Architecture

| Level | Type | For | Count |
|-------|------|-----|-------|
| **1** | Workflow Templates | Beginners | 6 ready-to-use templates |
| **2** | Atomic Modules | Developers/AI | 127+ fine-grained modules |
| **3** | Composite Modules | Power Users | 9 high-level workflows |
| **4** | Advanced Patterns | Enterprise | 9 resilience patterns |

## Module Categories

| Category | Modules | Examples |
|----------|---------|----------|
| `string.*` | 8 | reverse, split, replace, trim |
| `array.*` | 10 | filter, sort, map, reduce, unique |
| `object.*` | 5 | keys, values, merge, pick |
| `file.*` | 6 | read, write, copy, delete |
| `browser.*` | 9 | launch, goto, click, extract |
| `api.*` | 4+ | http_get, http_post, github |
| `ai.*` | 4 | openai, ollama, anthropic |
| `notification.*` | 4 | slack, discord, telegram, email |

## Why Flyto Core?

### vs. n8n / Zapier
- **Finer granularity** — Atomic modules vs. monolithic nodes
- **Git-native** — Version control your workflows
- **No cloud dependency** — Runs entirely local

### vs. Python Scripts
- **Declarative YAML** — Non-programmers can read and modify
- **Built-in resilience** — Retry, timeout, error handling included
- **Module reuse** — Don't rewrite the same HTTP/browser code

### vs. Airflow / Prefect
- **Lightweight** — No scheduler, database, or infrastructure needed
- **Developer-friendly** — Just YAML + Python, no DAG ceremony
- **AI-ready** — Module metadata designed for LLM consumption

## For Module Authors

Modules use the `@register_module` decorator with rich metadata:

```python
from src.core.modules.registry import register_module
from src.core.modules.base import BaseModule

@register_module(
    module_id='string.reverse',
    version='1.0.0',
    category='string',
    label='Reverse String',
    description='Reverse the characters in a string',

    params_schema={
        'text': {
            'type': 'string',
            'required': True,
            'label': 'Text to reverse'
        }
    },
    output_schema={
        'result': {'type': 'string'}
    }
)
class StringReverseModule(BaseModule):
    def validate_params(self):
        self.text = self.require_param('text')

    async def execute(self):
        return {'result': self.text[::-1]}
```

See **[Module Specification](docs/MODULE_SPECIFICATION.md)** for the complete guide.

## Installation

### Basic
```bash
pip install -r requirements.txt
```

### With Browser Automation
```bash
pip install playwright
playwright install chromium
```

### With AI Integrations
```bash
pip install -r requirements-integrations.txt
```

## Project Structure

```
flyto-core/
├── src/core/
│   ├── modules/
│   │   ├── atomic/        # Level 2: 127+ atomic modules
│   │   ├── composite/     # Level 3: 9 composite modules
│   │   ├── patterns/      # Level 4: 9 advanced patterns
│   │   └── third_party/   # External integrations
│   └── engine/            # Workflow execution engine
├── workflows/
│   └── templates/         # Level 1: Ready-to-use templates
├── docs/                  # Documentation
└── i18n/                  # Internationalization (en, zh, ja)
```

## Documentation

- **[Module Specification](docs/MODULE_SPECIFICATION.md)** — Complete module API reference
- **[Writing Modules](docs/WRITING_MODULES.md)** — Guide to creating custom modules
- **[CLI Reference](docs/CLI.md)** — Command-line options
- **[DSL Reference](docs/DSL.md)** — YAML workflow syntax

## Contributing

We welcome contributions! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for guidelines.

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/flyto-core.git

# Create feature branch
git checkout -b feature/my-module

# Make changes, then submit PR
```

## Security

Report security vulnerabilities via **[security@flyto.dev](mailto:security@flyto.dev)**.
See **[SECURITY.md](SECURITY.md)** for our security policy.

## License

**Source Available License** — Free for non-commercial use.

| Use Case | License Required |
|----------|-----------------|
| Personal projects | Free |
| Education & research | Free |
| Internal business tools | Free |
| Commercial products/services | [Commercial License](LICENSE-COMMERCIAL.md) |

See **[LICENSE](LICENSE)** for complete terms.

For commercial licensing inquiries: licensing@flyto.dev

---

<p align="center">
  <b>Source-available core engine of the Flyto automation platform.</b><br>
  Built for developers. Designed for AI.
</p>

---

*Copyright (c) 2025 Flyto. All Rights Reserved.*
