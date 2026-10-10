# Pre-execute hook write-back and label ranking (2.37.1)

Owner: claude
Branch: claude/core-browser-verify
Date: 2026-10-04

Rebased onto 2.37.0 (#127) before merge; the version is 2.37.1.

## What changed

An adversarial review of 2.36.1 (`2026-10-04-browser-type-label-and-step-records.md`)
found three defects; this fixes them.

1. **Credential resolution broke (regression in 2.36.1).** 2.36.1 handed
   pre-execute hooks a redacted *copy* of the step params. Cloud's
   `CredentialResolverHooks.on_pre_execute` resolves `secretRef` mappings and
   `${secrets.NAME}` strings by rewriting `context.params` in place, and that
   rewrite reached the module only by aliasing. On 2.36.1 the module received the
   unresolved reference. Under a credential name (`password`, `api_key`) the copy
   showed `[REDACTED]`, so the hook had nothing to resolve. Inside a reference,
   `credential_name` was redacted too.
   - `src/core/engine/redaction.py`: added `snapshot_hook_params` and
     `apply_hook_param_changes`. The engine writes back exactly the leaves a hook
     changed, so a `[REDACTED]` placeholder never overwrites a real value.
   - A mapping under a credential name is walked instead of blanked: a credential
     is a scalar, so a mapping there is a reference to one.
   - Names ending `_name`, `_id`, `_ref`, `_type`, `_kind` or `_label` stay
     visible.
   - Wired in `step_executor/executor.py` (pre-execute) and
     `workflow/engine.py` (resource sub-nodes).
2. **Redaction gaps.**
   - Resource sub-node hooks (`engine._execute_resource_sub_nodes`, e.g. an
     `ai.model` carrying `api_key`) still got raw params.
   - The name rule missed `Authorization`, `Cookie` and camelCase tokens
     (`accessToken`, `refreshToken`, `idToken`).
   - Both are fixed. A list under a credential name is still blanked.
3. **`browser.type` 1.2.1 label ranking.** 2.36.1 tried the wrapping-label
   selector (`label:has-text >> input`, a substring match on any input) before
   the ranked associations. Target "Password" then went to the wrong field in
   three cases:
   - it filled the "Show password" checkbox (and errored);
   - it typed into a wrapped "Confirm password" field;
   - a partial `label[for]` match ("Password hint", a plain text box) beat an
     exact `aria-label`.

   The fix is one page-side ranked list covering every association (`label.control`
   for wrapping and `for=` labels, `aria-labelledby`, `aria-label`). Sort order:
   exact text, then visible, then kind, then document order. Selectors prefer a
   unique id, then `aria-labelledby`, name or aria-label, then a structural
   `css=` path. The static fallbacks only match inputs that accept text.

## Why

The incident in the baseline was a password typed into nothing. 2.36.1 fixed
that layout, but on common login markup it could now put the password into a
visible plain-text field. Its redaction also silently disabled Cloud's
credential injection, and that would land as soon as Cloud pins 2.36.1.

## Verified

- Repro against both Cores, using Cloud's real
  `services/runtime/execution/credential_hooks.py` (token mint stubbed):
  - 2.36.1 (`46d3e27`): the module receives
    `{'type': 'secretRef', ...}` / `'${secrets.api}'`;
  - this branch: the module receives the resolved values.
- New tests fail on 2.36.1 and pass here:
  - `tests/core/test_step_record_failure_and_param_redaction.py`: 11 failures on
    2.36.1 for write-back, header and camelCase names, and reference labels;
    the sub-node test fails as well.
  - `tests/modules/test_browser_type_label_association.py`
    (`TestTheExactVisibleFieldWins`): 4 of 5 pages fail on 2.36.1.
- Real Chromium suites: `test_hints`, `test_browser_detect`, browser mega-e2e,
  a_outcome, click semantics and type label association. 373 passed.
- `pytest -m 'not browser'`, first run: 5182 passed and 3 failed.
  - Two of the failures were my test module id leaking into the production
    snapshot. I renamed it to `test.record.*` and they pass.
  - `test_version_identity` is environmental (shared venv) and passes alone.
- Final rerun: 5184 passed, 192 skipped, 1 failed (`test_version_identity`,
  environmental), coverage 67.51%.
- These pass: `check_release_drift`, `check_documentation`, `check_brand_identity`,
  `lint-project-memory` and ruff on the touched files. `executor.py` has 11
  pre-existing ruff findings, the same as on main.
- `flyto-index verify --strict`: 20 pass and 1 fail. The fail is the
  pre-existing `weak_scan_taint` finding, which is also failing on main.
- `flyto-index task validate`: fails for environmental reasons, as on 2.36.1:
  repo-wide ruff findings in `examples/`, and the indexer's pytest lacks
  `pytest-cov`.

## Not verified

- No Cloud or Desktop run. Cloud still pins an older Core, and old Desktops
  bundle their own.
- A hook running *after* the credential resolver, in the same Cloud composite,
  still sees the resolved value in `context.params`. That is the same as before
  2.36.1, and Cloud's own `redact_sensitive` decides what it logs.
- A password that is only detected at runtime (selector `#pw`) is still in
  Cloud's `step_started` line. This gap is carried over from 2.36.1.

## Follow-ups

- Cloud: pin Core 2.37.1 or later. 2.36.1 and 2.37.0 break `secretRef`
  injection.
- Cloud (generic): rewrite `step_started` params when the post-execute params
  arrive.
- Tag and release 2.37.1.
