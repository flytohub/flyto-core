# Migration And Capability Status

## Current Inventory

| Surface | Measured state |
|---|---:|
| Runtime catalog | 480 modules, 88 categories |
| Literal module registrations | 487 |
| Packaged recipes | 41 |
| Maintained Python source | 970 files, 223,555 lines |
| Python declarations | 5,944 across 821 files |
| Static CLI parsers | Generated in `reference/cli.md` |
| Static HTTP operations | 28 |
| Environment-variable names | 108 |

Catalog search and detail report each module's registry-declared
`provides_capability` and `plugin` as the registry holds them, without deriving
either value from the module ID.

Three built-in modules form an extensible verified deterministic domain-solver
baseline. They cover only a proper 3D point transform, SI constant-acceleration
kinematics, and ideal dilution arithmetic. Each declares the same fresh
six-field `flyto.execution-verification-receipt.v1` output schema. The
`evidence_sha256` value covers canonical nested evidence only; the envelope is
validated separately. It provides tamper evidence, not a signature, sensor
attestation, or physical-world proof. These modules infer no semantics from
labels or IDs and claim neither complete mathematics, physics, or chemistry nor
sensor, hardware, substance identity, reaction, laboratory, medical,
compatibility, handling, or safety authority.

## Active And Defined Surfaces

- CLI, MCP stdio, Execution API, recipes, module registry, workflow engine,
  trace, evidence, and replay are active open-source Core surfaces.
- Verification service endpoints are active when the optional API runtime and
  internal key are configured.
- Eight plugin HTTP handlers are defined by a router factory but not mounted by
  the current Execution API.
- `flyto.plugin.v1` validation and inert adoption are implemented, including a
  prevalidated bounded built-in collection for existing-ID collision checks;
  its shared value/key/endpoint/allowlist gate rejects unsafe Unicode before
  canonicalization and error projection. Registry lifecycle adoption and
  runtime execution are not implemented by it.
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
