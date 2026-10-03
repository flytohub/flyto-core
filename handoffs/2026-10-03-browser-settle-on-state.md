# Browser modules settle on page state, not fixed sleeps

Owner: claude
Branch: claude/sd-k1
Date: 2026-10-03
Status: Implemented locally, not pushed or released

## What changed

- New `src/core/modules/atomic/browser/_settle.py`: `install_dom_watch` /
  `settle_dom` (MutationObserver quiet window that returns `unchanged` at once
  when an action mutated nothing), `settle_new_document` (interactive element,
  or loaded and DOM-still), `next_mutation`, and `first_state` (race named
  waits, losers cancelled, raising waits drop out).
- `browser.click`: the unconditional `wait_for_timeout(300/500)` is gone.
  `_NavigationSignals` listens for the clicked document's `request`,
  `framenavigated` and `requestfailed` for the whole click. A requested
  navigation is awaited to commit (cap 5 s); a new document then gets
  `domcontentloaded` plus `settle_new_document` (broadened to buttons and
  links); an in-place click gets `settle_dom` (100 ms quiet, 1 s cap). The
  inferred-tab 2 s wait races the popup against a same-tab navigation.
  `_resolve_button_or_link` uses one `or_()` locator `wait_for` and then keeps
  the exact-before-contains order; URL outcomes use `wait_for_url(...,
  wait_until='commit')`.
- `browser.login`: `_await_login_answer` races indicator / URL change /
  password hidden / MFA input / error message (baselines taken before submit),
  `wait_ms` as the cap only; the `wait_for_timeout(min(wait_ms, 3000))`
  fallback and both `networkidle` waits are gone.
- `browser.select` waits for option hidden or trigger `aria-expanded="false"`
  (1 s cap, swallowed). `browser.interact` select waits for the option visible,
  falling back to a forced click. `browser.form` `delay_between_fields_ms`
  defaults to 0 and skips the last field. `browser.detect` waits on an `or_()`
  union of its locator strategies plus a MutationObserver per frame.
  `browser.dialog` waits on an `asyncio.Event` set after the dialog is handled;
  `listen` also ends on the first dialog (an unanswered dialog blocks the page).
- `browser.wait` duration-only: logs a warning and returns `advice`.
  `validate_workflow` adds a `DURATION_ONLY_WAIT` warning (never an error).
  The MCP `execute_module` description says to wait on selector state.
- Tests: `tests/modules/browser/test_settle_on_state.py` (new, 14 cases);
  `tests/modules/test_browser_click_semantics.py` fakes gained `or_`,
  `wait_for`, `wait_for_url`, `on`/`remove_listener`, `evaluate`.

## Review follow-up (second commit)

- `browser.login`: after a `url_changed` / `password_gone` / `mfa_cleared`
  answer, `_settle_answered_page` follows JS redirect hops and waits for the
  landed document to load and go 500 ms DOM-quiet, or for a visible MFA input,
  capped by what is left of `wait_ms`. Fixes the regression where an OTP input
  rendered after load was missed (`mfa_detected=False`, `logged_in=True`).
- `install_dom_watch` also tracks timers (<= 1 s) and fetch/XHR started while
  the click is dispatched; `settle_dom` waits for them before its quiet window,
  and restores the page's own functions when done. A click that navigates
  from a timer or routes after a response now reports that navigation.
  `_click_and_settle` re-checks for a requested navigation after the settle.
- `next_mutation` coalesces wakes (50 ms quiet or 250 ms batch), so detect on
  a constantly mutating page runs about timeout / 250 ms passes.
- `_resolve_button_or_link` re-waits the union for the rest of its budget when
  the match re-rendered before the preference pass counted it.
- Tests: six new cases in `test_settle_on_state.py` (20 total); the no-change
  click test asserts `settle_dom` answered `unchanged` and the click took under
  0.25 s. All six new cases fail on the first commit's `src/`.

## Verified

- New tests: 20/20, three consecutive runs (14/14 at the first commit). They patch `Page/Frame.wait_for_timeout`
  and non-zero `asyncio.sleep` from browser modules to raise. Against the
  unmodified modules they fail (fixed `wait_for_timeout(500/300/3000)`, the
  5 s `networkidle` timeout and detect's 0.5 s sleep).
- `test_browser_click_semantics.py` 47/47 (63.7 s before, 27.7 s after),
  `test_browser_actions_outcome.py`, `test_browser_detect.py`,
  `test_crawl_infra.py` (except `test_robots_on_real_site`, which needs the
  public internet), `test_browser_mega_e2e.py` 39/39, `tests/core/api`,
  `tests/core/test_validation.py`, catalog/registration/outcome/policy suites.
- `scripts/check_documentation.py` PASS after regenerating `docs/reference/`
  and `docs/TOOL_CATALOG.md` and updating the inventory counts.
  `check_brand_identity.py` PASS, `lint-project-memory.sh` PASS. Ruff: no new
  findings in any touched file (pre-existing ones left as they were).

## Not verified / not done

- `pytest -m 'not browser and not e2e'`: 4751 passed, 174 skipped, 64 failed.
  All 64 (63 in `tests/test_hints.py`, a Node.js harness error, and
  `test_version_identity.py`, installed-package version) fail identically
  with this branch's `src/` stashed, so they are environmental.
- `flyto-index verify --strict --full-scan` in the worktree: every check passes
  except `weak_scan_taint` (one medium-confidence path flow
  `mcp_post -> run_recipe -> load_recipe`), which fails the same way with
  this branch's `src/` stashed. `task(action='validate')` was not run.
- Not released. Needs a flyto-core release, the flyto-cloud pin bump, and a
  Desktop release (Core is bundled by PyInstaller); the Cloud worker picks it
  up on its next deploy.
- Linting of composed templates in flyto-ai `compose_workflow` is not here;
  only Core's `validate_workflow` warns.
- The composed `login_erp` run (sidecar log 2026-10-03 07:30): its first
  `browser.type` waited 10 s for `#email` on `http://127.0.0.1:8080/`, a page
  with 0 inputs and 15 buttons. That is the template typing before it opens
  the sign-in form, so it timed out; no wait in Core caused it. The following
  `browser.wait` is a 1 s duration-only wait, which the new warning flags.

## Behaviour notes

- A login submit that produces no observable answer (no indicator, URL,
  password, MFA or error change) now waits the full `wait_ms`; before,
  `networkidle` could return after about 0.5 s on a quiet page.
- `browser.detect` on a page that mutates constantly re-runs a detection pass
  at most every 250 ms instead of every 500 ms, still capped by `timeout`.
- `browser.login` without a `success_indicator` now spends one 500 ms quiet
  window on the landed page after a redirect (the time `networkidle` used to
  imply). A landed page that keeps mutating ends at `wait_ms`.
- `browser.click` temporarily wraps `setTimeout`, `clearTimeout`, `fetch` and
  `XMLHttpRequest.prototype.send` between the click and its settle; a page
  that captured one of them in that window keeps a pass-through wrapper.
- A click that navigates from a timer longer than 1 s, or after a request
  slower than the 1 s settle cap, is still reported before the navigation;
  declare `expected_outcome` for those.
