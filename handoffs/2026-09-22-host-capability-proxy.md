# Host capability proxy closure — 2026-09-22

Owner: ChatGPT  
Branch: `feat/host-capability-proxy`

## Result

Flyto2 Core remains the sole deterministic workflow engine for external
equipment. `capability.invoke` still consumes only an opaque, execution-scoped
dispatcher. The HTTP workflow boundary can now receive that dispatcher from a
trusted local execution host without serializing authority into workflow data.

Runtime supplies three host-only headers to local Core:

- `X-Flyto-Host-Capability-Endpoint`
- `X-Flyto-Host-Capability-Token`
- `X-Flyto-Host-Capability-Timeout`

Core accepts only a literal `127.0.0.1` HTTP endpoint with an explicit port.
The proxy never follows redirects, uses the random bearer supplied by the local
host, caps responses, and exposes itself to workflow execution only through
`_flyto_runtime_external_capability_dispatcher`.

Opaque runtime authority is recursively stripped from hook variables,
checkpoints, workflow output and runtime state projections so it cannot leak
into traces, evidence or API responses.

## Verification

- generated documentation: 980 maintained Python files / 6,091 declarations
- documentation contract: pass
- brand identity: pass
- changed-surface Ruff: pass
- host proxy + capability invocation focused tests: 6 passed
- strict Flyto2 Indexer: 18 passed, 0 warnings, 0 failures

## Boundary

Core still does not discover equipment, choose resources, approve capabilities,
speak ROS/vendor protocols, or own Cloud scheduling. The execution host owns
the adapter process and assignment-scoped authority; Core owns deterministic
workflow semantics only.
