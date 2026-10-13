# Optional external IoT adapters: implementation and acceptance boundary

Branch: feat/iot-ecosystem-adapters-20261013
Repo: flytohub/flyto-core
Date: 2026-10-13

Goal: Reuse the existing Core ModuleRegistry, capability.invoke and
CapabilityHost (no second scheduler or per-vendor Core modules). The external
reference package is self-contained under examples/integrations.

Implemented:
- Passive W3C WoT 1.1 Thing Description parsing, no remote form invocation,
  discovered-not-approved projection, export requiring host-provided auth/forms.
- Home Assistant REST exact entity binding; passive discovery, state observation,
  light/switch on/off, persistent SQLite unique call admission, failure
  and unknown-outcome no-replay, observed logical state before completion.
- MQTT optional paho TLS read-only exact topic telemetry, bounded scalar JSON,
  fresh observations only; retained samples rejected. No publish or actuation.
- flyto.modules pack registers four canonical capability rows with validated
  contracts; flyto2.external_adapters entrypoints reuse CapabilityHost.

Tests: examples/integrations/tests exercises malicious import, unknown outcome,
call ID reuse, independent adapter instance, concurrent SQLite claims,
unobserved effects, MQTT invalid/retained/stale samples, and real Core registry.

Limitations: tests are unit/integration against mocked external clients, not
real Home Assistant, MQTT broker, robots or physical equipment. A persistent
per-resource ledger is essential; a separate ledger on multiple hosts is not
a global exactly-once guarantee. Actual Cloud/AI Space registration and
approval, independent physical evidence, crashes and operator acceptance
remain open.

Not started in this repository: new OPC UA, Viam, native Matter, Isaac Sim or
Tuya adapters. Matter devices can be bridged via an operator-provided HA Matter
integration, but are not directly paired/commissioned by this package.
Open-RMF already has a separate flyto-robotics provider; do not duplicate it.

Local acceptance: 53 adapter/registry/Core-host tests passed on Python 3.11;
280 passed when run alongside existing Core host and contract regressions.
Wheel built successfully; Ruff, documentation inventory, brand, and
project-memory checks passed with optional-package exclusion from Core's
built-in inventory. Local Python 3.12 lacks pytest; the new GitHub workflow
checks both 3.11 and 3.12 on CI.

Indexer strict verification: 20 PASS, 0 WARN, 1 FAIL. The failing
weak_scan_taint/path_traversal flow is the already-existing
src/core/api/routes/mcp.py -> src/core/mcp_handler.py ->
src/cli/recipe.py::load_recipe path, fingerprint 66be6a7449f057065a6429e5.
None of those files changed in this branch. This must not be described as an
all-green strict gate; no suppression or CI bypass was introduced.

Next: push branch and review PR CI; physical and remaining ecosystem
integrations are separately tracked in tasks.md and ROADMAP.md.
The root user request names eight integrations, but this PR must not be sold as
eight independently complete production adapters. External accounts, licensed
tools and physical acceptance were not available.
