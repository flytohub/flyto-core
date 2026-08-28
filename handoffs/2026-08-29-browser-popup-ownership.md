# Browser popup ownership closure

- Date: 2026-08-29
- Owner: codex
- Branch: `main`
- Status: implemented and validated locally; real EVTEK workflow rerun awaits
  action-time confirmation because it transmits stored login and TOTP values.

## Problem

An EVTEK portal action visibly opened the attendance application in a second
Chromium tab, but the workflow preview stayed on the opener. The immediately
following `browser.tab(action=switch, index=1)` failed with `Invalid tab index:
1. Valid range: 0-0`.

The workflow was not at fault. `browser.click` settled and refreshed hints only
against the pre-click page. It did not observe a page created by the action or
move the driver's current-page reference to it.

## Change

- `browser.click` now subscribes to the BrowserContext `page` event before the
  click and records the existing page set.
- A newly created page becomes `browser._page` before load settling, hint
  refresh, live preview, or the next workflow node.
- Explicit `_blank` and inline `window.open` actions receive a bounded wait for
  slow page creation; ordinary same-page clicks do not inherit that delay.
- Click output now exposes `opened_new_tab`, `tab_count`, `current_index`, and
  the final controlled `url`.
- The module contract version moved from `1.1.1` to `1.2.0`.
- A focused regression reproduces the production sequence and proves an
  immediate `browser.tab(index=1)` sees both pages.

## Verification

- Focused contract: 3 passed.
- Real headless Chromium smoke: a `_blank` link produced two context pages;
  click adopted index 1 and immediate tab switch to index 1 succeeded.
- Non-browser/non-E2E suite: 3,188 passed, 11 skipped, 275 deselected; 63.96%
  coverage.
- Browser suite: 242 passed, 5 skipped, 3,227 deselected.
- Generated reference/catalog, documentation contract, brand identity, focused
  Ruff, project-memory lint, package build, Twine validation, npm audit, and
  pip audit passed.
- Strict Flyto2 Indexer full scan: 19 passed, 0 warnings, 0 failures.
- The Indexer `task.validate` wrapper itself used repository-wide unrelated
  Ruff inputs and a pytest runtime without pytest-cov; local feedback
  `feedback-40f72b350e1bb231b52b13c3` records that runtime mismatch. The actual
  project-venv commands above passed.

## Next action

Restart flyto-cloud so its no-reload backend imports the changed editable core.
After the user confirms the credential-bearing run, execute template
`eYWGo53Jl7XorUf3RvED` and verify the live preview and terminal node remain on
the attendance page. Opening the attendance application is in scope; no actual
attendance record should be submitted as part of this proof.
