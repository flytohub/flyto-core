# Standalone Core mobile workflow validation — 2026-10-10

Owner: ChatGPT. Product direction: local-first AI Space, optional hosted
Cloud, no dependency on the separate cybersecurity Engine.

## Implemented

- Read-only provider core.workflow.validate consumes bounded input in the
  flyto2.execution.v1 installed-capability contract.
- Delegates directly to the existing Core workflow validator with parameter
  validation. Returns actual valid/errors/warnings and a content SHA-256
  digest of the reviewed graph, never an executed-workflow receipt.
- Rejects overlong payloads, duplicate/bad IDs, dangling edges and
  unsupported requests before validation.
- Seven focused tests pass including real subprocess invocation and
  unknown-module refusal, without Cloud.
- Generated docs refreshed and 981-file/6095-declaration inventory
  corrected. Documentation, brand identity, project-memory and Ruff checks
  passed locally.

## Known verification limitation

Full strict Flyto2 Indexer remains **not green**: 20 PASS and one baseline
high-risk taint-flow finding through Core's existing MCP run_recipe path
(`src/core/api/routes/mcp.py` → `src/cli/recipe.py`). None of those
files were changed in this branch. The existing load_recipe implementation
resolves the path and explicitly confines it to RECIPES_DIR; the scanner
indicates medium confidence/name-only callee evidence. Do not suppress or
misreport this result; triage independently before claiming a clean security
scan.

This module is NOT an offline AI planner, workflow executor, approval engine,
ROS2 actuation path, complete verified mission, or Android cockpit. Those
remain mandatory features for local parity with Flyto2 Cloud.

## Install as a Runtime capability

See docs/mobile-workflow-validator.md and Runtime's independently installed
adapter manifest. The operator must install Core on the target host,
allowlist core.workflow.validate, and pair the phone to Runtime HTTPS.
