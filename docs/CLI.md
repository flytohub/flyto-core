# Flyto2 Core CLI

The installed `flyto` command is the supported terminal surface for recipes,
YAML workflows, replay, module discovery, plugins, templates, the local HTTP
server, and AI-assisted recipe learning.

The generated [CLI parser reference](reference/cli.md) lists every static
command, argument, default, choice, and implementation line. Recipe arguments
are dynamic because they come from each recipe's parameter schema; use
`flyto recipe <name> --help` for that final layer.

## Installation

```bash
pip install flyto-core
flyto --help
```

Browser recipes also need:

```bash
pip install 'flyto-core[browser]'
playwright install chromium
```

## Command Map

| Command | Purpose | Runtime boundary |
|---|---|---|
| `flyto run WORKFLOW` | Execute a YAML workflow | Local workflow engine |
| `flyto recipes` | List packaged recipes | Packaged recipe assets |
| `flyto recipe NAME` | Execute a packaged recipe | Dynamic recipe schema |
| `flyto replay --from-step STEP` | Resume a recorded run | `.flyto-runs` state |
| `flyto modules` | List registry modules | Environment-filtered registry |
| `flyto plugin ...` | Search, install, inspect, or remove plugins | Local plugin loader and registry |
| `flyto template ...` | Exchange templates with the configured API | Remote template API |
| `flyto serve` | Start the local Execution API | FastAPI, optional `api` extra |
| `flyto learn TASK --save NAME` | Explore with an LLM and save a recipe | Optional provider credentials |

## Run Workflows

```bash
flyto run workflow.yaml
flyto run workflow.yaml --params '{"url":"https://example.com"}'
flyto run workflow.yaml --params-file params.yaml
flyto run workflow.yaml --env-file .env --param region=us --param retries=2
flyto run workflow.yaml --lang en
```

For backward compatibility, `flyto workflow.yaml` is rewritten internally to
`flyto run workflow.yaml`. Current automation should use the explicit form.

Supported static run flags are `--lang`, `--params`, `--params-file`,
`--env-file`, and repeatable `--param key=value`. There is no global
`--dry-run`, `--verbose`, `--quiet`, or `--pretty` parser option in the current
implementation.

## Recipes

```bash
flyto recipes
flyto recipe full-audit --url https://example.com
flyto recipe screenshot --url https://example.com --output page.png
flyto recipe full-audit --help
```

Recipe values are parsed from each YAML parameter contract. See
[Recipes](RECIPES.md) and the generated [packaged asset inventory](reference/configuration.md).

## Replay

```bash
flyto replay --from-step fetch
flyto replay --from-step 3 --run-dir .flyto-runs/run-123
```

`--from-step` is required. If `--run-dir` is omitted, the CLI uses
`.flyto-runs/latest`.

## Modules

```bash
flyto modules
flyto modules --env production
flyto modules --format json --output modules.json
```

The runtime catalog can differ by environment, installed optional dependencies,
plugins, and policy. The checked-in [Tool Catalog](TOOL_CATALOG.md) records the
repository's active generation environment.

## Plugins

```bash
flyto plugin list
flyto plugin available
flyto plugin search browser
flyto plugin info example
flyto plugin install example --version 1.2.3
flyto plugin install example --upgrade
flyto plugin uninstall example
```

Plugin installation executes package-manager operations. Review package source,
permissions, manifest, and trust before installation. See [Plugin SDK](PLUGIN_SDK.md).

## Templates

```bash
export FLYTO_TOKEN='...'
export FLYTO_API_URL='https://api.example.com/api'

flyto template list
flyto template search 'browser extract'
flyto template info TEMPLATE_ID
flyto template export TEMPLATE_ID -o template.yaml
flyto template import template.yaml
flyto template push TEMPLATE_ID template.yaml -m 'Update steps'
flyto template pull TEMPLATE_ID -o template.yaml
flyto template diff TEMPLATE_ID template.yaml
flyto template history TEMPLATE_ID
```

The default API URL is defined in `src/cli/template.py`; deployments should set
`FLYTO_API_URL` explicitly. Authentication comes from `FLYTO_TOKEN` or
`~/.flyto/token`.

## Serve

```bash
pip install 'flyto-core[api]'
flyto serve --host 127.0.0.1 --port 8333
```

The server always initializes a bearer token. Use `FLYTO_API_TOKEN` to supply
one, otherwise Core writes a generated token to `~/.flyto/.api-token-<port>`.
See [HTTP API](API.md) before binding beyond loopback.

## Learn

```bash
flyto learn 'capture the pricing table' --save pricing-watch \
  --provider openai --model gpt-4o --max-iterations 20 \
  --variables url=https://example.com
```

`--save` is required. `--api-key` can pass a provider key directly, but an
environment variable or secret manager is preferable because shell history may
persist command arguments.

## Exit And Error Behavior

- Command handlers return zero on success and non-zero on validation,
  dependency, network, authentication, or execution failure.
- Missing optional extras produce an installation hint instead of silently
  disabling a requested command.
- Workflow and recipe failures preserve run state when the execution path
  supports replay.

## Source References

- [Every parser command and argument](reference/cli.md)
- [Every Python declaration](reference/python-api.md)
- [Environment readers](reference/configuration.md)
