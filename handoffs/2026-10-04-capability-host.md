# Generic capability host and contract optional keys (2.36.0)

Owner: claude
Branch: claude/capability-host
Date: 2026-10-04

## What changed

- `src/core/capability_host/` (new): `CapabilityHost`, an opaque run-scoped
  dispatcher injected at `_flyto_runtime_external_capability_dispatcher`
  (`host.context()`). Resolves the adapter by exact, unique entry-point name in
  `flyto2.external_adapters`; reads contracts from the registry
  (`registry_contract_lookup`: `declared` / `absent` / `ambiguous`, only
  `declared` is trusted). Policy: resource match; actuating, contract-less or
  ambiguous capabilities need `allow`; `role: safe_stop` always runs with no
  prompt; a non-`simulation` deployment (attribute `deployment_mode`, else
  `observe(phase="preflight")["deployment_mode"]`, unknown = physical) needs
  `yes_physical` or an interactive yes, and is refused with no `confirm`.
  Deadline = `expected_duration_ms` > `timeout_ms` > 60 s, clamped 1 s..1 h.
  Phases from contract evidence; contract `settled` -> adapter `post_stop`.
  `timeout`/`failed` (incl. adapter exception, unknown outcome) -> `cancel` +
  `safe_stop`. Outcome/detail/evidence recorded verbatim; verdicts from
  `judge` recorded beside, never replacing, the outcome. Declared artifacts
  are checked (kind, media type, size) and saved; none passing -> `failed`.
- `src/cli/main.py`, `src/cli/runner.py`, `src/cli/capability_host.py`:
  `flyto run WF --capability-host ADAPTER --resource ID [--allow IDS]
  [--yes-physical] [--capability-evidence PATH]`; Ctrl-C -> `safe_stop`;
  records written as JSON.
- `src/core/capability_contract.py`: optional `role` (`safe_stop`, must be
  cancellable false / requires_safe_stop false / idempotent true),
  `artifacts` (1..8 `{kind, media_types, max_bytes<=20 MiB}`), `recovery`
  (`{capabilities 1..8, observe?, guidance<=500}`), `expected_duration_ms`
  (1..3,600,000). Emitted only when declared, so 2.35 contracts and manifest
  hashes are unchanged. `OPTIONAL_FIELDS` for provider feature detection.
- Docs: `docs/CAPABILITY_HOST.md` (new), `docs/CAPABILITY_CONTRACT.md`
  (optional keys, artifact transport `evidence.artifacts[{kind, media_type,
  data_base64}]`), CHANGELOG, DECISIONS, STATE, docs index, regenerated
  `docs/reference/`, inventory counts. Version 2.36.0.

## Why

Phase B of the module-pack plan: a pack must be provable with flyto-core
alone, and Cloud's dispatcher must be able to drop provider knowledge
(`_PLANNED_MOTIONS`, `_CAPTURES`, hard-coded `motion.halt`) by reading
contracts. Approval invariants the reviewer required for a core-only host
(allow list, physical confirmation failing closed, safe stop) are enforced in
the host; floors stay in the adapter.

Not done (deliberate): no `/v1/workflows/run` wiring — an HTTP request has no
terminal to confirm physical actuation, and the existing host proxy headers
stay the only HTTP path. Desktop does not switch to this host.

## Verified

- `pytest -m "not browser"` (Python 3.11): 5025 passed, 192 skipped, 65 failed on the first run; all 65 were environmental (63 `tests/test_hints.py` needing `jsdom` before `npm ci`, plus `tests/test_version_identity.py` reading stale editable metadata before reinstall) and pass after `npm ci` + reinstall (66/66 in those two files).
- `tests/core/test_capability_host.py` (36) and
  `tests/core/test_capability_contract_optional_fields.py` with the existing
  contract tests (226 together) pass under Python 3.11.
- CLI smoke with a fake adapter installed via a `.dist-info` entry point:
  not allowed -> host refusal, step fails; `--allow` -> completed, record
  written; unknown adapter and `--allow` without `--capability-host` exit with
  an error.
- `check_documentation.py`, `check_brand_identity.py`,
  `lint-project-memory.sh`, `check_release_drift.py` pass; ruff clean on the
  audited list and every changed file.
- `flyto-index verify . --full-scan --strict`: 20/21; the one failure is the
  pre-existing `weak_scan_taint` (`api/routes/mcp.py` -> `cli/recipe.py`)
  recorded in the 2026-10-04 contract handoff, untouched here.

## Not verified

- No real adapter (flyto-robotics `ros2.generic`) or Gazebo twin run through
  the host; fake adapter only.
- No pack declares the new optional keys yet (flyto-modules-robotics must
  feature-detect `OPTIONAL_FIELDS`).
- `task(action='validate')` via MCP not run (MCP pinned to another root).

## Follow-ups

- flyto-modules-robotics: `role: safe_stop` on halt, `artifacts` on
  observe/map, `recovery` on motions, `expected_duration_ms` on navigate,
  gated on `OPTIONAL_FIELDS`.
- flyto-robotics: return `evidence.artifacts` in the transport above.
- flyto-cloud: read `role`/`artifacts`/`expected_duration_ms` instead of its
  provider sets, keeping them as legacy fallback.
