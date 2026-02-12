# Flyto Core

[![PyPI version](https://img.shields.io/pypi/v/flyto-core.svg)](https://pypi.org/project/flyto-core/)
[![License: Source Available](https://img.shields.io/badge/License-Source%20Available-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

<!-- mcp-name: io.github.flytohub/flyto-core -->

> The open-source execution engine for AI agents. 300+ atomic modules, MCP-native, secure by default.

## What is Flyto Core?

Flyto Core is an **open-source workflow automation engine** designed with three principles:

- **Atomic-first** — 300+ fine-grained modules that compose like LEGO bricks
- **Local-first & Git-native** — YAML workflows that version, diff, and test like code
- **Designed for AI automation** — Rich module metadata lets AI understand and compose workflows

## Quick Start

```bash
pip install flyto-core
```

Or from source:
```bash
git clone https://github.com/flytohub/flyto-core.git
cd flyto-core
pip install -r requirements.txt
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
# Output: "OTYLF OLLEH"
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
    print(result)  # {"ok": True, "data": {"result": "olleH", ...}}

asyncio.run(main())
```

## Use Cases

### Local AI Agent Lab
Build AI agents that run entirely on your machine with Ollama integration.

```yaml
steps:
  - id: ask_ai
    module: ai.ollama.chat
    params:
      model: llama3
      prompt: "Summarize this: ${input.text}"
```

### Web Automation & Scraping
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

### API Orchestration
Chain API calls with built-in retry and error handling.

```yaml
steps:
  - id: fetch
    module: http.request
    params:
      url: "https://api.example.com/data"
    retry:
      max_attempts: 3
      delay_ms: 1000
```

### Internal Tooling
Companies can build custom `crm.*`, `billing.*`, `internal.*` modules versioned in Git.

## Module Categories

| Category | Modules | Examples |
|----------|---------|----------|
| `string.*` | 11 | reverse, uppercase, split, replace, trim |
| `array.*` | 15 | filter, sort, map, reduce, unique, chunk |
| `object.*` | 10 | keys, values, merge, pick, omit |
| `file.*` | 8 | read, write, copy, move, delete, diff |
| `browser.*` | 39 | launch, goto, click, extract, scroll, screenshot |
| `flow.*` | 21 | switch, loop, foreach, branch, parallel |
| `http.*` | 3 | request, response_assert |
| `ai.*` | 5 | model, memory, memory_vector |
| `document.*` | 8 | pdf_parse, excel_read, word_parse |
| `data.*` | 7 | json_parse, csv_read, text_template |

**Total: 300+ atomic modules** across 50 categories, plus 28 third-party integrations.

## Connect Any AI via MCP

Every module is automatically available as an [MCP](https://modelcontextprotocol.io/) tool. Any MCP-compatible AI can discover, inspect, and execute all 300+ modules — zero glue code.

```
Claude ──┐
GPT    ──┤                    ┌─ browser.launch
Cursor ──┼── MCP Protocol ──→ ├─ string.reverse
Any AI ──┘                    ├─ file.read
                              └─ ... 300+ modules
```

**Setup (30 seconds):**

Add to your MCP client config (e.g. `~/.claude/mcp_servers.json`):
```json
{
  "flyto-core": {
    "command": "python",
    "args": ["-m", "core.mcp_server"],
    "cwd": "/path/to/flyto-core/src"
  }
}
```

Then your AI can:
1. `list_modules` — discover all available capabilities
2. `get_module_info("browser.extract")` — see params schema and examples
3. `execute_module("browser.extract", {"selector": "h1"})` — run it

**Why this matters:** n8n, Airflow, and Zapier can't be called by AI agents directly. Flyto Core can. Every `@register_module` is instantly an MCP tool — add a module, and every connected AI sees it immediately.

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
from core.modules.registry import register_module
from core.modules.schema import compose, presets

@register_module(
    module_id='string.reverse',
    version='1.0.0',
    category='string',
    label='Reverse String',
    description='Reverse the characters in a string',
    params_schema=compose(
        presets.INPUT_TEXT(required=True),
    ),
    output_schema={
        'result': {'type': 'string', 'description': 'Reversed string'}
    },
)
async def string_reverse(context):
    params = context['params']
    text = str(params['text'])
    return {
        'ok': True,
        'data': {'result': text[::-1], 'original': params['text']}
    }
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
│   │   ├── atomic/        # 300+ atomic modules
│   │   ├── composite/     # High-level composite modules
│   │   ├── patterns/      # Advanced resilience patterns
│   │   └── third_party/   # External integrations
│   └── engine/            # Workflow execution engine
├── workflows/             # Example workflows
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
