# crypto.totp and browser launch diagnosability

Owner: claude
Branch: codex/totp-browser-flow
Date: 2026-08-24

## What changed

- `src/core/modules/atomic/crypto/totp.py` — new `crypto.totp` module, standard
  library only. Accepts a Base32 setup key in any rendering an authenticator
  displays (lowercase, space-grouped, unpadded) or a whole `otpauth://totp/`
  enrolment URI, honouring the URI's `digits`, `period`, `algorithm`, `issuer`,
  and account label. Explicit parameters beat the URI; the URI beats the RFC
  default. `min_remaining` waits out the current window rather than returning a
  code that expires while the form carrying it is in flight.
  `otpauth://hotp/` is refused because a counter cannot be derived from a clock.
- `src/core/modules/atomic/crypto/__init__.py` — registers it.
- `~/.flyto/decode_authenticator_export.py` (outside every repository, mode
  700) — converts a Google Authenticator "transfer accounts" QR into a params
  file. That QR is `otpauth-migration://offline?data=`, a protobuf carrying
  every account at once, which `crypto.totp` deliberately does not accept: a
  workflow step needs one account's key, not a multi-account export. The tool
  lists entries without printing secrets, refuses HOTP entries, and writes the
  chosen key to a mode-600 file. Verified against a synthetic dense export
  (version 20 QR, eight accounts) inside a full-size phone screenshot.
- `src/core/browser/driver.py` — `_record_launch_failure` and
  `_no_engine_message`. Each channel and mode attempt is caught so the next can
  run, so the original exceptions were the only evidence of why nothing
  started; they are now appended to the raised error.
- `src/core/modules/atomic/browser/type.py` — accepts `string` input and
  `crypto.*` upstream so a TOTP step can feed a password field; `clear` now
  defaults to true.
- `workflows/totp_login_action.yaml` — parameterised login → OTP → act → prove
  template. Every site-specific string is an input; credentials and the
  authenticator secret are runtime inputs with no defaults.
- `tests/fixtures/totp_site.py` and `tests/e2e/test_totp_login_workflow.py` —
  a throwaway staff portal whose second factor is a real TOTP, and the two
  runs that drive the workflow against it. Its TOTP check is written against
  RFC 6238 directly rather than by calling `crypto.totp`, because a site that
  validated codes with the code that generates them would agree with itself no
  matter what either side did.
- `tests/modules/test_crypto_totp.py`, `tests/core/test_browser_driver_launch.py`,
  `tests/core/test_validation.py` — coverage for all of the above.
- Inventory copy moved 479 → 480 modules and 486 → 487 literal registrations
  across `README.md`, `PROJECT.md`, `ARCHITECTURE.md`, `STATE.md`, `demo.py`,
  `docs/`, `pyproject.toml`, `server.json`, `src/core/catalog_facts.py`, and
  `tests/test_public_metadata.py`; generated references and
  `tests/snapshots/production_modules.json` regenerated.

## Why

A site whose second factor is a TOTP could not be automated at all: the six
digits exist only inside a browser login flow and no API hands them over.
`crypto.hmac` had SHA1 but nothing decoded Base32, so the primitive was
unreachable. `browser.login` already detects an MFA prompt and stops at a
breakpoint for a human — this removes the human from that step.

Correctness is pinned to the published RFC 6238 and RFC 4226 vectors rather
than to this implementation's own output, so a later refactor that changes the
algorithm fails the suite instead of re-baselining itself.

Rejected: a deprecated `min_validity` alias alongside `min_remaining`. The
module has never shipped, so nothing can depend on the older name, and the
alias would have reached the UI and the generated catalog on day one.

The launch change is diagnosability only. The launch path itself was already
working and was not modified.

## Verified

- `No browser engine available` was **not** reproducible on this host. A real
  launch succeeds through the persistent Playwright Chromium context, direct
  (`LAUNCH_OK {'status': 'success', 'browser_type': 'chromium'}`) and through
  MCP `browser.launch` (`browser_session: 708182c9`). The channel fallback in
  `54b0fe4` is present on main.
- Forced failure now names its cause:
  `No browser engine available. … Attempts: chrome-canary-does-not-exist
  (persistent): BrowserType.launch_persistent_context: Unsupported chromium
  channel …; chrome-canary-does-not-exist (regular): BrowserType.launch: …`
- `.venv/bin/python -m pytest -m 'not browser and not e2e'` — 3,166 passed,
  11 skipped, 273 deselected, coverage 63.38% against the 60% floor.
- `tests/modules/test_crypto_totp.py` — 57 passed, covering the RFC 6238
  vectors for SHA1/SHA256/SHA512 and the RFC 4226 counter vectors.
- All 18 workflow steps pass `validate_node_params(..., strict=True)` against
  the live module schemas — which turned out not to be worth much on its own;
  see the defects below that only a real run surfaced.
- **The workflow now runs end to end against a site that refuses a wrong
  code.** With the right secret: no error, 18/18 steps, evidence written, and
  the site recorded exactly one punch at `21:51:24`. With a secret for a
  different seed: the run fails at `await_signed_in`, no evidence file is
  written, and **the site recorded nothing**. That second case is the whole
  point of the workflow — a run cannot report success unless the site
  registered the action — and it is now a test rather than a claim.
- Both secret import forms produce the same code, and the URI form recovers
  issuer and account.
- `scripts/check_documentation.py` and `scripts/check_brand_identity.py` pass.
- Audited-surface Ruff (the `docs/TESTING.md` list, extended with
  `totp.py` and `tests/modules/test_crypto_totp.py`) is clean.
- `flyto-index verify . --full-scan --strict` — 19 pass, 0 warn, 0 fail, on a
  clean tree.
- The 21 English `modules.crypto.totp.*` keys are on flyto-i18n `main`, in
  `locales/modules/en/crypto.json` and in the built `dist/` bundles. Their
  values survived a later Cloud sync unmangled, which matters because
  `sync-from-core.py` would have rewritten them with the shifted label /
  description pairing described under Follow-ups.
- The published artifact was checked, not just the source. `flyto-core 2.31.0`
  installed from PyPI into a clean Python 3.12 environment resolves
  `crypto.totp`, returns the RFC 6238 value `94287082` at t=59, imports an
  `otpauth://` URI and recovers its issuer and account, and rolls forward
  under `min_remaining`. `_no_engine_message` is in the same wheel.
- Edge cases probed against the shipped module: a padding-only or single-
  character secret, a non-Base32 character, an `otpauth://` URI with an empty
  `secret=`, and an uppercase `OTPAUTH://TOTP/` scheme all behave correctly.

## Not verified

- No run against the user's own portal. The sequence is proven end to end
  against a site built for the purpose, so the engine path, the browser steps,
  the TOTP interop, and the confirmation gate are all exercised; what remains
  unproven is only that portal's particular selectors and confirmation marker.
- `flyto-index task validate` reports two failures, both environmental:
  repo-wide Ruff flags `examples/agent_demo/planner.py` and
  `examples/agent_demo/run.py` (I001), which this change does not touch and
  which already fail at `344187c`; and its pytest invocation uses an
  interpreter without `pytest-cov`, so `pyproject.toml`'s `--cov` addopts are
  rejected before any test runs. The repo venv runs the same tests green.
- The other fifteen locales fall back to English for the new keys.
- Browser and E2E suites were not run.
- A secret that decodes to fewer than 16 bytes is accepted. RFC 4226 requires
  at least 128 bits, but real deployments vary and rejecting short keys would
  break working setups, so a truncated paste still produces codes the site
  will refuse rather than an error naming the cause.

## Defects that only running it surfaced

Schema validation passed all three of these. They are recorded because the
lesson generalises: a workflow that has never run is not a verified workflow.

- `behavior: human` is not a valid `browser.launch` value (`fast`, `normal`,
  `careful`, `human_like`), so the run died on its second step.
  `workflows/scrape_chatgpt_share.yaml` carried the same value and could never
  have run either; both are fixed. `validate_node_params(..., strict=True)`
  does not check enum membership.
- The engine reads a workflow's `params:` list, not an `inputs:` mapping.
  Nothing anywhere reads `inputs:`, so every `default:` declared under it was
  inert and the unsupplied values reached Playwright as the literal
  `${otp_field_selector}`. Both workflows now declare `params:`, and the e2e
  test omits every defaulted parameter so that the defaults are exercised
  rather than assumed.
- The SSRF guard blocks loopback, private addresses, and any port outside
  80/443/8080/8443. `browser.goto`'s `ssrf_protection` parameter does not open
  it — `_ssrf_enforced()` returns `True` unconditionally, by design and with a
  comment saying so — yet the parameter is still offered in the module schema
  as though setting it did something. Only `FLYTO_ALLOWED_HOSTS` /
  `FLYTO_ALLOW_PRIVATE_NETWORK` change the outcome. The workflow now says so,
  because a staff portal is normally on a private network.

## Follow-ups

- Bind the workflow to a real site and record an end-to-end run.
- Translate `modules.crypto.totp.*` beyond English.
- Fix flyto-i18n `scripts/sync-from-core.py`: it pairs each label with the
  following field's description instead of its own, which is why
  `modules.crypto.hmac.params.algorithm.description` reads "Secret key for
  HMAC". A full sync would also add 410 unrelated keys across other categories.
- Fix the two pre-existing `examples/agent_demo/` Ruff findings so repo-wide
  `task validate` can go green.
- Consider removing `ssrf_protection` from the `browser.goto` schema, or making
  it reject a `false` that cannot be honoured. A parameter that is documented,
  offered, and ignored is worse than no parameter.
- Consider having `validate_node_params(..., strict=True)` check `select`
  fields against their declared options. It would have caught
  `behavior: human` before a browser ever started.

## Note on ownership

This change was produced by Claude and Codex editing the same working tree at
the same time, which is what `CLAUDE.md` tells both agents not to do. Codex
renamed `min_validity` to `min_remaining`, added the `browser.type` connection
rules, and committed the combined result as `dad6ef4` on this branch. The
verification recorded above was run by Claude against that commit.
