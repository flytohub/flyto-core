# verify.spec policy-gate bypass (GHSA-wmwj-g59x-c8px)

Owner: claude
Branch: claude/verify-spec-policy-gate
Date: 2026-08-25

## What changed

- `src/core/modules/atomic/verify/spec_runner.py` — `execute_module_dynamic()`
  now calls the policy-gated `instance.run()` instead of `instance.execute()`.
  A `ModulePolicyError` from a child is re-raised rather than folded into a
  per-rule error, so a denied module fails the whole `verify.spec` call instead
  of reading like an ordinary failed verification.
- `src/core/modules/base.py` — `_execute_with_resilience()` re-raises
  `ModulePolicyError` untouched. It used to be retried like a transient failure
  and then repackaged as a generic `Exception`, which hid from the caller that
  the module was blocked rather than broken.
- `src/core/api/routes/modules.py` — `POST /v1/execute` gained
  `_nested_policy_error()`, the nested-module pre-flight the MCP transport
  already had. It reuses `core.mcp_handler._collect_workflow_module_ids` and
  `_module_missing_permissions` so the two boundaries cannot drift.
- `tests/core/test_reported_security_advisories.py` — the advisory's named
  regression test, `test_verify_spec_ruleset_cannot_run_a_denied_module`.
- `tests/core/test_policy_chokepoint.py` — the dispatch matrix (both rule
  branches, default denylist, strict allowlist, allowed-but-ungranted), the
  MCP and REST boundary checks, and a registry-wide AST test that fails on any
  function that resolves a module by a non-constant id and then awaits
  `<obj>.execute()`.
- `security/advisories.json` + `SECURITY_STATUS.md`, `CHANGELOG.md`,
  `STATE.md`, `ARCHITECTURE.md`, `docs/` inventory tokens and
  `docs/reference/` regenerated.

## Why

`verify.spec` picks its child modules out of the caller's own ruleset —
`rules[].source.module` / `rules[].target.module`, with free-form params — and
dispatched them with `execute()`. Both locks (the module filter and the
dangerous-permission grant) live in `BaseModule.run()`, so a caller restricted
to `verify.spec` could name `shell.exec` in a rule and run host commands as the
service account. This is the same omission that was fixed for nested
Warroom/test steps in `testing/runner.py` (GHSA-675h-j4qg-m52x); `verify.spec`
was the sibling call site that was missed.

Rejected: routing the fixed-class child calls in `verify/runner.py` and
`browser/readability.py` through `run()` in the same change. Those pick a
module the author named, not one the caller chose, so they are not this
advisory, and changing them alters which modules a `verify.run` call requires
an operator to allow. Recorded as a follow-up instead.

## Verified

- Reporter's PoC against the **built artifact**, three configurations:
  `flyto-core[api]==2.31.0` from PyPI reproduces (`exploit_reproduced: true`,
  `marker_outside_sandbox: true`); the `2.31.1` wheel built from this tree
  refuses all three (`bypass_top_level_ok: false`, marker absent, error
  `Module 'verify.spec' declares nested module(s) blocked by security policy:
  shell.exec`). The negative control — a direct `shell.exec` request is denied —
  holds in every run.
- The new tests were run against the unpatched dispatcher first and failed
  there (`DID NOT RAISE ModulePolicyError`; the REST case returned `ok: true`).
- `.venv/bin/python -m pytest -m 'not browser and not e2e'` — **3175 passed, 11
  skipped, 275 deselected**, 63.67% coverage.
- `scripts/check_documentation.py`, `scripts/check_brand_identity.py`,
  `scripts/lint-project-memory.sh`, `scripts/check_release_drift.py` — PASS.
- `python -m build` + `twine check dist/*` — PASS. `npm audit --audit-level=high`
  — 0 vulnerabilities.
- `flyto-index verify . --strict --full-scan` — 20/20 PASS. The first run failed
  `rules_policy` on two `except Exception:` lines the pre-flight introduced into
  `src/core/api/**`; they are now narrowed and the check passes.
- Ruff on every changed file: no new findings. The four that remain
  (`spec_runner.py` I001/F401/SIM108, `test_policy_chokepoint.py` I001) exist on
  `main` and were left alone.

## Not verified

- `flyto-index task validate` did not run against this repo: it drives the
  indexer's own interpreter, which has no `pytest-cov`, and its repo-wide Ruff
  scan covers `examples/`, which CI does not lint. Both failures are
  environmental; the equivalent gates were run directly and are above.
- Browser and e2e markers were not run.
- 2.31.1 is not released. The advisory names `2.31.1` as the patched version, so
  the GHSA must not be published until the tag and the PyPI artifact exist.

## Follow-ups

- Cut `v2.31.1` (tag push runs `publish-pypi.yml`), then PATCH the advisory's
  patched version and publish it — that is what notifies the reporter.
- `verify/runner.py` (six sites) and `browser/readability.py` still call
  `execute()` on fixed child classes, so `verify.run` runs `verify.capture` etc.
  without the policy gate. Not caller-selected, so not this advisory, but it
  means an operator who denied `verify.capture` still gets it through
  `verify.run`. Decide whether those should be gated too.
