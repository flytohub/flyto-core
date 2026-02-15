# Flyto Core

[![PyPI version](https://img.shields.io/pypi/v/flyto-core.svg)](https://pypi.org/project/flyto-core/)
[![License: Source Available](https://img.shields.io/badge/License-Source%20Available-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

<!-- mcp-name: io.github.flytohub/flyto-core -->

> Deterministic execution engine for AI agents. 329 modules across 63 categories, MCP-native, evidence snapshots, execution trace, replay from any step.

## Quick Start — Use with Your AI (MCP)

```bash
pip install flyto-core
```

Add to your MCP client config:

<details open>
<summary><b>Claude Code</b></summary>

Run:
```bash
claude mcp add flyto-core -- python -m core.mcp_server
```

Or add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "flyto-core": {
      "command": "python",
      "args": ["-m", "core.mcp_server"]
    }
  }
}
```

</details>

<details>
<summary><b>Cursor</b></summary>

Add to `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "flyto-core": {
      "command": "python",
      "args": ["-m", "core.mcp_server"]
    }
  }
}
```

</details>

<details>
<summary><b>Windsurf</b></summary>

Add to `~/.codeium/windsurf/mcp_config.json`:
```json
{
  "mcpServers": {
    "flyto-core": {
      "command": "python",
      "args": ["-m", "core.mcp_server"]
    }
  }
}
```

</details>

<details>
<summary><b>Remote MCP Server (HTTP)</b></summary>

Run the server:
```bash
pip install flyto-core[api]
flyto serve
# ✓ flyto-core running on 127.0.0.1:8333
```

Then point any MCP client to the HTTP endpoint:
```json
{
  "mcpServers": {
    "flyto-core": {
      "url": "http://localhost:8333/mcp"
    }
  }
}
```

Supports [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http) — works with Cursor, Windsurf, and any standard MCP client that connects over HTTP.

</details>

**Done.** Your AI now has 329 tools — browser automation, file I/O, data parsing, APIs, notifications, and more.

```
Claude ──┐
Cursor ──┤                    ┌─ browser.launch, .click, .extract (38 tools)
Windsurf ┼── MCP Protocol ──→ ├─ file.read, .write, .copy (8 tools)
Any AI ──┘                    ├─ data.csv.read, .json.parse, .text.template
                              └─ ... 329 modules across 63 categories
```

See the **[Full Tool Catalog](docs/TOOL_CATALOG.md)** for every module, parameter, and description.

## Quick Start — HTTP API

```bash
pip install flyto-core[api]
flyto serve
# ✓ flyto-core running on 127.0.0.1:8333
```

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

| Endpoint | Purpose |
|----------|---------|
| `POST /mcp` | MCP Streamable HTTP transport (remote MCP server) |
| `POST /v1/workflow/run` | Execute workflow with evidence + trace |
| `GET /v1/workflow/{id}/evidence` | Get step-by-step state snapshots |
| `POST /v1/workflow/{id}/replay/{step}` | Replay from any step |
| `POST /v1/execute` | Execute a single module |
| `GET /v1/modules` | Discover all modules |

## Quick Start — Interactive Demo

```bash
pip install flyto-core[api]
python -m core.quickstart
```

Runs a 5-step data pipeline (file → JSON parse → template → format → export), shows the execution trace, evidence snapshots, and replays from step 3 — all in 30 seconds.

## Why Flyto Core?

AI agents are running multi-step tasks — browsing, calling APIs, moving data. But after they finish, all you have is a chat log.

Flyto Core gives you:

- **329 Modules** — composable building blocks across 63 categories ([full catalog](docs/TOOL_CATALOG.md))
- **Execution Trace** — structured record of every step: input, output, timing, status
- **Evidence Snapshots** — full context_before and context_after at every step boundary
- **Replay** — re-execute from any step with the original (or modified) context

## Module Categories

| Category | Count | Examples |
|----------|-------|----------|
| `browser.*` | 38 | launch, goto, click, extract, screenshot, fill forms, wait |
| `flow.*` | 19 | switch, loop, foreach, branch, parallel, retry |
| `array.*` | 15 | filter, sort, map, reduce, unique, chunk, flatten |
| `string.*` | 11 | reverse, uppercase, split, replace, trim, slugify, template |
| `api.*` | 11 | OpenAI, Anthropic, Gemini, Notion, Slack, Telegram |
| `object.*` | 10 | keys, values, merge, pick, omit, get, set, flatten |
| `file.*` | 8 | read, write, copy, move, delete, exists, edit, diff |
| `stats.*` | 8 | mean, median, percentile, correlation, standard deviation |
| `validate.*` | 7 | email, url, json, phone, credit card |
| `math.*` | 6 | calculate, round, ceil, floor, power, abs |
| `image.*` | 5 | resize, convert, crop, watermark, compress |
| `data.*` | 4 | json.parse, json.stringify, text.template, pipeline |
| `pdf.*` | 4 | parse, extract text, merge, compress |

**329 modules** across 63 categories. See **[Full Tool Catalog](docs/TOOL_CATALOG.md)** for every module with parameters and descriptions.

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

## Replay from a Failed Step

```bash
# Step 3 failed? Replay from there.
curl -X POST localhost:8333/v1/workflow/{execution_id}/replay/step3 \
  -H 'Content-Type: application/json' \
  -d '{}'
```

The engine loads the context snapshot at step 3 and re-executes from that point. No wasted computation.

## Installation

```bash
# Core engine (includes MCP server)
pip install flyto-core

# With HTTP API server
pip install flyto-core[api]

# With browser automation
pip install flyto-core[browser]
playwright install chromium

# Everything
pip install flyto-core[all]
```

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
│   ├── api/              # HTTP Execution API + MCP HTTP transport (FastAPI)
│   ├── mcp_handler.py    # Shared MCP logic (tools, dispatch)
│   ├── mcp_server.py     # MCP STDIO transport (Claude Code, local)
│   ├── modules/
│   │   ├── atomic/       # 329 atomic modules
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
