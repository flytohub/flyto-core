# Flyto2 Runtime capability bridge client

Owner: ChatGPT

## Goal

Keep `flyto-core` and `flyto-runtime` independently installable while allowing
Core-side composition through Runtime's provider-neutral
`flyto2.execution.v1` localhost bridge.

## Boundary

- `core.runtime.capability_bridge.FlytoRuntimeCapabilityClient` is explicit and
  opt-in. Core import/startup does not discover or connect to Runtime.
- The endpoint must be loopback HTTP and the caller must supply the Runtime
  same-user bridge token directly or through an explicitly named token file.
- Manifest discovery and invocation use only JSON wire contracts; Core imports
  no Runtime TypeScript classes, stores, provider SDKs, or credentials.
- Durable side effects retain the original `operation_id`. Accepted results are
  resolved through bounded contract follow-ups; a nested wait may itself remain
  accepted, and terminal reconciliation replays the original operation rather
  than creating a replacement side effect.
- Existing workflow `HostCapabilityProxy` / `capability.invoke` remains a
  separate equipment/resource dispatch boundary and is not rewritten around the
  Runtime machine/coding capability contract.

## Verification

Focused bridge tests cover manifest discovery, nested accepted follow-ups,
operation-id replay, loopback URL rejection, explicit token-file loading, and
secret-safe transport failures. Final documentation, brand, package, test, and
strict Indexer gates are recorded before merge.
