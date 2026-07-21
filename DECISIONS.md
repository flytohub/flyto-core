# Decisions

## 2026-07-21 - Runtime identity and test security state are process-safe

Decision: import the installed Python package only as `core`, reject legacy
`src.core` imports, and permit private-network or auth exceptions only through
fixtures that restore process state. Test helpers that load external modules
must sandbox `sys.modules` instead of modifying imported frameworks.

Reason: duplicate package identities and collection-time environment changes
made auth and SSRF controls depend on test order. A security gate must fail
closed under the complete suite, not only when a test runs alone.

## 2026-07-21 - Coverage measures the control kernel

Decision: retain the 60% line gate for the orchestration and security-control
kernel. Atomic modules, third-party adapters, enterprise overlays, test-runtime
packages, and optional plugin implementations use catalog, schema, contract,
and real integration gates and do not dilute the kernel percentage.

Reason: one aggregate percentage across the control plane and hundreds of
independently deployable adapters was permanently red while hiding which
boundary lacked evidence. The split keeps the kernel threshold enforceable
without skipping adapter tests or lowering the threshold.

## 2026-06-23 - Warroom verification is deterministic first

Decision: Warroom pass/fail decisions come from replayable program evidence:
site/action/API/state graphs, module assertions, screenshots, DOM evidence, and
redacted reports. LLM review is opt-in and advisory only.

Reason: Flyto2 Warroom must work as a verification instrument, not a prompt
wrapper. LLM output cannot make a failing deterministic gate pass by itself.

## 2026-06-21 - Project memory is release-controlled

Decision: keep root project memory files, workflow docs, and handoff registry in
the repository and validate them in CI.

Reason: flyto-core is used to prove product loops. Its own workflow expectations
must be durable, visible, and checked.

## 2026-06-21 - Recipes are product contracts

Decision: maintained recipes should represent executable contracts for product
flows and release smoke, not only demos.

Reason: Flyto2 needs closed-loop verification from UI and API behavior back to
backend state, evidence, and release readiness.
