# browser.type label association and step-record integrity (2.36.1)

Owner: claude
Branch: claude/browser-type-robustness
Date: 2026-10-04

## What changed

- `src/core/modules/atomic/browser/type.py` (module 1.2.0): `type_method: label`
  resolves `<label for=id>` to `[id="..."]` and `aria-labelledby` to
  `[aria-labelledby="..."]` on the page (exact label text ranked before
  substring; targets must be typeable). Order: wrapping label, explicit
  associations, `aria-label`, then the sibling heuristics. `sensitive_params`
  classmethod marks `text` when `input_type` is password or target/selector
  names a credential. At runtime an `<input type=password>` is detected; the
  result masks `text` and reports `_sensitive_params`.
- `src/core/modules/atomic/browser/_hints.py`: password input `value` is
  `[REDACTED]` when filled; a password's value is no longer its name fallback.
  (Found while testing: the hints in a type result quoted the password.)
- `src/core/engine/redaction.py`: `redact_step_params`, `is_sensitive_param_name`,
  `runtime_sensitive_params`, `SENSITIVE_PARAMS_KEY`. Sources: credential-like
  names, schema `secret`/`format: password` (`ModuleRegistry.secret_param_names`),
  `BaseModule.sensitive_params(params)`, runtime `_sensitive_params`. Empty,
  boolean and bare `{{..}}`/`${..}` values stay visible.
- `src/core/engine/step_executor/context_builder.py`: `HookContext.params` is the
  redacted copy (pre, post, retry). Modules still get plaintext.
- `src/core/engine/step_executor/executor.py`: trace `set_input` params redacted
  (resolved params held env-substituted secrets); a failure absorbed by
  `on_error: continue` is passed to the post-execute hook as `error` and fails
  the trace step. The workflow still continues. Only when the step's own result
  is the `{ok: False}` dict (a foreach aggregate is not affected).

## Why

Real run `~/.flyto/runs/20261003-8a757be6/steps.jsonl`: a login `browser.type`
(label "Password", `on_error: continue`) failed to find its field, was logged
`step_succeeded` with `{ok: false}` output, and its `input_params.text` held
the password in plaintext.

## Verified

- New tests: `tests/core/test_step_record_failure_and_param_redaction.py` (36),
  `tests/modules/test_browser_type_label_association.py` (18, real Chromium).
  Both red with the executor/type changes reverted (19 failures).
- Real-Chromium suites touching type/hints/click: 311 passed.
- `pytest -m 'not browser'`: 5081 passed before and 5154 passed after rebasing onto 2.36.0, 192 skipped (one order-dependent `test_version_identity` failure from the shared local venv, passes alone) (after
  linking `node_modules` for jsdom; without it `tests/test_hints.py` errors).
- `check_release_drift.py`, `check_documentation.py`, `check_brand_identity.py`,
  `lint-project-memory.sh`, ruff on touched files: pass.
- `flyto-index verify . --full-scan --strict`: 20 pass / 1 fail, the pre-existing
  `weak_scan_taint` (`api/routes/mcp.py` path) also on main.

## Not verified

- `flyto-index task validate` failed environmentally (repo-wide ruff on
  `examples/`, and its pytest lacks `pytest-cov`). Recorded, not fixed.
- No live Cloud run. Cloud writes `steps.jsonl` at `on_pre_execute`, so a
  password detected ONLY at runtime (selector `#pw`, nothing password-like in
  params) is redacted in the post hook, trace and output, but the
  `step_started` line was already written with the hook's pre-execute params.
  Closing that needs Cloud to rewrite/omit typed text on post-execute.

## Follow-ups

- Cloud: pin core 2.36.1; consider using the post-execute params for the
  step row.
