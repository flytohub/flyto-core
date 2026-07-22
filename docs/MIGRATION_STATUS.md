# Migration And Capability Status

## Current Inventory

| Surface | Measured state |
|---|---:|
| Runtime catalog | 452 modules, 84 categories |
| Literal module registrations | 466 |
| Packaged recipes | 41 |
| Maintained Python source | 932 files, 190,753 lines |
| Python declarations | 5,351 across 786 files |
| Static CLI parsers | Generated in `reference/cli.md` |
| Static HTTP operations | 22 |
| Environment-variable names | 93 |

## Active And Defined Surfaces

- CLI, MCP stdio, Execution API, recipes, module registry, workflow engine,
  trace, evidence, and replay are active open-source Core surfaces.
- Verification service endpoints are active when the optional API runtime and
  internal key are configured.
- Eight plugin HTTP handlers are defined by a router factory but not mounted by
  the current Execution API.
- Optional provider modules depend on their SDK, credential, policy, and network
  environment; static registration is not deployment proof.

## Closed In This Audit

- Replaced stale CLI options with a parser-backed guide and generated reference.
- Added bearer protection to workflow status and evidence reads.
- Excluded three non-test credential-backed AI demos from pytest collection.
- Made the runtime Tool Catalog deterministic and checkable.
- Added source-backed references for every maintained Python declaration,
  registered module, CLI parser, HTTP decorator, environment reader, recipe,
  bundle, and workflow asset.
- Added explicit crypto, DNS, and AI extras and verified their implementations
  in the complete offline test suite.
- Replaced the focused-only CI gate with documentation, brand, audited lint,
  offline coverage, npm audit, package/Twine, and strict Indexer closure.

## Remaining Work

- Decide whether plugin HTTP management should be removed or mounted behind an
  explicit authenticated product boundary.
- Continue reducing broad exception handling and optional-integration import
  coupling without changing published module IDs.
- Add production-like browser/E2E evidence for integrations that cannot be
  validated offline.
- Keep runtime catalog and static registration differences explainable as
  optional dependencies, aliases, plugins, or policy, not unexplained drift.
