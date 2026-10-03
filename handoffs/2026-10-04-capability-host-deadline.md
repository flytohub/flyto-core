# Capability host deadline watchdog

Owner: claude
Branch: claude/capability-host-deadline (PR #125)
Date: 2026-10-04

## What changed

Follow-up to `2026-10-04-capability-host.md` (PR #124), from an adversarial
review. `src/core/capability_host/host.py`:

- `adapter.invoke` runs in a daemon thread joined for `deadline + grace`
  (`deadline_grace_seconds`, default 5 s). Past that the call is recorded as
  `timeout` with `"host_watchdog": true`, then `cancel` and `safe_stop` run.
  The abandoned adapter thread is not killed.
- Calls on one host are serialized with a call lock. `stop_now()` and
  `emergency_stop()` do not take it.
- An actuating call reclassified `failed` for returning no declared artifact
  is now followed by `cancel` and `safe_stop`.

Docs: `docs/CAPABILITY_HOST.md`, CHANGELOG `[Unreleased]`, regenerated
`docs/reference/`, inventory counts.

## Why

On #124 a hung adapter blocked the host indefinitely: the "safe stop on
timeout" invariant depended entirely on the adapter honouring
`deadline_seconds`. Parallel workflow branches could also drive one resource
with two actuating calls at once.

## Verified

- Three new tests in `tests/core/test_capability_host.py` fail on 2b2ba4b and
  pass here; host + optional-field tests 77 passed.
- Full `pytest -m 'not browser'`: 5039 passed; 2 local-only failures
  (`tests/test_hints.py` needs `jsdom`; `test_version_identity` compares
  against the venv's installed package), unrelated to this change.
- ruff, `check_documentation`, `check_brand_identity`, `check_release_drift`,
  `lint-project-memory`: pass. CI result is on PR #125.

## Not verified

- No run against the real `ros2.generic` adapter, Gazebo or hardware.
- `task(action='validate')` not run (MCP pinned to another repo).

## Follow-ups

- A pack can mark any capability `role: safe_stop` and so bypass `--allow`
  and the physical confirmation. Pack installation is the trust boundary
  today; a stricter rule (for example, safe_stop takes no arguments) is open.
- `adapter_evidence` keeps `data_base64` verbatim, so the evidence JSON can
  carry up to 8 x 20 MiB of base64 per call.
