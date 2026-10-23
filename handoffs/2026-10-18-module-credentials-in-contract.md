# Module credentials declared in the contract

Owner: claude
Branch: lane/secrets-at-save (from `origin/feat/unified-platform-integration-20261018`)
Date: 2026-10-18

## What changed

A host that stores a workflow (Cloud's save gate and its copy) asks the
module contract which values are credentials. Before this change, part of the
answer was the engine's name rule, which misreads names in both directions.

- `BaseModule.sensitive_paths(params)` (`src/core/modules/base.py`) names each
  credential as a path into the params. `("text",)` is a whole parameter;
  `("fields", 1, "value")` is one leaf. By default it returns the names from
  `sensitive_params` as whole-parameter paths, so existing modules are
  unchanged.
- `browser.fill_form` overrides it (`src/core/modules/atomic/browser/fill_form.py`):
  - it returns every `sensitive_value`, and every `value` typed into a field
    whose label or selector names a credential;
  - `sensitive_params` is now derived from `sensitive_paths`;
  - `items.properties.sensitive_value` carries `secret: True`.
- `ModuleRegistry.cleared_param_names` (`src/core/modules/registry/core.py`)
  reads `secret: False`, which outranks the name rule.
- `redact_step_params` (`src/core/engine/redaction.py`):
  - it honours `secret: False`;
  - it redacts exactly the leaves a module names. A fill_form step record
    keeps its email field and labels readable.
- Catalog: every parameter named like a credential now states `secret`. That
  is 41 entries in 30 module files:
  - 38 are `true` (GitHub, Slack, Stripe, Airtable, Notion, Sheets, Jira,
    Salesforce, Twilio, Telegram, WhatsApp, AWS S3, SMTP, SSH, Anthropic,
    Gemini, ui.evaluate, figma, jwt_verify);
  - 3 are `false`: `browser.login.password_selector`,
    `auth.oauth2.token_url` and `browser.proxy_rotate.preserve_cookies`.
- `browser.type` already declared its credentials (`sensitive_text` is
  `secret`/`format: password`; `text` when `input_type` is password or the
  target names a credential). Its contract did not change. It is now covered
  by the test.
- `tests/core/api/test_capability_surface.py` still forbids the words
  "secret" and "password" in `/v1/capabilities`, except as the schema marker
  `"secret": true|false` / `"format": "password"`. The marker names no value,
  and hosts read it from the manifest.
- Version stays 2.41.0 (unreleased). The CHANGELOG entry is under 2.41.0
  Added. The generated reference has been regenerated, and the inventory
  tokens are 6,408 declarations and 239,653 lines.

## Why

These were the copy lane's findings. Cloud refused nothing that the module
contract would have called a secret, because the contract never said it. For
example, `fields[].sensitive_value` had no marker, and a "Password" field's
`value` was only reachable by the coarse `sensitive_params -> {"fields"}`.

Rejected: a Cloud-side name list (owner rule: contract, never name), and
widening the engine name rule. That rule already misreads `password_selector`
and `token_url`, and in Cloud a false positive now refuses a save.

## Verified

- Failing first: the new `tests/modules/test_module_sensitivity_contract.py`
  had 19 failed and 1 passed before the change. After the change, 20 passed.
- `pytest tests/modules tests/core -m "not browser"`: 4,629 passed, 165
  skipped, 0 failed.
- fill_form and browser.type tests, including real Chromium: 43 passed.
- `tests/runtime`, top-level tests and `tests/browser`: 664 passed and 63
  failed. All 63 failures are in `tests/test_hints.py`, and the same 63 fail
  on the base commit with the change stashed.
- `scripts/generate_reference.py` was run, then `check_documentation.py`
  passed: 186 Markdown files.
- `check_brand_identity.py` passed: 1,275 files.
- `lint-project-memory.sh` passed.
- ruff on the changed files reports 36 findings both before and after the
  change. All are pre-existing, and none are in new code.
- `flyto-index verify --strict`: 20 passed and 1 failed. The failure is
  `weak_scan_taint` on mcp -> recipe path traversal, and the same failure
  appears with the change stashed.

## Not verified

- No CI run and no release.
- Cloud pins flyto-core by commit (`795d07e`, 2.40.0). Until that pin moves to
  a commit with this change, Cloud reads fill_form coarsely: the whole
  `fields` list counts as the secret, and a `value: ${secrets.X}` on a
  Password field still counts as a credential, because 2.40's
  `sensitive_params` does not skip references. `sensitive_value:
  ${secrets.X}` passes on both.
- Third-party packs are not audited. The catalog test covers only the modules
  registered in this repository.

## Follow-ups

- Bump Cloud's flyto-core pin once this lands, in the Cloud lane
  `lane/secrets-at-save`.

## Addendum (second commit): engine step settings are one table

- `core.engine.flow_control.STEP_SETTING_KEYS` and `is_step_setting` list
  the per-step execution settings the engine reads off a step. These are
  `timeout`, `retry`, `on_error`, `when`, `foreach`, `as` and `output`, plus
  the legacy spellings `onError`, `runIf` and `foreachAs`.
- No module schema declares these settings. Cloud's contract reader reads
  this table, so it does not refuse them as undeclared module parameters.
- `tests/core/test_step_setting_keys.py` ties the table to the engine
  source: 3 tests failed before the change and pass after.
- The CHANGELOG entry is under 2.41.0. The generated reference was
  regenerated, and the inventory tokens are now 6,409 declarations and
  239,669 lines.
- Checks after the change:
  - `tests/core` and `tests/modules` (excluding browser-marked): 4,632
    passed, 165 skipped;
  - docs check passed on 187 Markdown files, the brand check on 1,276 files,
    and the memory lint passed;
  - `verify --strict`: 20 passed, 1 failed. The failure is the same
    pre-existing `weak_scan_taint` finding.
- Cloud must pin a flyto-core commit that contains this table. Until it
  does, Cloud's reader treats `timeout` and the other settings as
  undeclared, and refuses them.
