# Feature Guide

## Capability Map

| Capability | What Core provides | Primary implementation/docs |
|---|---|---|
| Module execution | Schema, policy, timeout, retry, result envelope | [Module Specification](MODULE_SPECIFICATION.md), [Tool Catalog](TOOL_CATALOG.md) |
| YAML workflows | Parameters, expressions, step graph, validation | [Workflow Specification](YAML_WORKFLOW_SPEC.md), [DSL](DSL.md) |
| Trace and evidence | Per-step status, timing, context, artifacts | [Architecture](architecture-map.md), [API](API.md) |
| Replay | Resume a saved execution from a selected step | [CLI](CLI.md), [API](API.md) |
| Browser automation | Navigation, interaction, extraction, screenshots, performance | `browser.*` in [Tool Catalog](TOOL_CATALOG.md) |
| Data and files | JSON/YAML/CSV/XML, transforms, archives, images, documents | Category tables in [Tool Catalog](TOOL_CATALOG.md) |
| AI operations | Provider calls, embeddings, vision, tools, agent loops | `ai.*`, `llm.*`, and `api.*` catalog entries |
| Verification | Assertions, visual checks, site graph, evidence packs | [Warroom verification](warroom-deterministic-verification.md) |
| MCP | stdio and authenticated Streamable HTTP module access | [API](API.md), [MCP recipe docs](flyto2-smoke-recipes.md) |
| Plugins | Python entry points and external process protocol | [Plugin SDK](PLUGIN_SDK.md), [Publishing](MODULE_PUBLISHING_GUIDE.md) |
| Recipes | 41 packaged workflows with dynamic CLI parameters | [Recipes](RECIPES.md) |
| Templates | Remote import/export/push/pull/diff/history | [CLI](CLI.md) |

## Execution Lifecycle

1. A caller chooses a recipe, workflow, or module.
2. The relevant transport parses input and applies authentication.
3. Workflow and module validation resolve schemas, connections, and policy.
4. The engine executes the selected callable with bounded context.
5. Hooks record trace, evidence, checkpoints, metering, or lineage.
6. The transport returns a structured success or error result.
7. Persisted runs can be inspected or replayed from a selected step.

## Module Availability

The public catalog is runtime-discovered, so four related counts have different
meanings:

- 452 modules are active in the checked catalog generation environment.
- 84 categories group that active catalog.
- 467 literal decorator registrations exist in maintained source.
- Additional modules can appear from installed plugins or optional dependencies.

Use `flyto modules --format json` to inspect the active runtime where the
workflow will execute.

## Browser Features

Browser modules cover lifecycle, navigation, tabs, frames, dialogs, cookies,
downloads, selectors, role/text interactions, forms, screenshots, PDF,
performance, accessibility-related inspection, visual snapshots, and challenge
detection. Network destinations still pass outbound policy; browser capability
does not bypass SSRF or private-network rules.

## Verification Features

Deterministic verification can discover observable controls and routes, compile
replay scenarios, execute assertions, capture desktop/mobile evidence, and emit
machine-readable plus Markdown reports. Optional LLM review can summarize the
evidence but does not decide the gate.

## Reference Closure

- [All 452 active module schemas](TOOL_CATALOG.md)
- [All 467 literal module implementations](reference/registered-modules.md)
- [All 5,383 maintained Python declarations](reference/python-api.md)
- [All CLI parsers](reference/cli.md)
- [All HTTP decorators](reference/http-api.md)
- [All environment readers and packaged workflow assets](reference/configuration.md)
