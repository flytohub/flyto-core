# Flyto2 Core

[![PyPI version](https://img.shields.io/pypi/v/flyto-core.svg)](https://pypi.org/project/flyto-core/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

<!-- mcp-name: io.github.flytohub/flyto-core -->

> Deterministic execution engine for AI agents. 412 modules across 78 categories, MCP-native, evidence snapshots, execution trace, replay from any step.

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

**Done.** Your AI now has 412 tools — browser automation, Docker, file I/O, data parsing, crypto, scheduling, APIs, and more.

```
Claude ──┐
Cursor ──┤                    ┌─ browser.launch, .click, .extract (38 tools)
Windsurf ┼── MCP Protocol ──→ ├─ file.read, .write, .copy (8 tools)
Any AI ──┘                    ├─ data.csv.read, .json.parse, .xml.parse, .yaml.parse
                              └─ ... 412 modules across 78 categories
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

## Why Flyto2 Core?

AI agents are running multi-step tasks — browsing, calling APIs, moving data. But after they finish, all you have is a chat log.

Flyto2 Core gives you:

- **412 Modules** — composable building blocks across 78 categories ([full catalog](docs/TOOL_CATALOG.md))
- **Execution Trace** — structured record of every step: input, output, timing, status
- **Evidence Snapshots** — full context_before and context_after at every step boundary
- **Replay** — re-execute from any step with the original (or modified) context
- **Triggers** — webhook (HMAC-verified) and cron scheduling for automated workflows
- **Execution Queue** — priority-based queue with concurrency control
- **Workflow Versioning** — semantic versioning, diff, and rollback
- **Usage Metering** — built-in billing hooks for step/workflow tracking
- **Timeout Guard** — configurable workflow and step-level timeout protection

## Module Categories

| Category | Count | Examples |
|----------|-------|----------|
| `browser.*` | 38 | launch, goto, click, extract, screenshot, fill forms, wait |
| `flow.*` | 24 | switch, loop, branch, parallel, retry, circuit breaker, rate limit, debounce |
| `array.*` | 15 | filter, sort, map, reduce, unique, chunk, flatten |
| `string.*` | 11 | reverse, uppercase, split, replace, trim, slugify, template |
| `api.*` | 11 | OpenAI, Anthropic, Gemini, Notion, Slack, Telegram |
| `object.*` | 10 | keys, values, merge, pick, omit, get, set, flatten |
| `image.*` | 9 | resize, convert, crop, rotate, watermark, OCR, compress |
| `data.*` | 8 | json/xml/yaml/csv parse and generate |
| `file.*` | 8 | read, write, copy, move, delete, exists, edit, diff |
| `stats.*` | 8 | mean, median, percentile, correlation, standard deviation |
| `validate.*` | 7 | email, url, json, phone, credit card |
| `docker.*` | 6 | run, ps, logs, stop, build, inspect |
| `archive.*` | 6 | zip create/extract, tar create/extract, gzip, gunzip |
| `math.*` | 6 | calculate, round, ceil, floor, power, abs |
| `k8s.*` | 5 | get_pods, apply, logs, scale, describe |
| `crypto.*` | 4 | AES encrypt/decrypt, JWT create/verify |
| `network.*` | 4 | ping, traceroute, whois, port scan |
| `pdf.*` | 4 | parse, extract text, merge, compress |
| `aws.s3.*` | 4 | upload, download, list, delete |
| `google.*` | 4 | Gmail send/search, Calendar create/list events |
| `cache.*` | 4 | get, set, delete, clear (memory + Redis) |
| `ai.*` | 3 | vision analyze, structured extraction, text embeddings |
| `env.*` | 3 | get, set, load .env file |
| `git.*` | 3 | clone, commit, diff |
| `markdown.*` | 3 | to HTML, parse frontmatter, table of contents |
| `queue.*` | 3 | enqueue, dequeue, size (memory + Redis) |
| `sandbox.*` | 3 | execute Python, Shell, JavaScript |
| `scheduler.*` | 3 | cron parse, interval, delay |
| `ssh.*` | 3 | remote exec, SFTP upload, SFTP download |
| `graphql.*` | 2 | query, mutation |
| `dns.*` | 1 | DNS lookup (A, AAAA, MX, CNAME, TXT, NS) |
| `monitor.*` | 1 | HTTP health check with SSL cert verification |

**412 modules** across 78 categories. See **[Full Tool Catalog](docs/TOOL_CATALOG.md)** for every module with parameters and descriptions.

## Engine Features

Beyond atomic modules, flyto-core provides production-grade engine infrastructure:

| Feature | Tier | Description |
|---------|------|-------------|
| Execution Trace | Free | Structured record of every step: input, output, timing, status |
| Evidence Snapshots | Free | Full context_before and context_after at every step boundary |
| Replay | Free | Re-execute from any step with original or modified context |
| Breakpoints | Free | Pause execution at any step, inspect state, resume |
| Data Lineage | Free | Track data flow across steps, build dependency graphs |
| Timeout Guard | Free | Configurable workflow/step-level timeout protection |
| Webhook Triggers | Pro | HMAC-SHA256 verified webhooks with payload mapping |
| Cron Triggers | Pro | 5-field cron scheduling with async scheduler loop |
| Execution Queue | Pro | Priority-based queue (LOW→CRITICAL) with concurrency control |
| Workflow Versioning | Pro | Semantic versioning, diff between versions, rollback |
| Usage Metering | Pro | Built-in billing hooks for step/workflow/module tracking |

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
│   │   ├── atomic/       # 412 atomic modules
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

[Apache License 2.0](LICENSE) — free for personal and commercial use.

---

<p align="center">
  <b>Deterministic execution engine for AI agents.</b><br>
  Evidence. Trace. Replay.
</p>
