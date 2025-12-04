# Flyto Core

**Open-source YAML workflow automation engine.** Run automation workflows with 100+ built-in modules.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/flytohub/flyto-core.git
cd flyto-core

# 2. Install
pip install -r requirements.txt

# 3. Run (all platforms)
python run.py workflow.yaml
```

## Usage

```bash
# Run a workflow
python run.py my_workflow.yaml

# With parameters
python run.py workflow.yaml --params '{"url": "https://example.com"}'

# Interactive mode (select workflow from menu)
python run.py
```

## Example Workflow

Create `hello.yaml`:

```yaml
name: "Hello World"
description: "Simple example"

steps:
  - id: reverse_text
    module: text.reverse
    params:
      text: "Hello World"

  - id: show_result
    module: utility.delay
    params:
      seconds: 0
    description: "Result: ${reverse_text.result}"
```

Run it:

```bash
python run.py hello.yaml
```

## Available Modules

**117 modules** across **23 categories**:

| Category | Examples |
|----------|----------|
| `string.*` | split, replace, trim, reverse |
| `array.*` | filter, sort, map, reduce, unique |
| `file.*` | read, write, copy, move, delete |
| `datetime.*` | parse, format, add, subtract |
| `math.*` | calculate, abs, round, ceil, floor |
| `data.*` | json.parse, json.stringify, csv.read |
| `browser.*` | launch, goto, click, type, extract |
| `api.*` | http_get, http_post, openai.chat |
| `utility.*` | delay, random.number, hash.md5 |

Full list: Run `python run.py` in interactive mode → select "List modules"

## Documentation

- [Module Specification](docs/MODULE_SPECIFICATION.md) - How modules work
- [Writing Modules](docs/WRITING_MODULES.md) - Create your own
- [CLI Reference](docs/CLI.md) - Command line options
- [DSL Reference](docs/DSL.md) - YAML workflow syntax

## Browser Automation

For browser modules (`browser.*`), install Playwright:

```bash
pip install playwright
playwright install chromium
```

## Optional Integrations

For third-party services (OpenAI, Slack, etc.):

```bash
pip install -r requirements-integrations.txt
```

## Project Structure

```
flyto-core/
├── run.py              # Entry point
├── src/
│   ├── cli/            # CLI interface
│   ├── core/
│   │   ├── engine/     # Workflow engine
│   │   ├── modules/    # 100+ atomic modules
│   │   └── browser/    # Playwright driver
│   └── integrations/   # Third-party connectors
├── workflows/          # Example workflows
├── i18n/               # Translations (en, zh, ja)
└── docs/               # Documentation
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE)
