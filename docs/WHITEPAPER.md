# Flyto2 Core Technical Whitepaper

## Abstract

Flyto2 Core is an open-source execution engine for AI agents and deterministic
workflow automation. It turns reviewed module schemas and replayable YAML into
bounded operations instead of allowing an agent to invent arbitrary production
code for every task. The same runtime supports a terminal CLI, MCP tools, a
local HTTP Execution API, packaged recipes, evidence capture, and replay.

The current generated runtime catalog contains 480 modules across 88 categories
and 41 packaged recipes. Catalog search and detail carry each module's
registry-declared `provides_capability` and `plugin`, never a value derived from
the module ID. Source traceability covers 967 maintained Python files,
202,022 lines, and 5,694 class/function/method declarations. These measurements
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
487 literal registrations; runtime discovery currently publishes 480 because
availability, aliases, dependency gates, plugins, and policy determine the
active set. That difference is now itself enforced: every literal registration
must be live, gated on a named optional dependency, or recorded as deliberately
not shipped, so a module cannot be documented and unreachable at the same time
(`tests/core/test_module_registration_coverage.py`).

The [Tool Catalog](TOOL_CATALOG.md) documents every runtime-discovered module,
parameter, and output. The [registered module source map](reference/registered-modules.md)
connects static module IDs to implementation lines.

### Bounded Domain Solvers

Three dependency-free offline modules implement source-declared semantics for
a proper 3D rigid point transform, one-dimensional constant-acceleration
kinematics, and ideal dilution arithmetic. Semantics are never inferred from a
label or module ID. Each publishes the exact six-field
`flyto.execution-verification-receipt.v1` output envelope. Its
`evidence_sha256` is SHA-256 over canonical nested `evidence` only; callers
validate the envelope separately. The digest is tamper evidence, not a
signature, sensor attestation, or physical-world proof.

The implementations are intentionally narrower than their subject areas. They
do not claim complete mathematics, physics, or chemistry and have no sensor,
hardware, substance identity, reaction, laboratory, medical, compatibility,
handling, or safety authority. Primary background references are SciPy's
[`Rotation`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Rotation.html)
and [`RigidTransform`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.RigidTransform.html)
documentation and [ROS tf2](https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Tf2.html)
for rigid transforms; [OpenStax University Physics, Motion with Constant
Acceleration](https://openstax.org/books/university-physics-volume-1/pages/3-4-motion-with-constant-acceleration)
for the kinematics equations; and the NIH/NCI protocol's [Dilution of a Stock
Solution](https://bio-protocol.org/exchange/minidetail?id=3654880&type=30)
for ideal dilution arithmetic. These references explain the bounded equations;
they do not extend the modules' authority.

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

The `flyto.plugin.v1` adoption slice validates detached manifests, local
artifacts, endpoint locality, and a bounded built-in collection of existing
reverse-DNS IDs. It is deliberately inert: it does not install, load, start, or
execute a plugin and supplies no operating-system sandbox.
One shared pre-canonicalization text boundary rejects C1 controls, bidi and
zero-width formats, surrogates, private-use, unassigned/noncharacters, and
line/paragraph separators from values, keys, endpoints, and allowlists. Stable
errors never reflect the rejected text.

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
