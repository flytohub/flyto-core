# Flyto2 Core Technical Whitepaper

## Abstract

Flyto2 Core is an open-source execution engine for AI agents and deterministic
workflow automation. It turns reviewed module schemas and replayable YAML into
bounded operations instead of allowing an agent to invent arbitrary production
code for every task. The same runtime supports a terminal CLI, MCP tools, a
local HTTP Execution API, packaged recipes, evidence capture, and replay.

The current generated runtime catalog contains 451 modules across 84 categories
and 41 packaged recipes. Source traceability covers 932 maintained Python files,
190,753 lines, and 5,351 class/function/method declarations. These measurements
come from checked generators and are not hand-maintained marketing totals.

## Problem

Agent-generated scripts are flexible but difficult to review, meter, replay,
secure, and explain after failure. Production operators need a smaller contract:

1. The agent chooses a named capability with a schema.
2. The runtime validates parameters and policy before execution.
3. Every step records status, timing, result, and optional evidence.
4. A failed run can resume from a known boundary.
5. Security controls remain in the execution path regardless of transport.

## Architecture

```text
CLI / MCP stdio / MCP HTTP / Execution API / packaged recipe
                         |
                   input validation
                         |
            workflow engine and module policy
                         |
         ModuleRegistry -> reviewed module callable
                         |
        trace / evidence / state / replay / metering
```

The transport layer parses and authenticates requests. The engine owns workflow
state and step orchestration. `ModuleRegistry` owns capability lookup and
metadata. Modules own one bounded action. Hooks record trace, evidence,
breakpoints, lineage, and metering without duplicating execution logic.

## Module Contract

An explicit `@register_module` declaration associates a module ID with version,
category, connection types, parameter/output schemas, permissions, retry and
timeout behavior, credentials, examples, and a callable. Static source contains
466 literal registrations; runtime discovery currently publishes 451 because
availability, aliases, dependency gates, plugins, and policy determine the
active set.

The [Tool Catalog](TOOL_CATALOG.md) documents every runtime-discovered module,
parameter, and output. The [registered module source map](reference/registered-modules.md)
connects static module IDs to implementation lines.

## Workflow Contract

A workflow is a graph of named steps. Each step selects a module, supplies
parameters, and can consume prior outputs or external parameters. Validation
checks syntax, module availability, connection rules, input shape, and reserved
fields before or during execution. The engine can run sequential, branch,
parallel, retry, breakpoint, and replay paths according to the selected module
and workflow contract.

The authoritative schemas and examples are in [YAML Workflow Specification](YAML_WORKFLOW_SPEC.md),
[DSL](DSL.md), and [Item Pipeline Specification](specs/ITEM_PIPELINE_SPEC.md).

## Runtime Surfaces

- **CLI:** nine top-level commands and nested plugin/template operations.
- **MCP stdio:** agent-facing module discovery and execution without an HTTP bind.
- **Execution API:** module discovery plus authenticated execution, workflow,
  evidence, replay, and MCP HTTP operations.
- **Verification service:** a separate deterministic runner with internal-key
  authentication for `/run` and an unauthenticated health probe.
- **Python:** direct engine and registry composition for applications embedding
  Core.

Static analysis finds 22 FastAPI operations. Eight plugin-management operations
belong to a router factory that `create_app` does not mount; they are source
capability, not an active Execution API claim.

## Security Model

Untrusted inputs include YAML, module parameters, URLs, page content, plugin
packages, filesystem paths, environment values, callbacks, and prior evidence.
The security model uses:

- bearer authentication for mutating and evidence-bearing Execution API paths;
- an internal key for verification `/run`;
- loopback binding by default and fail-closed non-loopback policy;
- module allow/deny policy at transport and execution boundaries;
- SSRF checks, explicit private-network opt-ins, and trusted-host controls;
- sandboxed path resolution and owner-only files for tokens and workflow state;
- persistence redaction for credential-like values;
- package and plugin review as a separate trust decision.

Security boundaries and environment switches are detailed in
[Security Model](SECURITY_MODEL.md).

## Determinism And Evidence

Core does not claim that every external system is deterministic. It makes the
execution boundary inspectable: selected module, normalized inputs, timing,
status, output, state changes, screenshots, and errors can be recorded. Replay
reuses known context and starts at a selected step instead of silently running
the entire workflow again.

LLM review may interpret evidence, but deterministic checks remain the release
authority for Warroom workflows. Generated text is not a pass/fail oracle.

## Extensibility

Python entry points and external plugin processes can contribute modules.
Plugins must declare manifests, permissions, runtime protocol, and module
schemas. Optional integrations remain optional dependencies; importing the core
package must not require every provider SDK.

## Traceability And Change Control

Generated references cover every maintained source module and declaration,
registered module, CLI parser, HTTP decorator, environment reader, recipe,
bundle, and workflow asset. A documentation ownership manifest maps every
source/configuration area to narrative and generated docs. CI rejects stale
references, broken local links, unowned files, incorrect Flyto2 branding,
unapproved public mailboxes, test failures, package build failures, and Indexer
policy failures.

## Current Limitations

- The checked-in runtime catalog reflects one discovery environment; optional
  dependencies and plugins can change the active set.
- Several integrations need real external credentials and cannot be proven by
  offline unit tests alone.
- Plugin HTTP routes are defined but not mounted by the current Execution API.
- Three historical AI browser demos are executable credential-backed scripts,
  not pytest cases; normal test collection excludes them explicitly.
- Enterprise overlays and hosted orchestration remain separate products and
  must not be inferred from open-source Core source alone.

## Licensing

Flyto2 Core is distributed under Apache License 2.0. Third-party services,
models, websites, packages, and data retain their own terms and licenses.
