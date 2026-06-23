# Warroom Hydration-Aware Replay Assertions

Date: 2026-06-23
Status: Active

## Context

The Flyto2 Product Verification full-stack smoke reached the engine and
verification microservice, but the generated scenario sometimes asserted
`document.body.innerText.length > 0` immediately after `browser.goto`.

For SPA routes this can run before hydration finishes. The evidence pack then
records a false P0 blank-screen finding, drops replay reliability to 0.5, and
blocks the 90-point gate even when the route later renders.

## Change

`warroom.generate_scenarios` now emits an async DOM assertion script that polls
for up to five seconds before measuring body text and horizontal overflow.
The script is emitted as an immediately evaluable function expression
(`(async () => ...)`) because `browser.evaluate` wraps non-function scripts.

This keeps the blank-screen guard deterministic:

- If the page hydrates, replay proceeds with stable DOM evidence.
- If the body is still empty after the timeout, the P0 assertion still fails.

## Verification

- `/opt/homebrew/bin/python3.11 -m pytest --no-cov tests/modules/test_warroom_modules.py tests/test_verification_service.py -q`

## Follow-Up

- Keep future replay generators using state/event waits where possible instead
  of fixed sleeps.
- Add route-specific ready selectors when product specs provide them.
