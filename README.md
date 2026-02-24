# flyto-core

[![PyPI version](https://img.shields.io/pypi/v/flyto-core.svg)](https://pypi.org/project/flyto-core/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

<!-- mcp-name: io.github.flytohub/flyto-core -->

> A workflow engine with 412 built-in modules. Trace every step. Replay from any point.

## Quick Start — 30 Seconds

```bash
pip install flyto-core[browser]
playwright install chromium

flyto recipe site-audit --url https://example.com
# ✓ audit.json — SEO meta, headings, missing alt tags, Web Vitals, screenshot
```

No config. No API key. Just pick a recipe and run.

### 25 Built-in Recipes

```bash
flyto recipes                  # List all recipes

# Audit & Performance
flyto recipe site-audit    --url https://example.com         # SEO + Web Vitals + screenshot report
flyto recipe web-perf      --url https://example.com         # Core Web Vitals (LCP, FCP, CLS, TTFB)

# Browser Automation
flyto recipe screenshot    --url https://example.com
flyto recipe page-to-pdf   --url https://example.com         # Render webpage as PDF
flyto recipe visual-snapshot --url https://example.com       # Mobile + desktop screenshots
flyto recipe webpage-archive --url https://example.com       # Save as PNG + PDF + HTML
flyto recipe scrape-page   --url https://example.com --selector h1
flyto recipe scrape-links  --url https://example.com
flyto recipe scrape-table  --url https://en.wikipedia.org/wiki/Python_(programming_language) --selector .wikitable
flyto recipe stock-price   --symbol AAPL

# Data & OCR
flyto recipe ocr           --input scan.png                  # Extract text from image
flyto recipe csv-to-json   --input data.csv
flyto recipe json-to-csv   --input data.json
flyto recipe pdf-extract   --input report.pdf

# Image
flyto recipe image-resize   --input photo.jpg --width 800
flyto recipe image-compress --input photo.jpg --quality 80
flyto recipe image-convert  --input photo.png --format webp

# Network & Security
flyto recipe port-scan     --host example.com                # Scan open ports
flyto recipe whois         --domain example.com              # Domain registration lookup

# DevOps
flyto recipe monitor-site  --url https://myapp.com
flyto recipe http-get      --url https://api.github.com/users/octocat
flyto recipe docker-ps
flyto recipe git-changelog

# Integrations
flyto recipe scrape-to-slack --url https://example.com --selector h1 --webhook $SLACK_URL
flyto recipe github-issue    --url https://example.com --owner me --repo my-app --title "Bug" --token $GITHUB_TOKEN
```

Each recipe is a YAML workflow template. Run `flyto recipe <name> --help` for full options.

### Recipe Reference

| Recipe | Description | Key args |
|--------|-------------|----------|
| **Audit & Performance** | | |
| `site-audit` | SEO + performance audit with report | `--url` `--output` |
| `web-perf` | Core Web Vitals (LCP, FCP, CLS, TTFB) | `--url` |
| **Browser** | | |
| `screenshot` | Screenshot any webpage | `--url` `--output` `--width` |
| `page-to-pdf` | Render webpage as PDF | `--url` `--output` `--size` |
| `visual-snapshot` | Mobile + desktop screenshots | `--url` |
| `webpage-archive` | Save as PNG + PDF + HTML | `--url` `--prefix` |
| `scrape-page` | Extract text via CSS selector | `--url` `--selector` |
| `scrape-links` | Extract all links from a page | `--url` |
| `scrape-table` | Extract HTML table data | `--url` `--selector` |
| `stock-price` | Fetch stock price from Yahoo Finance | `--symbol` |
| **Data & OCR** | | |
| `ocr` | Extract text from image (Tesseract) | `--input` `--lang` |
| `csv-to-json` | Convert CSV to JSON | `--input` |
| `json-to-csv` | Convert JSON array to CSV | `--input` |
| `pdf-extract` | Extract text from PDF | `--input` |
| **Image** | | |
| `image-resize` | Resize an image | `--input` `--width` |
| `image-compress` | Compress an image | `--input` `--quality` |
| `image-convert` | Convert image format | `--input` `--format` |
| **Network & Security** | | |
| `port-scan` | Scan open ports on a host | `--host` `--ports` |
| `whois` | Domain registration lookup | `--domain` |
| **DevOps** | | |
| `monitor-site` | HTTP health check | `--url` |
| `http-get` | Fetch URL and save response | `--url` |
| `docker-ps` | List Docker containers | `--all` |
| `git-changelog` | Git diff with file statistics | `--repo` `--ref` |
| **Integrations** | | |
| `scrape-to-slack` | Scrape a page → send to Slack | `--url` `--selector` `--webhook` |
| `github-issue` | Screenshot a bug → create GitHub issue | `--url` `--owner` `--repo` `--title` |

See **[docs/RECIPES.md](docs/RECIPES.md)** for full documentation with all arguments and examples.

## Write Your Own Workflows

Recipes are just YAML files. Write your own:

```yaml
name: price-monitor
steps:
  - id: open
    module: browser.launch
    params: { headless: true }

  - id: page
    module: browser.goto
    params: { url: "https://competitor.com/pricing" }

  - id: prices
    module: browser.evaluate
    params:
      script: |
        JSON.stringify([...document.querySelectorAll('.price')].map(e => e.textContent))

  - id: save
    module: file.write
    params: { path: "prices.json", content: "${prices.result}" }

  - id: close
    module: browser.close
```

```bash
flyto run price-monitor.yaml
```

Every run produces an execution trace (input/output/timing per step) and state snapshots. If step 3 fails, replay from step 3 — no re-running the whole thing.

## 412 Modules, 78 Categories

| Category | Count | Examples |
|----------|-------|----------|
| `browser.*` | 38 | launch, goto, click, extract, screenshot, fill forms, wait |
| `flow.*` | 24 | switch, loop, branch, parallel, retry, circuit breaker, rate limit |
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
| `ssh.*` | 3 | remote exec, SFTP upload, SFTP download |
| `git.*` | 3 | clone, commit, diff |
| `sandbox.*` | 3 | execute Python, Shell, JavaScript |
| `dns.*` | 1 | DNS lookup (A, AAAA, MX, CNAME, TXT, NS) |
| `monitor.*` | 1 | HTTP health check with SSL cert verification |

See the **[Full Tool Catalog](docs/TOOL_CATALOG.md)** for every module, parameter, and description.

## Engine Features

- **Execution Trace** — structured record of every step: input, output, timing, status
- **Evidence Snapshots** — full state before and after each step boundary
- **Replay** — re-execute from any step with the original (or modified) context
- **Breakpoints** — pause execution at any step, inspect state, resume
- **Data Lineage** — track data flow across steps, build dependency graphs
- **Timeout Guard** — configurable workflow and step-level timeout protection

## How is this different?

| | flyto-core | Shell scripts | n8n / Zapier | Individual MCP servers |
|---|---|---|---|---|
| Setup | `pip install flyto-core` | Manual | SaaS account | 15+ packages |
| Modules | 412 built-in | Write yourself | 500+ (GUI only) | 1-5 each |
| Interface | CLI + YAML + Python + HTTP + MCP | CLI | GUI | MCP only |
| Trace / Replay | Built-in | No | Partial | No |
| License | Apache-2.0 | N/A | Proprietary / AGPL | Varies |

## Also Works As

<details>
<summary><b>MCP Server</b> — for Claude Code, Cursor, Windsurf</summary>

```bash
pip install flyto-core
claude mcp add flyto-core -- python -m core.mcp_server
```

Or add to your MCP config:
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

Your AI gets all 412 modules as tools.

</details>

<details>
<summary><b>HTTP API</b> — for integrations and remote execution</summary>

```bash
pip install flyto-core[api]
flyto serve
# ✓ flyto-core running on 127.0.0.1:8333
```

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/workflow/run` | Execute workflow with evidence + trace |
| `POST /v1/workflow/{id}/replay/{step}` | Replay from any step |
| `POST /v1/execute` | Execute a single module |
| `GET /v1/modules` | Discover all modules |
| `POST /mcp` | MCP Streamable HTTP transport |

</details>

<details>
<summary><b>Python API</b> — for programmatic use</summary>

```python
import asyncio
from core.modules.registry import ModuleRegistry

async def main():
    result = await ModuleRegistry.execute(
        "string.reverse",
        params={"text": "Hello"},
        context={}
    )
    print(result)  # {"ok": True, "data": {"result": "olleH"}}

asyncio.run(main())
```

</details>

## Installation

```bash
# Core engine + CLI + MCP server
pip install flyto-core

# With browser automation (for screenshot, scrape recipes)
pip install flyto-core[browser]
playwright install chromium

# With HTTP API server
pip install flyto-core[api]

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
    params_schema=compose(presets.INPUT_TEXT(required=True)),
    output_schema={'result': {'type': 'string', 'description': 'Reversed string'}},
)
async def string_reverse(context):
    text = str(context['params']['text'])
    return {'ok': True, 'data': {'result': text[::-1]}}
```

See **[Module Specification](docs/MODULE_SPECIFICATION.md)** for the complete guide.

## Contributing

We welcome contributions! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for guidelines.

## Security

Report security vulnerabilities via **[security@flyto.dev](mailto:security@flyto.dev)**.
See **[SECURITY.md](SECURITY.md)** for our security policy.

## License

[Apache License 2.0](LICENSE) — free for personal and commercial use.

---

<p align="center">
  <b>One package. 412 modules. Trace, replay, done.</b>
</p>
