# `browser.fill_form`: a whole form in one call (2.38.0)

Owner: claude
Branch: claude/browser-fill-form
Date: 2026-10-04

## What changed

- `src/core/modules/atomic/browser/fill_form.py` (new): `browser.fill_form` 1.0.0.
  `fields` [{label|selector, value|sensitive_value}] for text/textarea/number/date,
  select (option value or text; list for multi), checkbox (true/false), radio
  (option value or text; a group may be named by its fieldset legend or
  radiogroup name); `uploads` [{label|selector, path}] (path checked with
  `validate_path_with_env_config`, as `browser.upload`); `submit` {label|selector}
  or {} for the form's own submit button; `confirm` {selector?, text?, timeout_ms?}.
  Every target (fields, uploads, submit control) is resolved before the first
  write, waiting up to `resolve_wait_ms` (3 s) for late-rendering controls via
  `next_mutation`. Error codes: `FIELDS_NOT_FOUND` (nothing written),
  `FILL_FAILED` (not submitted), `FORM_INVALID` (constraint validation read from
  `validity`, not submitted), `CONFIRMATION_NOT_SEEN` (submitted; readback holds
  the page text). Per-field read-back from the live DOM; password inputs,
  credential-named labels/selectors and `sensitive_value` are returned as `***`
  and `_sensitive_params: ["fields"]` is set (same rule as `browser.type`).
- `browser/_label_resolve.py` (new): the label resolver moved out of `type.py`
  unchanged, plus `accept=` (which controls qualify) and
  `label_fallback_selectors()`. `browser.type` imports it; its tests pass unchanged.
- Contract: `provides_capability="browser.fill_form"`, `controlled`,
  `actuates: False`, `cancellable`, not idempotent, effect
  `external.record.changed`. `actuates: True` was rejected on purpose: flyto-ai
  `permissions.grade_module_contract` grades any actuating contract risk 4 /
  `DANGER_FULL` (a confirmation), which would put one fill_form above the
  `browser.type` calls (legacy `WORKSPACE_WRITE`) it replaces. `controlled`
  without `actuates` grades risk 3 "external write", which is what a submit is.
- `mcp_handler.py` `execute_module` description: a FORMS line ("read the form
  once, then call browser.fill_form once"), the module in the common list, and
  a params example. `browser.form` was dropped from the INTERACTION list.
- The snapshot guard sets in `modules/atomic/llm/_resilience.py` are unchanged:
  fill_form is NOT in `_INTERACT_MODULES`. A wrong label fills nothing and says
  so, and adding it would cost an injected-snapshot round when the agent
  already read the page by other means.
- Version 2.38.0; catalog_facts 482 modules / 55 browser; docs, references,
  `tests/snapshots/production_modules.json`, `tests/test_public_metadata.py`
  counts regenerated.

## Why

In the award demo the computer AI took about 100 s to file the 新增紀錄 form
after the operator said yes: one model round-trip per field, upload and the
submit. No module filled a form by label in one call (`browser.form` keys by
name/id only, no uploads, reports success with failed fields).

## Verified

- `tests/modules/test_browser_fill_form.py`: 20 passed (8 unmarked, 12
  `@pytest.mark.browser` against real Chromium with
  `tests/fixtures/fill_form_page.html`); `test_browser_type_label_association.py`
  23 passed after the resolver move.
- Non-browser suite, branch vs a clean origin/main checkout on this machine:
  the only failures new on the branch were the module-count/description tests
  and `test_rest_get_response_carries_no_volatile_detail` (my schema said
  "secret"/"password"); all fixed and rerun green. The ~64 failures common to
  both are local-environment (installed-package metadata etc.).
- `scripts/check_documentation.py`, `check_brand_identity.py`,
  `lint-project-memory.sh` pass; ruff clean on changed files.
- `flyto-index verify . --full-scan --strict`: all pass except
  `weak_scan_taint`, the pre-existing `api/routes/mcp.py -> cli/recipe.py`
  path-traversal finding also on main.
- MCP `task(action='validate')` could not target this repo (the session's MCP
  server is pinned to flyto-indexer); ruff + pytest were run directly instead.
- Measured on a throwaway demo ERP (port 18087, temporary `ERP_DATA_DIR`,
  throwaway password hash; live 8080 untouched), 3 rounds each, module time only:
  fill_form 1 call, median 393 ms; field by field 10 calls, median 589 ms. All
  6 records stored with photo and `DELIVERED`.

## Not verified

- No run with a real LLM agent: the ~100 s is model round-trips, which this
  change removes (10 calls -> 1) but which were not re-timed end to end.
- Not released to PyPI or tagged. flyto-cloud pin not bumped (coordinator).

## Follow-ups

- flyto-cloud: `api/ai/moat.py` `_SYSTEM_PROMPT_TEMPLATE` still says "fill
  forms ... browser.type, browser.click"; `services/space_tasks/inferred_requirements.py`
  maps unknown `browser.*` to `browser.navigate`, so fill_form should be added
  as `browser.interact`; `services/runtime/execution/redaction.py` special-cases
  `browser.type` `text` only, so check fill_form's `fields` redaction there.
