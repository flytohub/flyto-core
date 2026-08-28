# Semantic Browser Click Closure

Owner: codex
Branch: main
Date: 2026-08-28

## What changed

`browser.click` button/link mode now resolves visible actions by role and
accessible name. The shared hint extractor applies the same naming sources and
does not offer hidden links. Click honours `timeout_ms`, captures the pre-click
URL before the action, and reports the semantic locator it used. Module copy
now describes selector-free use; CSS/XPath remains advanced mode.

## Why

The EVTEK login page exposed a visible icon-only application link whose name
came from image alt text, plus hidden duplicate text. The Element Picker offered
`kintone`, while the executor's unrelated CSS `:has-text()` query timed out.
The user-selected value therefore was not executable without hand-written CSS.

## Verified

- 81 focused hint, semantic-click, wait, and browser-launch tests passed.
- A real local Playwright smoke offered only the visible icon link and clicked
  it by the accessible name `kintone`.
- The Cloud EVTEK flow completed browser creation, nested login, authenticated
  visible-state verification, and `browser.click` into the kintone portal. The
  run artifact records success with `method=button` and a link-role semantic
  locator.
- Documentation, brand, changed-surface Ruff, and project-memory checks passed.
- Full offline suite: 3,186 passed, 11 skipped, 275 deselected; 63.97%
  coverage against the 60% floor.
- Package sdist and wheel built successfully and passed Twine; Python and Node
  dependency audits found no known vulnerabilities.
- Strict Indexer passed 19/19 with no warnings or failures.

## Not verified

The flow intentionally stopped at the portal. It did not open the attendance
application or perform a clock-in/clock-out action.

## Follow-ups

Build the next attendance workflow only after its read-only state and explicit
action-confirmation contract are defined separately.
