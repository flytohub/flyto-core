# Flyto Core

[![PyPI version](https://img.shields.io/pypi/v/flyto-core.svg)](https://pypi.org/project/flyto-core/)
[![License: Source Available](https://img.shields.io/badge/License-Source%20Available-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

<!-- mcp-name: io.github.flytohub/flyto-core -->

> Deterministic execution engine for AI agents. 300+ atomic modules, evidence snapshots, execution trace, replay from any step.

## Quick Start

```bash
pip install flyto-core[api]
python -m core.quickstart
```

That's it. In 30 seconds you'll see:

1. A 5-step workflow execute with full trace
2. Evidence snapshots (context_before/after) for every step
3. Replay from step 3 — without re-running steps 1-2

## Why Flyto Core?

AI agents are running multi-step tasks — browsing, calling APIs, moving data. But after they finish, all you have is a chat log.

Flyto Core gives you:

- **Execution Trace** — structured record of every step: input, output, timing, status
- **Evidence Snapshots** — full context_before and context_after at every step boundary
- **Replay** — re-execute from any step with the original (or modified) context
- **300+ Atomic Modules** — composable building blocks for any workflow

## HTTP Execution API

```bash
flyto serve
# ✓ flyto-core running on 127.0.0.1:8333
```

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/workflow/run` | Execute workflow with evidence + trace |
| `GET /v1/workflow/{id}/evidence` | Get step-by-step state snapshots |
| `POST /v1/workflow/{id}/replay/{step}` | Replay from any step |
| `POST /v1/execute` | Execute a single module |
| `GET /v1/modules` | Discover all 300+ modules |

### Run a workflow

```bash
curl -X POST localhost:8333/v1/workflow/run \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": {
      "name": "example",
      "steps": [
        {"id": "step1", "module": "string.uppercase", "params": {"text": "hello"}},
        {"id": "step2", "module": "string.reverse", "params": {"text": "world"}}
      ]
    },
    "enable_evidence": true,
    "enable_trace": true
  }'
```

### Replay from a failed step

```bash
# Step 3 failed? Replay from there.
curl -X POST localhost:8333/v1/workflow/{execution_id}/replay/step3
```

The engine loads the context snapshot at step 3 and re-executes from that point. No wasted computation.

## YAML Workflows

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

```bash
flyto run workflow.yaml
# Output: "OTYLF OLLEH"
```

## Python API

```python
import asyncio
from core.modules.registry import ModuleRegistry

async def main():
    result = await ModuleRegistry.execute(
        "string.reverse",
        params={"text": "Hello"},
        context={}
    )
    print(result)  # {"ok": True, "data": {"result": "olleH", ...}}

asyncio.run(main())
```

## Module Categories

| Category | Modules | Examples |
|----------|---------|----------|
| `string.*` | 11 | reverse, uppercase, split, replace, trim |
| `array.*` | 12 | filter, sort, map, reduce, unique, chunk |
| `object.*` | 5 | keys, values, merge, pick, omit |
| `file.*` | 3 | read, write, copy |
| `browser.*` | 38 | launch, goto, click, extract, scroll, screenshot |
| `flow.*` | 18 | switch, loop, foreach, branch, parallel |
| `http.*` | 1 | request |
| `ai.*` | 7 | model, memory, memory_vector, local_ollama |
| `document.*` | 8 | pdf_parse, excel_read, word_parse |
| `data.*` | 9 | json_parse, csv_read, text_template |

**300+ atomic modules** across 40+ categories, plus 28 third-party integrations.

## MCP Integration

Every module is automatically available as an [MCP](https://modelcontextprotocol.io/) tool. Any MCP-compatible AI can discover, inspect, and execute all 300+ modules.

```
Claude ──┐
GPT    ──┤                    ┌─ browser.launch
Cursor ──┼── MCP Protocol ──→ ├─ string.reverse
Any AI ──┘                    ├─ file.read
                              └─ ... 300+ modules
```

Add to your MCP client config:
```json
{
  "flyto-core": {
    "command": "python",
    "args": ["-m", "core.mcp_server"]
  }
}
```

## Installation

```bash
# Core engine
pip install flyto-core

# With HTTP API server
pip install flyto-core[api]

# With browser automation
pip install flyto-core[browser]
playwright install chromium

# Everything
pip install flyto-core[all]
```

## Use Cases

### Auditable Agent Execution
Run multi-step agent workflows with full evidence trail — every step's state captured, replayable, on disk.

### Web Automation
Automate browsers with the `browser.*` module family (38 modules: launch, goto, click, extract, screenshot, etc.)

### API Orchestration
Chain API calls with built-in retry and error handling.

### Internal Tooling
Build custom `crm.*`, `billing.*`, `internal.*` modules versioned in Git.

## For Module Authors

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

## Project Structure

```
flyto-core/
├── src/core/
│   ├── api/              # HTTP Execution API (FastAPI)
│   ├── modules/
│   │   ├── atomic/       # 300+ atomic modules
│   │   ├── composite/    # High-level composite modules
│   │   ├── patterns/     # Advanced resilience patterns
│   │   └── third_party/  # External integrations
│   └── engine/
│       ├── workflow/     # Workflow execution engine
│       ├── evidence/     # Evidence collection & storage
│       └── replay/       # Replay manager
├── workflows/            # Example workflows
└── docs/                 # Documentation
```

## Contributing

We welcome contributions! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for guidelines.

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

See **[LICENSE](LICENSE)** for complete terms. For commercial licensing: licensing@flyto.dev

---

<p align="center">
  <b>Deterministic execution engine for AI agents.</b><br>
  Evidence. Trace. Replay.
</p>
