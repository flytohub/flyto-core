# Browser click outcome verification

- Date: 2026-08-30
- Owner: codex
- Branch: `main`
- Status: implemented and locally validated; not pushed or deployed

## Problem

A browser click returning without an exception proved only that Playwright
dispatched the action. Site JavaScript could suppress an intended popup or the
page could already be in the requested terminal state, while the workflow
still reported success and blamed the next node.

## Change

- `browser.click` moved from contract 1.2.0 to 1.3.0.
- An explicit `_blank`, `formtarget=_blank`, or inline `window.open` intent now
  requires a new page within a bounded outcome timeout.
- Authors may require `new_tab`, `url_change`, `url_contains`,
  `selector_visible`, `selector_hidden`, or explicit `click_only` behavior.
- URL/selector terminal states already true before dispatch are refused as
  non-evidence.
- Output separates `verification_status`, `effect_observed`, observed effects,
  and pre/post URL.
- Foreground page adoption remains exactly the 1.2.0 contract; `browser.tab`
  was not modified.

## Verification

- Focused browser-click contract: 11 passed, including a real Chromium
  state-transition proof and an intercepted `_blank` failure.
- Non-browser suite initially found only generated catalog/reference drift from
  the public schema change; regeneration and documentation reconciliation fixed
  those gates. Final replay: 3,222 passed, 12 skipped, 248 browser-marked
  deselected.
- Browser suite: 243 passed and 5 skipped, including the real Chromium click
  outcome proofs.
- Package build and Twine checks passed; npm and locked Python dependency
  audits reported zero known vulnerabilities.
- Strict Indexer closure: 19/19 passed, health 92/A, documentation 100, zero
  secret findings and zero high-risk taint flows.

## Boundaries

No live EVTEK attendance action, credential transmission, remote deployment,
push, or change to `browser.tab` is part of this work.
